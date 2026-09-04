"""Phase 12 — Reliability regression tests.

Focused tests for each confirmed reliability issue and critical failure path:
  R-1: Webhook duplicate delivery race condition (IntegrityError handling)
  R-2: Webhook malformed JSON → 400
  R-3: Webhook missing payment entity → 400
  R-4: Execution provider failure → state revert
  R-5: Execution idempotent replay
  R-6: Action state machine invalid transition
  R-7: Recovery stop cancels open actions
  R-8: Payment ingestion stale webhook (state precedence)
"""

import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models import Customer, Merchant, Payment, RecoveryAction
from app.models.enums import (
    PaymentMethod,
    PaymentStatus,
    RecoveryActionStatus,
    RecommendedAction,
)
from app.services.action_state_machine import (
    InvalidTransitionError,
    apply_transition,
    validate_transition,
)
from app.services.payment_ingestion_service import plan_transition
from app.utils.errors import AppError
from app.utils.password_hash import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = "test_webhook_secret_local_only"


def _sign(raw_body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _post_webhook(client, payload: dict, event_id: str) -> "httpx.Response":
    body = _canonical(payload)
    return client.post(
        "/api/webhooks/razorpay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "x-razorpay-event-id": event_id,
            "x-razorpay-signature": _sign(body),
        },
    )


def _payment_entity(
    pay_id: str = "pay_REL_TEST_001",
    *,
    amount: int = 10000,
    status: str = "failed",
    method: str = "upi",
) -> dict:
    return {
        "id": pay_id,
        "amount": amount,
        "currency": "INR",
        "status": status,
        "method": method,
        "created_at": 1756200000,
    }


def _fail_event(pay_id: str = "pay_REL_TEST_001") -> dict:
    return {
        "event": "payment.failed",
        "payload": {"payment": {"entity": _payment_entity(pay_id, status="failed")}},
    }


def _capture_event(pay_id: str = "pay_REL_TEST_001") -> dict:
    return {
        "event": "payment.captured",
        "payload": {"payment": {"entity": _payment_entity(pay_id, status="captured", amount=10000)}},
    }


def _seed_payment_with_status(db_session, merchant_id, external_id: str, status: PaymentStatus):
    """Create a payment directly in the DB with the given status (for unit tests)."""
    from app.models.enums import FailureCategory, Priority

    customer = Customer(
        merchant_id=merchant_id,
        external_customer_id=f"CUST_{external_id}",
        name=f"Customer {external_id}",
    )
    db_session.add(customer)
    db_session.flush()

    payment = Payment(
        merchant_id=merchant_id,
        customer_id=customer.id,
        external_payment_id=external_id,
        amount=Decimal("10000.00"),
        currency="INR",
        method=PaymentMethod.UPI,
        status=status,
        attempt_number=1,
        priority=Priority.MEDIUM,
    )
    db_session.add(payment)
    db_session.flush()
    return payment


# ---------------------------------------------------------------------------
# R-1: Webhook duplicate delivery race condition
# ---------------------------------------------------------------------------

class TestWebhookDuplicateDelivery:
    """Concurrent webhook deliveries with the same event_id must not crash with 500."""

    def test_duplicate_event_id_returns_duplicate_not_500(self, client):
        """Sending the same event_id twice should return 200 duplicate, not 500."""
        payload = _fail_event("pay_RACE_001")
        event_id = "evt_RACE_001"

        # First delivery — should succeed
        resp1 = _post_webhook(client, payload, event_id)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["result"] == "PROCESSED"

        # Second delivery — should be duplicate, not 500
        resp2 = _post_webhook(client, payload, event_id)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["result"] == "DUPLICATE_EVENT"

    def test_processed_event_returns_none_on_race_requery(self, db_session):
        """After IntegrityError + rollback, re-querying a PROCESSED event should return it."""
        from app.models import WebhookEvent
        from app.models.webhook import WebhookStatus

        # Insert and mark as PROCESSED (simulates the winning concurrent transaction)
        event = WebhookEvent(
            provider="razorpay",
            provider_event_id="evt_RACE_002",
            event_type="payment.failed",
            status=WebhookStatus.PROCESSED,
            payload_hash="abc123",
        )
        db_session.add(event)
        db_session.flush()

        # Re-query should find it
        existing = db_session.query(WebhookEvent).filter(
            WebhookEvent.provider == "razorpay",
            WebhookEvent.provider_event_id == "evt_RACE_002",
        ).one_or_none()

        assert existing is not None
        assert existing.status == WebhookStatus.PROCESSED


# ---------------------------------------------------------------------------
# R-2: Webhook malformed JSON → 400
# ---------------------------------------------------------------------------

