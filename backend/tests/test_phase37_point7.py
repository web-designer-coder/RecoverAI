"""Point 7 regression — idempotency / data-integrity constraints.

Verifies DB-level uniqueness enforced by ph37_p7_data_integrity migration:
- recovery_actions.idempotency_key (nullable unique)
- recovery_decisions (payment_id, version_number) composite unique

Preserves merchant isolation and existing valid operations.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import Base
from app.models import Payment, RecoveryAction, RecoveryDecision, Merchant, Customer, Customer
from app.models.enums import RecoveryActionStatus, RecommendedAction


def _session():
    url = get_settings().database_url
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    return Session()


def test_idempotency_key_unique_non_null():
    """Point 7A — duplicate idempotency_key rejected at DB level."""
    session = _session()
    try:
        # Use the seeded merchant to create a clean payment for this test.
        merchant = session.query(Merchant).filter(Merchant.name == "RecoverAI Demo Merchant").one()
        # Create a customer for the merchant.
        customer = Customer(
            merchant_id=merchant.id,
            external_customer_id=f"idempotency-cust-{merchant.id}",
            name=f"Customer for idempotency test",
            email=f"idempotency_{merchant.id}@test.in",
        )
        session.add(customer)
        session.flush()
        # Create a payment that is guaranteed to have no existing RecoveryActions.
        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            external_payment_id=f"idempotency-test-{merchant.id}",
            amount=100,
            currency="INR",
            method="CARD",
            status="FAILED",
            attempt_number=1,
        )
        session.add(payment)
        session.flush()
        # First insert with a deterministic test key tied to the new payment
        a1 = RecoveryAction(
            payment=payment,
            action_type=RecommendedAction.RETRY,
            status=RecoveryActionStatus.PENDING,
            idempotency_key="P7IDEMP001",
        )
        session.add(a1)
        session.commit()
        # Second insert with same key — must raise IntegrityError
        a2 = RecoveryAction(
            payment=payment,
            action_type=RecommendedAction.RETRY,
            status=RecoveryActionStatus.PENDING,
            idempotency_key="P7IDEMP001",
        )
        session.add(a2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.rollback()


def test_recovery_decision_version_unique_composite():
    """Point 7B — (payment_id, version_number) duplicate rejected."""
    session = _session()
    try:
        # Use the seeded merchant to create a clean payment for this test.
        merchant = session.query(Merchant).filter(Merchant.name == "RecoverAI Demo Merchant").one()
        # Create a customer for the merchant.
        customer = Customer(
            merchant_id=merchant.id,
            external_customer_id=f"version-cust-{merchant.id}",
            name=f"Customer for version test",
            email=f"version_{merchant.id}@test.in",
        )
        session.add(customer)
        session.flush()
        # Create a payment that is guaranteed to have no existing RecoveryDecisions.
        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            external_payment_id=f"version-test-{merchant.id}",
            amount=100,
            currency="INR",
            method="CARD",
            status="FAILED",
            attempt_number=1,
        )
        session.add(payment)
        session.flush()
        # Use a version number that is guaranteed to be unused for this payment.
        ver = 9999
        d1 = RecoveryDecision(payment=payment, version_number=ver)
        session.add(d1)
        session.commit()
        d2 = RecoveryDecision(payment=payment, version_number=ver)
        session.add(d2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.rollback()


def test_active_action_per_payment_preserved():
    """Point 7 — existing uq_active_action_per_payment remains intact."""
    session = _session()
    try:
        # Find a payment that already has a PENDING action (to test the constraint)
        merchant = session.query(Merchant).filter(Merchant.name == "RecoverAI Demo Merchant").one()
        payment = session.query(Payment).filter(Payment.merchant_id == merchant.id).first()
        if payment is None:
            pytest.skip("No payments found for merchant")

        # Check if this payment already has a PENDING action
        existing_active = session.query(RecoveryAction).filter(
            RecoveryAction.payment_id == payment.id,
            RecoveryAction.status == RecoveryActionStatus.PENDING,
        ).first()

        # If no existing PENDING action, we need to create one first to test the constraint
        if existing_active is None:
            # Create a customer and payment if needed for the test action
            customer = Customer(
                merchant_id=merchant.id,
                external_customer_id=f"active-action-test-cust-{merchant.id}",
                name=f"Test customer for active action",
                email=f"test-active-action_{merchant.id}@test.in",
            )
            session.add(customer)
            session.flush()

            test_payment = Payment(
                merchant_id=merchant.id,
                customer_id=customer.id,
                external_payment_id=f"active-action-test-payment-{merchant.id}",
                amount=100,
                currency="INR",
                method="CARD",
                status="FAILED",
                attempt_number=1,
            )
            session.add(test_payment)
            session.flush()

            # Add the first PENDING action
            pending_action = RecoveryAction(
                payment_id=test_payment.id,
                action_type=RecommendedAction.RETRY,
                status=RecoveryActionStatus.PENDING,
            )
            session.add(pending_action)
            session.commit()  # Commit so it's visible to new transactions

            # Now try to add a second PENDING action - should fail
            duplicate_action = RecoveryAction(
                payment_id=test_payment.id,
                action_type=RecommendedAction.RETRY,
                status=RecoveryActionStatus.PENDING,
            )
            session.add(duplicate_action)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        else:
            # Payment already has a PENDING action, try to add another
            duplicate_action = RecoveryAction(
                payment_id=payment.id,
                action_type=RecommendedAction.RETRY,
                status=RecoveryActionStatus.PENDING,
            )
            session.add(duplicate_action)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        session.rollback()
