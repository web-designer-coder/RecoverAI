"""Point 9 regression — recovery service merchant isolation.

Verifies that the recovery service correctly isolates data by merchant ID:
- list_recoveries only returns payments for the given merchant
- get_recovery_detail only returns details for the given merchant
- stop_recovery only affects actions for the given merchant

Preserves existing behavior and assumes repository methods are correctly scoped.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Customer, Merchant, PaymentFailure as Failure, Payment, RecoveryDecision
from app.models.enums import (
    FailureCategory,
    PaymentStatus,
    RecoveryActionStatus,
    RecommendedAction,
    PaymentMethod,
)
from app.services.recovery_service import RecoveryService


def test_list_recoveries_merchant_isolation(db_session):
    """Point 9A — list_recoveries returns only payments for the given merchant."""
    # Create two merchants
    from app.models import Merchant
    m1 = Merchant(name="Merchant 1", email="m1@example.com")
    m2 = Merchant(name="Merchant 2", email="m2@example.com")
    db_session.add_all([m1, m2])
    db_session.flush()

    # Create a customer and payment for each merchant
    cust1 = Customer(merchant_id=m1.id, external_customer_id="CUST_M1")
    cust2 = Customer(merchant_id=m2.id, external_customer_id="CUST_M2")
    db_session.add_all([cust1, cust2])
    db_session.flush()

    payment1 = Payment(
        merchant_id=m1.id,
        customer_id=cust1.id,
        external_payment_id="PAY_M1_001",
        amount=Decimal("1000.00"),
        currency="INR",
        method=PaymentMethod.CARD,
        status=PaymentStatus.FAILED,
        attempt_number=1,
    )
    payment2 = Payment(
        merchant_id=m2.id,
        customer_id=cust2.id,
        external_payment_id="PAY_M2_001",
        amount=Decimal("2000.00"),
        currency="INR",
        method=PaymentMethod.CARD,
        status=PaymentStatus.FAILED,
        attempt_number=1,
    )
    db_session.add_all([payment1, payment2])
    db_session.flush()

    # Add failures and decisions to make data non-empty
    failure1 = Failure(
        payment_id=payment1.id,
        occurred_at=datetime.now(timezone.utc),
        failure_reason="Insufficient funds",
        failure_code="insufficient_funds",
        failure_category=FailureCategory.INSUFFICIENT_FUNDS,
    )
    failure2 = Failure(
        payment_id=payment2.id,
        occurred_at=datetime.now(timezone.utc),
        failure_reason="Bank decline",
        failure_code="bank_decline",
        failure_category=FailureCategory.BANK_DECLINE,
    )
    db_session.add_all([failure1, failure2])

    decision1 = RecoveryDecision(
        payment_id=payment1.id,
        version_number=1,
        recovery_probability=0.7,
        ai_confidence=0.8,
        recommended_action=RecommendedAction.RETRY,
        expected_recovery_amount=Decimal("700.00"),
        optimal_recovery_at=datetime.now(timezone.utc),
        model_version="test_model",
        signals=[],
        explanation="Test decision",
        data_sufficiency="HIGH",
        optimal_window="WINDOW_1",
    )
    decision2 = RecoveryDecision(
        payment_id=payment2.id,
        version_number=1,
        recovery_probability=0.6,
        ai_confidence=0.7,
        recommended_action=RecommendedAction.RETRY,
        expected_recovery_amount=Decimal("1200.00"),
        optimal_recovery_at=datetime.now(timezone.utc),
        model_version="test_model",
        signals=[],
        explanation="Test decision",
        data_sufficiency="HIGH",
        optimal_window="WINDOW_1",
    )
    db_session.add_all([decision1, decision2])
    db_session.flush()

    service = RecoveryService(db_session)

    # Merchant 1 should see only payment1
    m1_list = service.list_recoveries(merchant_id=m1.id)
    assert len(m1_list) == 1
    assert m1_list[0].payment_id == "PAY_M1_001"
    assert m1_list[0].amount == 1000.0
    assert m1_list[0].currency == "INR"

    # Merchant 2 should see only payment2
    m2_list = service.list_recoveries(merchant_id=m2.id)
    assert len(m2_list) == 1
    assert m2_list[0].payment_id == "PAY_M2_001"
    assert m2_list[0].amount == 2000.0
    assert m2_list[0].currency == "INR"

    # Cross-check: ensure no leakage
    assert m1_list[0].payment_id != m2_list[0].payment_id
    assert m1_list[0].amount != m2_list[0].amount

    # Cleanup
    db_session.rollback()


def test_get_recovery_detail_merchant_isolation(db_session):
    """Point 9B — get_recovery_detail returns details only for the given merchant."""
    # Create two merchants
    from app.models import Merchant
    m1 = Merchant(name="Merchant 1", email="m1@example.com")
    m2 = Merchant(name="Merchant 2", email="m2@example.com")
    db_session.add_all([m1, m2])
    db_session.flush()

    # Create a customer and payment for each merchant
    cust1 = Customer(merchant_id=m1.id, external_customer_id="CUST_M1_DETAIL")
    cust2 = Customer(merchant_id=m2.id, external_customer_id="CUST_M2_DETAIL")
    db_session.add_all([cust1, cust2])
    db_session.flush()

    payment1 = Payment(
        merchant_id=m1.id,
        customer_id=cust1.id,
        external_payment_id="PAY_M1_DETAIL",
        amount=Decimal("1500.00"),
        currency="INR",
        method=PaymentMethod.UPI,
        status=PaymentStatus.FAILED,
        attempt_number=1,
    )
    payment2 = Payment(
        merchant_id=m2.id,
        customer_id=cust2.id,
        external_payment_id="PAY_M2_DETAIL",
        amount=Decimal("2500.00"),
        currency="INR",
        method=PaymentMethod.UPI,
        status=PaymentStatus.FAILED,
        attempt_number=1,
    )
    db_session.add_all([payment1, payment2])
    db_session.flush()

    # Add failures and decisions
    failure1 = Failure(
        payment_id=payment1.id,
        occurred_at=datetime.now(timezone.utc),
        failure_reason="Network error",
        failure_code="network_failure",
        failure_category=FailureCategory.NETWORK_FAILURE,
    )
    failure2 = Failure(
        payment_id=payment2.id,
        occurred_at=datetime.now(timezone.utc),
        failure_reason="Invalid CVV",
        failure_code="expired_card",
        failure_category=FailureCategory.EXPIRED_CARD,
    )
    db_session.add_all([failure1, failure2])

    decision1 = RecoveryDecision(
        payment_id=payment1.id,
        version_number=1,
        recovery_probability=0.85,
        ai_confidence=0.9,
        recommended_action=RecommendedAction.RETRY,
        expected_recovery_amount=Decimal("1275.00"),
        optimal_recovery_at=datetime.now(timezone.utc),
        model_version="test_model",
        signals=[],
        explanation="Test decision",
        data_sufficiency="HIGH",
        optimal_window="WINDOW_1",
    )
    decision2 = RecoveryDecision(
        payment_id=payment2.id,
        version_number=1,
        recovery_probability=0.5,
        ai_confidence=0.6,
        recommended_action=RecommendedAction.RETRY,
        expected_recovery_amount=Decimal("1250.00"),
        optimal_recovery_at=datetime.now(timezone.utc),
        model_version="test_model",
        signals=[],
        explanation="Test decision",
        data_sufficiency="HIGH",
        optimal_window="WINDOW_1",
    )
    db_session.add_all([decision1, decision2])
    db_session.flush()

    service = RecoveryService(db_session)

    # Merchant 1 requesting their own payment should succeed
    detail1 = service.get_recovery_detail(merchant_id=m1.id, external_payment_id="PAY_M1_DETAIL")
    assert detail1 is not None
    assert detail1.payment_id == "PAY_M1_DETAIL"
    assert detail1.amount == 1500.0
    assert detail1.currency == "INR"
    assert detail1.recovery_probability == 0.85
    assert detail1.confidence == 0.9

    # Merchant 2 requesting merchant 1's payment should return None (or raise?)
    # The service uses require_payment which raises payment_not_found if not found for that merchant.
    # We expect it to raise an exception because the payment exists but not for merchant 2.
    with pytest.raises(Exception):  # payment_not_found
        service.get_recovery_detail(merchant_id=m2.id, external_payment_id="PAY_M1_DETAIL")

    # Merchant 2 requesting their own payment should succeed
    detail2 = service.get_recovery_detail(merchant_id=m2.id, external_payment_id="PAY_M2_DETAIL")
    assert detail2 is not None
    assert detail2.payment_id == "PAY_M2_DETAIL"
    assert detail2.amount == 2500.0
    assert detail2.currency == "INR"
    assert detail2.recovery_probability == 0.5
    assert detail2.confidence == 0.6

    # Cleanup
    db_session.rollback()


def test_stop_recovery_merchant_isolation(db_session):
    """Point 9C — stop_recovery only halts actions for the given merchant."""
    # Create two merchants
    from app.models import Merchant
    m1 = Merchant(name="Merchant 1", email="m1@example.com")
    m2 = Merchant(name="Merchant 2", email="m2@example.com")
    db_session.add_all([m1, m2])
    db_session.flush()

    # Create a customer and payment for each merchant
    cust1 = Customer(merchant_id=m1.id, external_customer_id="CUST_M1_STOP")
    cust2 = Customer(merchant_id=m2.id, external_customer_id="CUST_M2_STOP")
    db_session.add_all([cust1, cust2])
    db_session.flush()

    payment1 = Payment(
        merchant_id=m1.id,
        customer_id=cust1.id,
        external_payment_id="PAY_M1_STOP",
        amount=Decimal("3000.00"),
        currency="INR",
        method=PaymentMethod.NET_BANKING,
        status=PaymentStatus.FAILED,
        attempt_number=1,
    )
    payment2 = Payment(
        merchant_id=m2.id,
        customer_id=cust2.id,
        external_payment_id="PAY_M2_STOP",
        amount=Decimal("4000.00"),
        currency="INR",
        method=PaymentMethod.NET_BANKING,
        status=PaymentStatus.FAILED,
        attempt_number=1,
    )
    db_session.add_all([payment1, payment2])
    db_session.flush()

    # Add failures (required for stop_recovery to not fail on missing failure)
    failure1 = Failure(
        payment_id=payment1.id,
        occurred_at=datetime.now(timezone.utc),
        failure_reason="Gateway timeout",
        failure_code="bank_decline",
        failure_category=FailureCategory.BANK_DECLINE,
    )
    failure2 = Failure(
        payment_id=payment2.id,
        occurred_at=datetime.now(timezone.utc),
        failure_reason="Expired card",
        failure_code="expired_card",
        failure_category=FailureCategory.EXPIRED_CARD,
    )
    db_session.add_all([failure1, failure2])
    db_session.flush()

    # Create a pending recovery action for each payment
    from app.models import RecoveryAction
    from app.models.enums import RecoveryActionStatus

    action1 = RecoveryAction(
        payment_id=payment1.id,
        action_type=RecommendedAction.RETRY,
        status=RecoveryActionStatus.PENDING,
    )
    action2 = RecoveryAction(
        payment_id=payment2.id,
        action_type=RecommendedAction.RETRY,
        status=RecoveryActionStatus.PENDING,
    )
    db_session.add_all([action1, action2])
    db_session.flush()

    service = RecoveryService(db_session)

    # Merchant 1 stops their own recovery
    resp1 = service.stop_recovery(merchant_id=m1.id, external_payment_id="PAY_M1_STOP")
    assert resp1 is not None
    assert resp1.payment_id == "PAY_M1_STOP"
    assert resp1.status == PaymentStatus.HALTED.value

    # Verify action1 is cancelled but action2 remains pending
    from sqlalchemy.orm import Session
    # Re-fetch actions to avoid session state issues
    actions_after = db_session.scalars(
        select(RecoveryAction).where(RecoveryAction.payment_id.in_([payment1.id, payment2.id]))
    ).all()
    action1_after = next(a for a in actions_after if a.payment_id == payment1.id)
    action2_after = next(a for a in actions_after if a.payment_id == payment2.id)
    assert action1_after.status == RecoveryActionStatus.CANCELLED
    assert action2_after.status == RecoveryActionStatus.PENDING  # untouched

    # Merchant 2 stops their own recovery
    resp2 = service.stop_recovery(merchant_id=m2.id, external_payment_id="PAY_M2_STOP")
    assert resp2 is not None
    assert resp2.payment_id == "PAY_M2_STOP"
    assert resp2.status == PaymentStatus.HALTED.value

    # Verify action2 is now cancelled
    actions_after2 = db_session.scalars(
        select(RecoveryAction).where(RecoveryAction.payment_id.in_([payment1.id, payment2.id]))
    ).all()
    action1_after2 = next(a for a in actions_after2 if a.payment_id == payment1.id)
    action2_after2 = next(a for a in actions_after2 if a.payment_id == payment2.id)
    assert action1_after2.status == RecoveryActionStatus.CANCELLED  # still cancelled
    assert action2_after2.status == RecoveryActionStatus.CANCELLED  # now cancelled

    # Cleanup
    db_session.rollback()