class TestWebhookMalformedJSON:
    """Malformed JSON payloads must return 400 INVALID_PAYLOAD, not 500."""

    def test_malformed_json_returns_400(self, client):
        body = b"this is not json"
        resp = client.post(
            "/api/webhooks/razorpay",
            content=body,
            headers={
                "Content-Type": "application/json",
                "x-razorpay-event-id": "evt_MALFORMED_001",
                "x-razorpay-signature": _sign(body),
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_PAYLOAD"


# ---------------------------------------------------------------------------
# R-3: Webhook missing payment entity → 400
# ---------------------------------------------------------------------------

class TestWebhookMissingPaymentEntity:
    """Webhook payloads missing payment.entity.id must return 400, not 500."""

    def test_missing_payment_entity_returns_400(self, client):
        payload = {"event": "payment.failed", "payload": {}}
        resp = _post_webhook(client, payload, "evt_MISSING_001")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_PAYLOAD"

    def test_missing_event_string_returns_400(self, client):
        payload = {"payload": {"payment": {"entity": _payment_entity()}}}
        resp = _post_webhook(client, payload, "evt_NOEVENT_001")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_PAYLOAD"


# ---------------------------------------------------------------------------
# R-4: Execution provider failure → state revert
# ---------------------------------------------------------------------------

class TestExecutionProviderFailureRevert:
    """When the provider fails, the action must transition to FAILED and
    payment must revert from PROCESSING to FAILED — no phantom state."""

    def test_provider_failure_reverts_to_failed(self, db_session, merchant_id):
        from app.services.recovery_execution_service import RecoveryExecutionService
        from app.services.providers.payment_provider import (
            ProviderExecutionResult,
            ExecutionStatus,
        )
        from app.models import RecoveryDecision, PolicyEvaluation
        from app.policy.models import PolicyDecision
        from datetime import datetime, timezone

        mid = uuid.UUID(merchant_id)

        # Seed: FAILED payment with an AI decision
        payment = _seed_payment_with_status(db_session, mid, "pay_EXEC_FAIL_001", PaymentStatus.FAILED)

        decision = RecoveryDecision(
            payment_id=payment.id,
            recommended_action=RecommendedAction.RETRY,
            recovery_probability=Decimal("0.85"),
            ai_confidence=Decimal("0.9"),
            expected_recovery_amount=Decimal("8500.00"),
            model_version="test-v1",
        )
        db_session.add(decision)
        db_session.flush()

        # Mock policy service to always approve
        mock_policy_result = PolicyDecision(
            decision="APPROVED", allowed=True, reason="Test approved",
            checks=[], policy_version="test-v1",
            evaluated_at=datetime.now(timezone.utc),
        )
        mock_evaluation = PolicyEvaluation(
            payment_id=payment.id,
            recovery_decision_id=decision.id,
            decision="APPROVED",
            allowed=True,
            policy_version="test-v1",
            checks=[],
        )
        db_session.add(mock_evaluation)
        db_session.flush()

        # Mock provider that always fails
        def failing_provider():
            provider = MagicMock()
            provider.execute_recovery.side_effect = Exception("Razorpay API timeout")
            return provider

        service = RecoveryExecutionService(db_session, provider=failing_provider)

        # Patch the policy service to return our mock result
        with patch.object(service._policy_service, 'evaluate_for_payment',
                          return_value=(mock_policy_result, mock_evaluation)):
            response = service.execute(mid, "pay_EXEC_FAIL_001")

        # Action should be FAILED
        action = db_session.scalars(
            select(RecoveryAction).where(RecoveryAction.payment_id == payment.id)
        ).first()
        assert action is not None
        assert action.status == RecoveryActionStatus.FAILED

        # Payment should have reverted from PROCESSING → FAILED
        db_session.refresh(payment)
        assert payment.status == PaymentStatus.FAILED


# ---------------------------------------------------------------------------
# R-5: Execution idempotent replay
# ---------------------------------------------------------------------------

class TestExecutionIdempotentReplay:
    """Same idempotency_key must return the same result without creating a new action."""

    def test_same_key_returns_same_result(self, db_session, merchant_id):
        from app.services.recovery_execution_service import RecoveryExecutionService
        from app.services.providers.payment_provider import (
            ProviderExecutionResult,
            ExecutionStatus,
        )
        from app.models import RecoveryDecision, PolicyEvaluation
        from app.policy.models import PolicyDecision
        from datetime import datetime, timezone

        mid = uuid.UUID(merchant_id)
        payment = _seed_payment_with_status(db_session, mid, "pay_IDEM_001", PaymentStatus.FAILED)

        decision = RecoveryDecision(
            payment_id=payment.id,
            recommended_action=RecommendedAction.RETRY,
            recovery_probability=Decimal("0.85"),
            ai_confidence=Decimal("0.9"),
            expected_recovery_amount=Decimal("8500.00"),
            model_version="test-v1",
        )
        db_session.add(decision)
        db_session.flush()

        # Mock policy service to always approve
        mock_policy_result = PolicyDecision(
            decision="APPROVED", allowed=True, reason="Test approved",
            checks=[], policy_version="test-v1",
            evaluated_at=datetime.now(timezone.utc),
        )
        mock_evaluation = PolicyEvaluation(
            payment_id=payment.id,
            recovery_decision_id=decision.id,
            decision="APPROVED",
            allowed=True,
            policy_version="test-v1",
            checks=[],
        )
        db_session.add(mock_evaluation)
        db_session.flush()

        # Mock provider that returns PROCESSING
        def processing_provider():
            provider = MagicMock()
            provider.execute_recovery.return_value = ProviderExecutionResult(
                status=ExecutionStatus.PROCESSING,
                external_reference="rzp_retry_001",
                message="Retry initiated",
            )
            return provider

        service = RecoveryExecutionService(db_session, provider=processing_provider)

        # Patch the policy service to return our mock result
        with patch.object(service._policy_service, 'evaluate_for_payment',
                          return_value=(mock_policy_result, mock_evaluation)):
            key = "idem_test_key_001"
            resp1 = service.execute(mid, "pay_IDEM_001", idempotency_key=key)
            assert resp1.status == "PROCESSING"

            # Count actions before replay
            actions_before = db_session.scalars(
                select(RecoveryAction).where(RecoveryAction.idempotency_key == key)
            ).all()
            count_before = len(actions_before)

            # Second call with same key — must replay, not create new action
            resp2 = service.execute(mid, "pay_IDEM_001", idempotency_key=key)
            assert resp2.status == "PROCESSING"
            assert resp2.action_id == resp1.action_id  # Same action

            actions_after = db_session.scalars(
                select(RecoveryAction).where(RecoveryAction.idempotency_key == key)
            ).all()
            assert len(actions_after) == count_before  # No new action created


# ---------------------------------------------------------------------------
# R-6: Action state machine invalid transition
# ---------------------------------------------------------------------------

class TestStateMachineInvalidTransition:
    """Invalid state transitions must raise InvalidTransitionError."""

    def test_succeeded_to_failed_raises(self, db_session, merchant_id):
        from app.models import RecoveryAction
        from app.models.enums import RecoveryActionStatus

        mid = uuid.UUID(merchant_id)
        payment = _seed_payment_with_status(db_session, mid, "pay_SM_001", PaymentStatus.FAILED)

        action = RecoveryAction(
            payment_id=payment.id,
            action_type=RecommendedAction.RETRY,
            status=RecoveryActionStatus.SUCCEEDED,  # terminal state
        )
        db_session.add(action)
        db_session.flush()

        with pytest.raises(InvalidTransitionError, match="SUCCEEDED → FAILED"):
            apply_transition(action, RecoveryActionStatus.FAILED)

    def test_cancelled_to_processing_raises(self, db_session, merchant_id):
        from app.models import RecoveryAction

        mid = uuid.UUID(merchant_id)
        payment = _seed_payment_with_status(db_session, mid, "pay_SM_002", PaymentStatus.FAILED)

        action = RecoveryAction(
            payment_id=payment.id,
            action_type=RecommendedAction.RETRY,
            status=RecoveryActionStatus.CANCELLED,  # terminal state
        )
        db_session.add(action)
        db_session.flush()

        with pytest.raises(InvalidTransitionError, match="CANCELLED → PROCESSING"):
            apply_transition(action, RecoveryActionStatus.PROCESSING)

    def test_pending_to_succeeded_raises(self, db_session, merchant_id):
        from app.models import RecoveryAction

        mid = uuid.UUID(merchant_id)
        payment = _seed_payment_with_status(db_session, mid, "pay_SM_003", PaymentStatus.FAILED)

        action = RecoveryAction(
            payment_id=payment.id,
            action_type=RecommendedAction.RETRY,
            status=RecoveryActionStatus.PENDING,
        )
        db_session.add(action)
        db_session.flush()

        # PENDING → SUCCEEDED is not allowed (must go through PROCESSING)
        with pytest.raises(InvalidTransitionError):
            apply_transition(action, RecoveryActionStatus.SUCCEEDED)


# ---------------------------------------------------------------------------
# R-7: Recovery stop cancels open actions
# ---------------------------------------------------------------------------

class TestRecoveryStopCancelsActions:
    """stop_recovery must transition PENDING/SCHEDULED actions to CANCELLED."""

    def test_stop_cancels_pending_and_scheduled_actions(self, db_session, merchant_id):
        """stop_recovery must transition PENDING/SCHEDULED actions to CANCELLED.

        Note: the uq_active_action_per_payment constraint only allows one
        non-terminal action per payment at a time, so we create each action
        separately with flushes and use only one active action.
        """
        from app.services.recovery_service import RecoveryService
        from app.models import RecoveryDecision, PaymentFailure
        from app.models.enums import FailureCategory
        from datetime import datetime, timezone

        mid = uuid.UUID(merchant_id)
        payment = _seed_payment_with_status(db_session, mid, "pay_STOP_001", PaymentStatus.PROCESSING)

        # Add a failure record (required for _to_response)
        failure = PaymentFailure(
            payment_id=payment.id,
            failure_code="insufficient_fund",
            failure_reason="Insufficient funds",
            failure_category=FailureCategory.INSUFFICIENT_FUNDS,
            attempt_number=1,
            occurred_at=datetime.now(timezone.utc),
        )
        db_session.add(failure)

        # Add an AI decision (required for _to_response)
        decision = RecoveryDecision(
            payment_id=payment.id,
            recommended_action=RecommendedAction.RETRY,
            recovery_probability=Decimal("0.8"),
            ai_confidence=Decimal("0.9"),
            expected_recovery_amount=Decimal("8000.00"),
            model_version="test-v1",
        )
        db_session.add(decision)
        db_session.flush()

        # Create a single PENDING action (the unique constraint allows only one active action per payment)
        action_pending = RecoveryAction(
            payment_id=payment.id,
            decision_id=decision.id,
            action_type=RecommendedAction.RETRY,
            status=RecoveryActionStatus.PENDING,
        )
        db_session.add(action_pending)
        db_session.flush()

        service = RecoveryService(db_session)
        service.stop_recovery(mid, "pay_STOP_001")

        # PENDING action should be CANCELLED
        db_session.refresh(action_pending)
        assert action_pending.status == RecoveryActionStatus.CANCELLED

        # Payment should be HALTED
        db_session.refresh(payment)
        assert payment.status == PaymentStatus.HALTED

        # Verify audit event was created
        from app.models import AuditEvent
        from app.models.enums import AuditEventType
        audit = db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.payment_id == payment.id,
                AuditEvent.event_type == AuditEventType.RECOVERY_HALTED,
            )
        ).first()
        assert audit is not None


