"""Phase 5 execution tests — safe execution, idempotency, state machine, audit.

Provider calls are always mocked via a FakeProvider injected through
``RecoveryExecutionService(db_session, provider=lambda: fake)``; no live
Razorpay credentials are ever required.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AuditEvent, Customer, Payment, PaymentFailure, RecoveryAction, RecoveryDecision
from app.models.enums import (
    ActorType,
    AuditEventType,
    FailureCategory,
    PaymentMethod,
    PaymentStatus,
    RecommendedAction,
    RecoveryActionStatus,
)
from app.schemas.policy_schemas import PolicyUpsertRequest
from app.utils.tokens import create_token
from app.services.action_state_machine import InvalidTransitionError, apply_transition
from app.services.providers.payment_provider import (
    ExecutionStatus,
    ProviderExecutionResult,
    RazorpayPaymentProvider,
)
from app.services.providers.razorpay_client import RazorpayNotConfigured
from app.services.recovery_execution_service import RecoveryExecutionService
from app.services.policy_service import PolicyService as PolicyStorageService
from app.services.recovery_service import RecoveryService

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


# --- fixtures / helpers ------------------------------------------------------


class FakeProvider:
    """Records execute_recovery calls; returns a canned result or raises."""

    def __init__(self, result=None, exc=None):
        self.calls: list[dict] = []
        self._result = result
        self._exc = exc

    def get_payment(self, provider_payment_id):
        return {}

    def execute_recovery(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._result


def processing_result(ref="plink_FAKE123"):
    return ProviderExecutionResult(
        status=ExecutionStatus.PROCESSING, message="link created",
        external_reference=ref,
    )


def relaxed_policy(db_session, merchant_id, **overrides) -> None:
    """PUT-equivalent policy without approval/high-value escalation gates."""
    storage = PolicyStorageService(db_session)
    cur = storage.get_policies(merchant_id)
    fields = dict(
        maximum_retries=cur.maximum_retries,
        recovery_window_days=cur.recovery_window_days,
        minimum_ai_confidence=Decimal(str(cur.minimum_ai_confidence)),
        high_value_threshold=Decimal(str(cur.high_value_threshold)),
        prevent_duplicate_recovery=True,
        require_policy_approval=False,
        maintain_audit_log=True,
        escalate_high_value=False,
        failure_rules=dict(cur.failure_rules),
    )
    fields.update(overrides)
    storage.upsert_policies(merchant_id, PolicyUpsertRequest(**fields))


def failed_payment(db_session, merchant_id, ext_id, amount="8499.00") -> Payment:
    m_uuid = uuid.UUID(merchant_id)
    customer = db_session.scalars(
        select(Customer).where(Customer.merchant_id == m_uuid)
    ).first()
    payment = Payment(
        merchant_id=m_uuid, customer_id=customer.id, external_payment_id=ext_id,
        amount=Decimal(amount), currency="INR", method=PaymentMethod.UPI,
        status=PaymentStatus.FAILED, attempt_number=1,
    )
    db_session.add(payment)
    db_session.flush()
    db_session.add(PaymentFailure(
        payment_id=payment.id, failure_category=FailureCategory.INSUFFICIENT_FUNDS,
        failure_code="insufficient_fund", failure_reason="insufficient balance",
        attempt_number=1, occurred_at=NOW - timedelta(hours=1),
    ))
    db_session.flush()
    return payment


def ai_decision(db_session, payment, *, action=RecommendedAction.RETRY,
                optimal_at=None, confidence="0.9000") -> RecoveryDecision:
    decision = RecoveryDecision(
        payment_id=payment.id, diagnosis="Insufficient funds",
        ai_confidence=Decimal(confidence), recovery_probability=Decimal("0.7000"),
        recommended_action=action,
        expected_recovery_amount=(payment.amount * Decimal("0.70")).quantize(Decimal("0.01")),
        optimal_recovery_at=optimal_at or NOW - timedelta(minutes=5),  # due NOW by default
        optimal_window="NOW", model_version="recoverai-v1", version_number=1,
        signals=[{"name": "category_history", "value": "positive"}],
        explanation="RecoverAI recommends RETRY.", data_sufficiency="LOW",
    )
    db_session.add(decision)
    db_session.flush()
    return decision


def audits(db_session, payment_uuid) -> list[AuditEvent]:
    return db_session.scalars(
        select(AuditEvent).where(AuditEvent.payment_id == payment_uuid)
    ).all()


# --- state machine (pure) -----------------------------------------------------


def test_invalid_transition_fails_safely():
    done = RecoveryAction(action_type=RecommendedAction.RETRY,
                          status=RecoveryActionStatus.SUCCEEDED)
    with pytest.raises(InvalidTransitionError):
        apply_transition(done, RecoveryActionStatus.PROCESSING)


def test_processing_cannot_restart():
    running = RecoveryAction(action_type=RecommendedAction.RETRY,
                             status=RecoveryActionStatus.PROCESSING)
    with pytest.raises(InvalidTransitionError):
        apply_transition(running, RecoveryActionStatus.PENDING)


def test_terminal_transition_stamps_completed_at():
    action = RecoveryAction(action_type=RecommendedAction.RETRY,
                            status=RecoveryActionStatus.PROCESSING)
    apply_transition(action, RecoveryActionStatus.SUCCEEDED)
    assert action.status is RecoveryActionStatus.SUCCEEDED
    assert action.completed_at is not None


def test_processing_stamps_started_at():
    action = RecoveryAction(action_type=RecommendedAction.RETRY,
                            status=RecoveryActionStatus.APPROVED)
    apply_transition(action, RecoveryActionStatus.PROCESSING)
    assert action.started_at is not None
    assert action.completed_at is None


# --- provider abstraction ------------------------------------------------------


class _StubClient:
    def __init__(self):
        self.link_calls = []

    def create_payment_link(self, *, amount_minor_units, currency, reference_id, description):
        self.link_calls.append(amount_minor_units)
        return {"id": "plink_stub", "short_url": "https://rzp.io/i/stub"}

    def close(self):
        pass  # no-op for test stubs


def test_non_retry_actions_never_fabricate_provider_ops():
    client = _StubClient()
    result = RazorpayPaymentProvider(client).execute_recovery(
        action_type=RecommendedAction.CUSTOMER_NOTIFICATION,
        amount=Decimal("100.00"), currency="INR", reference_id="PAY_X",
    )
    assert result.status is ExecutionStatus.CUSTOMER_ACTION_REQUIRED
    assert client.link_calls == []  # nothing was sent to Razorpay


def test_retry_creates_payment_link_with_paise_conversion():
    client = _StubClient()
    result = RazorpayPaymentProvider(client).execute_recovery(
        action_type=RecommendedAction.RETRY,
        amount=Decimal("8499.00"), currency="INR", reference_id="PAY_X",
    )
    # ₹8499.00 → 849900 paise exactly (single conversion point).
    assert client.link_calls == [849900]
    assert result.status is ExecutionStatus.PROCESSING
    assert result.external_reference == "plink_stub"


# --- execution service (DB-backed) ---------------------------------------------


def test_approved_execution_creates_action_and_audits(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_OK")
    decision = ai_decision(db_session, payment)
    fake = FakeProvider(result=processing_result())
    service = RecoveryExecutionService(db_session, provider=lambda: fake)

    response = service.execute(uuid.UUID(merchant_id), "PAY_EXEC_OK")

    assert response.decision == "APPROVED"
    assert response.status == "PROCESSING"
    assert response.action == "RETRY"
    assert response.external_reference == "plink_FAKE123"
    assert len(fake.calls) == 1

    action = db_session.get(RecoveryAction, uuid.UUID(response.action_id))
    assert action.status is RecoveryActionStatus.PROCESSING
    assert action.policy_evaluation_id is not None   # traceable to authorizing evaluation
    assert action.started_at is not None
    events = {e.event_type for e in audits(db_session, payment.id)}
    assert AuditEventType.RECOVERY_PROCESSING in events
    assert AuditEventType.RECOVERY_EXECUTED in events


def test_blocked_execution_never_touches_provider(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_BLOCKED")
    ai_decision(db_session, payment)
    payment.status = PaymentStatus.HALTED
    db_session.flush()

    fake = FakeProvider(result=processing_result())
    factory_calls = []
    def counting_factory():
        factory_calls.append(1)
        return fake

    response = RecoveryExecutionService(db_session, provider=counting_factory).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_BLOCKED"
    )
    assert response.decision == "BLOCKED"
    assert any(c.check_name == "payment_state" and c.status == "FAIL"
               for c in response.checks)
    assert factory_calls == [] and fake.calls == []
    actions = db_session.scalars(select(RecoveryAction).where(
        RecoveryAction.payment_id == payment.id)).all()
    assert actions == []  # no action row for blocked executions


def test_escalated_high_value_never_touches_provider(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id, escalate_high_value=True)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_HV", amount="99000.00")
    ai_decision(db_session, payment)

    fake = FakeProvider(result=processing_result())
    response = RecoveryExecutionService(db_session, provider=lambda: fake).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_HV"
    )
    assert response.decision == "ESCALATED"
    hv = next(c for c in response.checks if c.check_name == "high_value")
    assert hv.metadata["requirement"] == "HUMAN_APPROVAL_REQUIRED"
    assert fake.calls == []


def test_execute_without_decision_raises_no_recovery_decision(db_session, merchant_id):
    from app.utils.errors import AppError

    relaxed_policy(db_session, merchant_id)
    failed_payment(db_session, merchant_id, "PAY_EXEC_NODEC")
    with pytest.raises(AppError) as exc_info:
        RecoveryExecutionService(db_session, provider=lambda: FakeProvider()).execute(
            uuid.UUID(merchant_id), "PAY_EXEC_NODEC"
        )
    assert exc_info.value.code == "NO_RECOVERY_DECISION"
    assert exc_info.value.status_code == 409


def test_duplicate_protection_blocks_second_execution(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_DUP")
    ai_decision(db_session, payment)
    db_session.add(RecoveryAction(payment_id=payment.id,
                                  action_type=RecommendedAction.RETRY,
                                  status=RecoveryActionStatus.SCHEDULED))
    db_session.flush()

    response = RecoveryExecutionService(db_session, provider=lambda: FakeProvider()).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_DUP"
    )
    dup = next(c for c in response.checks if c.check_name == "duplicate_recovery")
    assert dup.status == "FAIL"


def test_db_constraint_prevents_two_active_actions(db_session, merchant_id):
    """The partial unique index holds even if application checks are bypassed."""
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_UQ")
    db_session.add(RecoveryAction(payment_id=payment.id,
                                  action_type=RecommendedAction.RETRY,
                                  status=RecoveryActionStatus.SCHEDULED))
    db_session.add(RecoveryAction(payment_id=payment.id,
                                  action_type=RecommendedAction.RETRY,
                                  status=RecoveryActionStatus.PROCESSING))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_idempotent_replay_returns_existing_action(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_IDEM")
    ai_decision(db_session, payment)
    fake = FakeProvider(result=processing_result())
    service = RecoveryExecutionService(db_session, provider=lambda: fake)

    first = service.execute(uuid.UUID(merchant_id), "PAY_EXEC_IDEM", idempotency_key="op-1")
    second = service.execute(uuid.UUID(merchant_id), "PAY_EXEC_IDEM", idempotency_key="op-1")

    assert first.action_id == second.action_id
    assert len(fake.calls) == 1  # provider hit exactly once
    rows = db_session.scalars(select(RecoveryAction).where(
        RecoveryAction.payment_id == payment.id)).all()
    assert len(rows) == 1
    assert "idempotent replay" in second.message


def test_scheduled_path_defers_without_provider_call(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_SCHED")
    future = NOW + timedelta(hours=12)
    ai_decision(db_session, payment, optimal_at=future)
    fake = FakeProvider(result=processing_result())

    response = RecoveryExecutionService(db_session, provider=lambda: fake).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_SCHED", now=NOW
    )
    assert response.status == "SCHEDULED"
    assert fake.calls == []  # nothing executes before the window opens
    action = db_session.get(RecoveryAction, uuid.UUID(response.action_id))
    assert action.status is RecoveryActionStatus.SCHEDULED
    assert action.scheduled_at == future
    assert payment.next_action_at == future
    assert AuditEventType.RECOVERY_SCHEDULED in {e.event_type for e in audits(db_session, payment.id)}


def test_payment_not_recovered_before_confirmation(db_session, merchant_id):
    """Link creation is PROCESSING only — RECOVERED waits for the webhook."""
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_PEND")
    ai_decision(db_session, payment)
    fake = FakeProvider(result=processing_result())

    response = RecoveryExecutionService(db_session, provider=lambda: fake).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_PEND"
    )
    assert response.status == "PROCESSING"
    db_session.expire(payment)
    assert payment.status is not PaymentStatus.RECOVERED
    assert payment.status is PaymentStatus.PROCESSING
    assert AuditEventType.PAYMENT_RECOVERED not in {e.event_type for e in audits(db_session, payment.id)}


def test_webhook_confirmed_success_marks_recovered(db_session, merchant_id):
    """Only a provider-confirmed final success moves money state."""
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_DONE")
    ai_decision(db_session, payment)
    confirmed = ProviderExecutionResult(status=ExecutionStatus.SUCCEEDED,
                                        message="captured", external_reference="pay_CONFIRMED")
    response = RecoveryExecutionService(db_session, provider=lambda: FakeProvider(confirmed)).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_DONE"
    )
    assert response.status == "SUCCEEDED"
    db_session.expire(payment)
    assert payment.status is PaymentStatus.RECOVERED
    action = db_session.get(RecoveryAction, uuid.UUID(response.action_id))
    assert action.status is RecoveryActionStatus.SUCCEEDED
    assert AuditEventType.PAYMENT_RECOVERED in {e.event_type for e in audits(db_session, payment.id)}


@pytest.mark.parametrize("provider_exc,expected_code", [
    (RazorpayNotConfigured(), "PROVIDER_UNAVAILABLE"),   # raised by factory
])
def test_provider_unavailable_fails_safely(db_session, merchant_id, provider_exc, expected_code):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_NOKEYS")
    ai_decision(db_session, payment)

    def broken_factory():
        raise provider_exc

    response = RecoveryExecutionService(db_session, provider=broken_factory).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_NOKEYS"
    )
    assert response.status == "FAILED"
    assert "Provider unavailable" in response.reason
    db_session.expire(payment)
    action = db_session.get(RecoveryAction, uuid.UUID(response.action_id))
    assert action.status is RecoveryActionStatus.FAILED
    assert expected_code in action.failure_reason          # code recorded on the action
    assert payment.status is PaymentStatus.FAILED          # never a manufactured success
    failed_events = [e for e in audits(db_session, payment.id)
                     if e.event_type is AuditEventType.RECOVERY_FAILED]
    assert failed_events and failed_events[-1].meta["provider_code"] == expected_code


def test_provider_exception_maps_to_failed_action(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_TIMEOUT")
    ai_decision(db_session, payment)
    boom = type("RazorpayTimeout", (Exception,), {})("timed out")
    boom.code = "RAZORPAY_TIMEOUT"
    boom.message = "gateway timed out"

    response = RecoveryExecutionService(db_session, provider=lambda: FakeProvider(exc=boom)).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_TIMEOUT"
    )
    assert response.status == "FAILED"
    db_session.expire(payment)
    action = db_session.get(RecoveryAction, uuid.UUID(response.action_id))
    assert action.status is RecoveryActionStatus.FAILED
    assert "RAZORPAY_TIMEOUT" in action.failure_reason
    assert payment.status is PaymentStatus.FAILED


def test_customer_notification_records_action_required(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_NOTIFY")
    ai_decision(db_session, payment, action=RecommendedAction.CUSTOMER_NOTIFICATION)
    fake = FakeProvider(result=processing_result())

    response = RecoveryExecutionService(db_session, provider=lambda: fake).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_NOTIFY"
    )
    assert response.status == "CUSTOMER_ACTION_REQUIRED"
    assert fake.calls == []                       # notification layer never calls Razorpay
    db_session.expire(payment)
    assert payment.status is PaymentStatus.NEEDS_ACTION
    action = db_session.get(RecoveryAction, uuid.UUID(response.action_id))
    assert action.status is RecoveryActionStatus.CUSTOMER_ACTION_REQUIRED


def test_stop_is_safe_and_preserves_history(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_STOP")
    ai_decision(db_session, payment)
    service = RecoveryExecutionService(db_session, provider=lambda: FakeProvider(processing_result()))
    service.execute(uuid.UUID(merchant_id), "PAY_EXEC_STOP")   # PROCESSING action exists

    stopped = RecoveryService(db_session).stop_recovery(uuid.UUID(merchant_id), "PAY_EXEC_STOP")

    assert stopped.status == "HALTED"
    # A PROCESSING action must NOT be silently rewritten to cancelled…
    action = db_session.scalars(select(RecoveryAction).where(
        RecoveryAction.payment_id == payment.id)).one()
    assert action.status is RecoveryActionStatus.PROCESSING
    # …and no audit history may be deleted.
    events_before = len(audits(db_session, payment.id))
    assert events_before >= 3   # policy + processing + executed chain intact


def test_stop_cancels_open_scheduled_action(db_session, merchant_id):
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_EXEC_STOPSCHED")
    ai_decision(db_session, payment, optimal_at=NOW + timedelta(days=1))
    RecoveryExecutionService(db_session, provider=lambda: FakeProvider()).execute(
        uuid.UUID(merchant_id), "PAY_EXEC_STOPSCHED", now=NOW
    )

    RecoveryService(db_session).stop_recovery(uuid.UUID(merchant_id), "PAY_EXEC_STOPSCHED")

    action = db_session.scalars(select(RecoveryAction).where(
        RecoveryAction.payment_id == payment.id)).one()
    assert action.status is RecoveryActionStatus.CANCELLED
    assert action.completed_at is not None


# --- E2E over HTTP (§37): analyze → validate-policy → execute -------------------


def test_e2e_http_flow_approve_validate_execute(client, db_session, merchant_id):
    from app.repositories import MerchantRepository
    relaxed_policy(db_session, merchant_id)
    payment = failed_payment(db_session, merchant_id, "PAY_E2E_FLOW")
    future = NOW + timedelta(hours=6)
    ai_decision(db_session, payment, optimal_at=future)
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"

    analyzed = client.post("/api/recoveries/PAY_E2E_FLOW/analyze")
    assert analyzed.status_code == 200
    new_decision_id = analyzed.json()["decision_id"]

    validated = client.post("/api/recoveries/PAY_E2E_FLOW/validate-policy")
    assert validated.status_code == 200
    body = validated.json()
    assert body["decision"] == "APPROVED"
    assert body["allowed"] is True
    assert body["policy_evaluation_id"]

    # No live credentials configured in tests → default provider factory fails
    # fast and execution fails safely instead of pretending.
    executed = client.post("/api/recoveries/PAY_E2E_FLOW/execute")
    assert executed.status_code == 200
    exec_body = executed.json()
    assert exec_body["decision"] == "APPROVED"
    # optimal_recovery_at of the fresh analysis lies ahead → SCHEDULED, no call.
    assert exec_body["status"] in {"SCHEDULED"}
    assert exec_body["policy_version"].startswith("v")

    trail = client.get("/api/recoveries/PAY_E2E_FLOW/audit")
    assert trail.status_code == 200
    types = [e["event_type"] for e in trail.json()]
    assert "POLICY_CHECK" in types
    assert "RECOVERY_SCHEDULED" in types
    assert new_decision_id  # analysis appended a fresh current version
