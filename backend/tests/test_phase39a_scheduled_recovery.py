"""Phase 39A-1 — Scheduled recovery contract tests.

The SCHEDULED state is an execution-state boundary; an external scheduler
calls RecoveryRepository.due_scheduled_actions() to retrieve due actions,
then calls RecoveryExecutionService.execute() with the action's
idempotency_key to perform a safe, idempotent replay.

These tests prove:
- due_scheduled_actions returns only SCHEDULED actions for the merchant
- non-due actions are not returned
- cross-merchant access is rejected
- repeat calls are safe (no duplicate work)
- execution through the existing execute() service is idempotent
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Customer, Merchant, PaymentFailure as Failure, Payment, RecoveryAction
from app.models.enums import (
    FailureCategory,
    PaymentStatus,
    PaymentMethod,
    RecoveryActionStatus,
    RecommendedAction,
)
from app.repositories import RecoveryRepository
from app.services.recovery_execution_service import RecoveryExecutionService


@pytest.fixture
def two_merchants(db_session):
    m1 = Merchant(name="M1", email="m1@x.com")
    m2 = Merchant(name="M2", email="m2@x.com")
    db_session.add_all([m1, m2])
    db_session.flush()
    return m1, m2


def _make_payment(db_session, merchant, amount="1000.00", ext="PAY_X"):
    cust = Customer(merchant_id=merchant.id, external_customer_id=f"CUST_{ext}")
    db_session.add(cust)
    db_session.flush()
    p = Payment(
        merchant_id=merchant.id,
        customer_id=cust.id,
        external_payment_id=ext,
        amount=Decimal(amount),
        currency="INR",
        method=PaymentMethod.CARD,
        status=PaymentStatus.FAILED,
        attempt_number=1,
    )
    db_session.add(p)
    db_session.flush()
    fail = Failure(
        payment_id=p.id,
        occurred_at=datetime.now(timezone.utc),
        failure_reason="Insufficient funds",
        failure_code="insufficient_funds",
        failure_category=FailureCategory.INSUFFICIENT_FUNDS,
    )
    db_session.add(fail)
    db_session.flush()
    return p


def test_scheduled_not_due_not_returned(db_session, two_merchants):
    m1, _ = two_merchants
    p = _make_payment(db_session, m1)
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    action = RecoveryAction(
        payment_id=p.id,
        action_type=RecommendedAction.RETRY,
        status=RecoveryActionStatus.SCHEDULED,
        scheduled_at=future,
    )
    db_session.add(action)
    db_session.flush()

    repo = RecoveryRepository(db_session)
    due = repo.due_scheduled_actions(m1.id)
    assert due == []


def test_scheduled_due_is_returned(db_session, two_merchants):
    m1, _ = two_merchants
    p = _make_payment(db_session, m1)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    action = RecoveryAction(
        payment_id=p.id,
        action_type=RecommendedAction.RETRY,
        status=RecoveryActionStatus.SCHEDULED,
        scheduled_at=past,
    )
    db_session.add(action)
    db_session.flush()

    repo = RecoveryRepository(db_session)
    due = repo.due_scheduled_actions(m1.id)
    assert len(due) == 1
    assert due[0].id == action.id


def test_scheduled_wrong_merchant_not_returned(db_session, two_merchants):
    m1, m2 = two_merchants
    p = _make_payment(db_session, m1, ext="PAY_M1")
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    action = RecoveryAction(
        payment_id=p.id,
        action_type=RecommendedAction.RETRY,
        status=RecoveryActionStatus.SCHEDULED,
        scheduled_at=past,
    )
    db_session.add(action)
    db_session.flush()

    repo = RecoveryRepository(db_session)
    due_for_m2 = repo.due_scheduled_actions(m2.id)
    assert due_for_m2 == []
    due_for_m1 = repo.due_scheduled_actions(m1.id)
    assert len(due_for_m1) == 1


def test_scheduled_execution_is_idempotent(db_session, two_merchants):
    """execute() with an existing idempotency_key must not create a duplicate action.

    Pre-creates a SCHEDULED action with an idempotency_key, then calls execute()
    with the same key. The service must find the existing action and return
    it without creating a new one.
    """
    from datetime import datetime as dt

    m1, _ = two_merchants
    p = _make_payment(db_session, m1, ext="PAY_IDEMP2")

    ik = "PAY_IDEMP2:sched-test:RETRY"

    # Pre-create a RecoveryDecision so policy evaluation can proceed (execute
    # requires a current decision; this reflects the real contract, not a mock).
    from app.models import RecoveryDecision
    decision = RecoveryDecision(
        payment_id=p.id,
        diagnosis="Test",
        recommended_action=RecommendedAction.RETRY,
        version_number=1,
    )
    db_session.add(decision)
    db_session.flush()

    # Pre-create a SCHEDULED action with the idempotency_key
    action = RecoveryAction(
        payment_id=p.id,
        decision_id=decision.id,
        action_type=RecommendedAction.RETRY,
        status=RecoveryActionStatus.SCHEDULED,
        scheduled_at=dt.now(timezone.utc) - timedelta(minutes=1),
        idempotency_key=ik,
    )
    db_session.add(action)
    db_session.flush()

    # No-op provider (must not be called)
    call_count = {"n": 0}
    class StubProvider:
        def execute_recovery(self, **kwargs):
            call_count["n"] += 1
            return None
    svc = RecoveryExecutionService(db_session, provider=lambda: StubProvider())

    # Call execute() with the same idempotency_key
    r = svc.execute(m1.id, "PAY_IDEMP2", idempotency_key=ik)
    # Idempotent replay returns the recorded state without a new provider call
    assert r.action_id == str(action.id), (
        f"Replay returned different action_id; expected {action.id} got {r.action_id}"
    )
    assert call_count["n"] == 0, (
        f"Provider was called {call_count['n']} times during replay; expected 0"
    )

    # Verify still only one action exists for this idempotency_key
    actions = db_session.scalars(
        select(RecoveryAction).where(RecoveryAction.idempotency_key == ik)
    ).all()
    assert len(actions) == 1, f"Expected 1 action, found {len(actions)}"


def test_scheduled_action_invalid_state_cannot_execute_via_replay(db_session, two_merchants):
    """An action in a terminal state (e.g. CANCELLED) must not be re-executed via the replay path."""
    m1, _ = two_merchants
    p = _make_payment(db_session, m1, ext="PAY_CANCEL")
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    action = RecoveryAction(
        payment_id=p.id,
        action_type=RecommendedAction.RETRY,
        status=RecoveryActionStatus.CANCELLED,
        scheduled_at=past,
        idempotency_key="PAY_CANCEL:RETRY",
    )
    db_session.add(action)
    db_session.flush()

    repo = RecoveryRepository(db_session)
    due = repo.due_scheduled_actions(m1.id)
    assert due == [], "CANCELLED actions must not be returned by due_scheduled_actions()"