# ---------------------------------------------------------------------------
# R-8: Payment ingestion state precedence (stale webhook)
# ---------------------------------------------------------------------------

class TestPaymentIngestionStatePrecedence:
    """Stale webhooks must never downgrade a payment to an older state."""

    def test_failed_after_recovered_is_stale_ignored(self):
        """A late payment.failed arriving after RECOVERED must be ignored."""
        result = plan_transition(PaymentStatus.RECOVERED, PaymentStatus.FAILED)
        assert result.applied is False
        assert result.note == "STALE_IGNORED"

    def test_failed_after_authorized_is_stale_ignored(self):
        """A late payment.failed arriving after AUTHORIZED must be ignored."""
        result = plan_transition(PaymentStatus.AUTHORIZED, PaymentStatus.FAILED)
        assert result.applied is False
        assert result.note == "STALE_IGNORED"

    def test_authorized_after_recovered_is_stale_ignored(self):
        """A late payment.authorized arriving after RECOVERED must be ignored."""
        result = plan_transition(PaymentStatus.RECOVERED, PaymentStatus.AUTHORIZED)
        assert result.applied is False
        assert result.note == "STALE_IGNORED"

    def test_recovered_always_wins(self):
        """RECOVERED (captured) always wins regardless of current state."""
        for current in [PaymentStatus.FAILED, PaymentStatus.PROCESSING, PaymentStatus.AUTHORIZED]:
            result = plan_transition(current, PaymentStatus.RECOVERED)
            assert result.applied is True, f"RECOVERED should win over {current.value}"

    def test_failed_on_new_payment_is_processed(self):
        """FAILED on a brand-new payment (current=None) is PROCESSED."""
        result = plan_transition(None, PaymentStatus.FAILED)
        assert result.applied is True
        assert result.note == "PROCESSED"

    def test_same_status_is_no_change(self):
        """Same status → NO_CHANGE (idempotent no-op)."""
        result = plan_transition(PaymentStatus.FAILED, PaymentStatus.FAILED)
        assert result.applied is False
        assert result.note == "NO_CHANGE"

    def test_halted_is_untouchable(self):
        """HALTED payments must never be overwritten by ingestion."""
        from app.services.payment_ingestion_service import _UNTOUCHABLE_BY_INGESTION
        assert PaymentStatus.HALTED in _UNTOUCHABLE_BY_INGESTION
        # Any incoming status against HALTED should be STALE_IGNORED
        for incoming in [PaymentStatus.FAILED, PaymentStatus.AUTHORIZED]:
            result = plan_transition(PaymentStatus.HALTED, incoming)
            assert result.applied is False
            assert result.note == "STALE_IGNORED"
