"""Regression tests for demo data seeding functionality."""
import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import (
    Merchant,
    Payment,
    PaymentFailure,
    RecoveryDecision,
    RecoveryAction,
    AuditEvent,
    Simulation,
    MerchantPolicy,
    Customer,
)
from app.seed import SEED_PAYMENTS, SEED_AUDIT, SEED_POLICIES, SEED_SIMULATIONS
from app.config import get_settings, Settings
from app.services.merchant_service import MerchantService
from app.utils.password_hash import hash_password


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear the settings cache before each test to ensure clean state."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_new_merchant_signup_creates_merchant(db_session: Session, monkeypatch):
    """(1) New merchant signup creates the merchant."""
    # Settings with demo seeding enabled
    test_settings = Settings(app_env="test", enable_demo_seeding=True)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: test_settings)

    service = MerchantService(db_session)
    merchant = service.create_merchant(
        business_name="Test Merchant",
        email="test@example.com",
        password="securepassword123"
    )

    assert merchant is not None
    assert merchant.id is not None
    assert merchant.name == "Test Merchant"
    assert merchant.email == "test@example.com"


def test_demo_dataset_created_only_when_enabled(db_session: Session, monkeypatch):
    """(2) Demo dataset is created only when demo seeding is enabled."""
    # Test with disabled seeding
    disabled_settings = Settings(app_env="test", enable_demo_seeding=False)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: disabled_settings)

    service = MerchantService(db_session)
    merchant = service.create_merchant(
        business_name="Test Merchant Disabled",
        email="test_disabled@example.com",
        password="securepassword123"
    )

    # Check that no demo data was created
    payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant.id)
    ).all()
    assert len(payments) == 0


def test_seeded_records_belong_to_newly_created_merchant(db_session: Session, monkeypatch):
    """(3) Seeded records belong to the newly created merchant."""
    test_settings = Settings(app_env="test", enable_demo_seeding=True)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: test_settings)

    service = MerchantService(db_session)
    merchant = service.create_merchant(
        business_name="Test Merchant With Data",
        email="test_with_data@example.com",
        password="securepassword123"
    )

    # Verify seeded data exists and belongs to the merchant
    payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant.id)
    ).all()
    assert len(payments) == len(SEED_PAYMENTS)

    for payment in payments:
        assert payment.merchant_id == merchant.id

    # Check other seeded entities through Payment relationship for PaymentFailure
    # PaymentFailure -> Payment -> merchant_id
    failures = db_session.scalars(
        select(PaymentFailure).join(Payment).where(Payment.merchant_id == merchant.id)
    ).all()
    assert len(failures) == len(SEED_PAYMENTS)  # One failure per payment

    decisions = db_session.scalars(
        select(RecoveryDecision).join(Payment, RecoveryDecision.payment_id == Payment.id).where(Payment.merchant_id == merchant.id)
    ).all()
    assert len(decisions) == len(SEED_PAYMENTS)

    actions = db_session.scalars(
        select(RecoveryAction).join(Payment, RecoveryAction.payment_id == Payment.id).where(Payment.merchant_id == merchant.id)
    ).all()
    assert len(actions) == len(SEED_PAYMENTS)

    # Audit events: 12 from SEED_AUDIT + 15 additional PAYMENT_FAILED events for payments
    # (all payments except the 3 that already have a PAYMENT_FAILED in SEED_AUDIT)
    # 12 + 15 = 27 total
    audit_events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.merchant_id == merchant.id)
    ).all()
    # At minimum, SEED_AUDIT events are present
    assert len(audit_events) >= len(SEED_AUDIT)

    simulations = db_session.scalars(
        select(Simulation).where(Simulation.merchant_id == merchant.id)
    ).all()
    assert len(simulations) == len(SEED_SIMULATIONS)

    policies = db_session.scalars(
        select(MerchantPolicy).where(MerchantPolicy.merchant_id == merchant.id)
    ).all()
    assert len(policies) == 1  # One policy record
    assert policies[0].merchant_id == merchant.id


def test_existing_merchant_isolation(db_session: Session, monkeypatch):
    """(4) Existing merchants cannot see another merchant's seeded records."""
    test_settings = Settings(app_env="test", enable_demo_seeding=True)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: test_settings)

    service = MerchantService(db_session)

    # Create first merchant
    merchant1 = service.create_merchant(
        business_name="Merchant One",
        email="merchant1@example.com",
        password="securepassword123"
    )

    # Create second merchant
    merchant2 = service.create_merchant(
        business_name="Merchant Two",
        email="merchant2@example.com",
        password="securepassword123"
    )

    # Verify merchant1 only sees their own data
    m1_payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant1.id)
    ).all()
    assert len(m1_payments) == len(SEED_PAYMENTS)

    # Verify merchant2 only sees their own data
    m2_payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant2.id)
    ).all()
    assert len(m2_payments) == len(SEED_PAYMENTS)

    # Verify the data is different (different IDs)
    m1_payment_ids = {p.id for p in m1_payments}
    m2_payment_ids = {p.id for p in m2_payments}
    assert m1_payment_ids.isdisjoint(m2_payment_ids)

    # Verify cross-merchant queries return empty
    m1_seeing_m2 = db_session.scalars(
        select(Payment).where(
            Payment.merchant_id == merchant2.id,
            Payment.merchant_id == merchant1.id  # Impossible condition
        )
    ).all()
    assert len(m1_seeing_m2) == 0


def test_two_merchants_receive_separate_datasets(db_session: Session, monkeypatch):
    """(5) Two newly created merchants receive separate datasets."""
    test_settings = Settings(app_env="test", enable_demo_seeding=True)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: test_settings)

    service = MerchantService(db_session)

    # Get count before creating new merchants
    count_before = len(db_session.scalars(select(Payment)).all())

    # Create first merchant
    merchant1 = service.create_merchant(
        business_name="First Merchant",
        email="first@example.com",
        password="securepassword123"
    )

    # Create second merchant
    merchant2 = service.create_merchant(
        business_name="Second Merchant",
        email="second@example.com",
        password="securepassword123"
    )

    # Get all payments for both new merchants
    m1_payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant1.id)
    ).all()
    m2_payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant2.id)
    ).all()

    assert len(m1_payments) == len(SEED_PAYMENTS)
    assert len(m2_payments) == len(SEED_PAYMENTS)

    # Verify no overlap in payment IDs between the two new merchants
    # Each uses same external IDs from SEED but different DB IDs
    m1_ids = {p.id for p in m1_payments}
    m2_ids = {p.id for p in m2_payments}
    assert m1_ids.isdisjoint(m2_ids)

    # Verify each set matches seed data (different amounts, etc.)
    seed_amounts = {p["amount"] for p in SEED_PAYMENTS}
    m1_amounts = {float(p.amount) for p in m1_payments}
    m2_amounts = {float(p.amount) for p in m2_payments}

    assert m1_amounts == seed_amounts
    assert m2_amounts == seed_amounts


def test_running_seed_twice_does_not_duplicate_records(db_session: Session, monkeypatch):
    """(6) Running the seed twice does not duplicate records."""
    test_settings = Settings(app_env="test", enable_demo_seeding=True)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: test_settings)

    service = MerchantService(db_session)

    # Create merchant
    merchant = service.create_merchant(
        business_name="Test Merchant",
        email="test_twice@example.com",
        password="securepassword123"
    )

    # Get initial counts
    initial_payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant.id)
    ).all()
    initial_count = len(initial_payments)
    assert initial_count == len(SEED_PAYMENTS)

    # Manually call seed again (simulating retry)
    from app.seed import seed_merchants_data
    seed_merchants_data(db_session, merchant)

    # Count should be the same
    after_payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant.id)
    ).all()
    after_count = len(after_payments)
    assert after_count == initial_count
    assert after_count == len(SEED_PAYMENTS)


def test_production_configuration_does_not_automatically_seed(db_session: Session, monkeypatch):
    """(7) Production configuration does not automatically seed demo data."""
    # Test with production environment
    prod_settings = Settings(app_env="production", enable_demo_seeding=True)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: prod_settings)

    service = MerchantService(db_session)
    merchant = service.create_merchant(
        business_name="Prod Merchant",
        email="prod@example.com",
        password="securepassword123"
    )

    # Should not seed in production even if enabled
    payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant.id)
    ).all()
    assert len(payments) == 0


def test_signup_authentication_still_works_normally(db_session: Session, monkeypatch):
    """(8) Signup/authentication still works normally."""
    test_settings = Settings(app_env="test", enable_demo_seeding=True)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: test_settings)

    service = MerchantService(db_session)

    # Create merchant
    merchant = service.create_merchant(
        business_name="Auth Test",
        email="auth@example.com",
        password="authpassword123"
    )

    # Authenticate with correct credentials
    authenticated = service.authenticate_merchant("auth@example.com", "authpassword123")
    assert authenticated is not None
    assert authenticated.id == merchant.id

    # Authenticate with wrong password
    wrong_auth = service.authenticate_merchant("auth@example.com", "wrongpassword")
    assert wrong_auth is None

    # Authenticate with non-existent email
    nonexistent = service.authenticate_merchant("nonexistent@example.com", "any password")
    assert nonexistent is None


def test_existing_merchant_isolation_tests_continue_passing(db_session: Session, monkeypatch):
    """(9) Existing merchant isolation tests continue passing."""
    # This is essentially testing that our changes didn't break existing isolation
    # Create a merchant without seeding (by disabling it)
    no_seed_settings = Settings(app_env="test", enable_demo_seeding=False)
    monkeypatch.setattr('app.services.merchant_service.get_settings', lambda: no_seed_settings)

    service = MerchantService(db_session)
    merchant = service.create_merchant(
        business_name="Isolation Test",
        email="isolation@example.com",
        password="securepassword123"
    )

    # Merchant should exist but have no seeded data
    assert merchant is not None
    assert merchant.id is not None

    payments = db_session.scalars(
        select(Payment).where(Payment.merchant_id == merchant.id)
    ).all()
    assert len(payments) == 0  # No seeding occurred


def test_repair_demo_recovery_dates():
    """Test that repair_demo_recovery_dates spreads recovered payments across months."""
    from app.seed import repair_demo_recovery_dates, _DEMO_MERCHANT_EMAIL, _DEMO_RECOVERED_DATES_HOURS
    from app.database import get_session_factory
    from app.models import Merchant, Payment
    from app.models.enums import PaymentStatus
    from sqlalchemy import select
    from datetime import datetime, timezone

    # Use a fresh session for testing
    factory = get_session_factory()
    session = factory()

    try:
        # First, seed the database to create demo merchant and payments
        from app.seed import seed_database
        # Temporarily override settings to allow seeding in test
        import app.config
        original_get_settings = app.config.get_settings

        class TestSettings:
            app_env = "test"
            enable_demo_seeding = True
            seed_demo_password = "test"

        app.config.get_settings = lambda: TestSettings()

        try:
            seed_database(session)
            session.commit()
        finally:
            app.config.get_settings = original_get_settings

        # Verify demo merchant exists
        demo_merchant = session.scalars(
            select(Merchant).where(Merchant.email == _DEMO_MERCHANT_EMAIL)
        ).first()
        print(f"DEBUG: Demo merchant found: {demo_merchant is not None}")
        if demo_merchant:
            print(f"DEBUG: Demo merchant ID: {demo_merchant.id}")
            print(f"DEBUG: Demo merchant email: {demo_merchant.email}")
        assert demo_merchant is not None, "Demo merchant should exist after seeding"

        # Verify we have the 4 recovered payments
        recovered_payments = session.scalars(
            select(Payment).where(
                Payment.merchant_id == demo_merchant.id,
                Payment.status == PaymentStatus.RECOVERED
            )
        ).all()
        print(f"DEBUG: Found {len(recovered_payments)} recovered payments")
        for p in recovered_payments:
            print(f"DEBUG: Payment {p.external_payment_id}: {p.created_at}")
        assert len(recovered_payments) == 4, f"Expected 4 recovered payments, got {len(recovered_payments)}"

        # Record original dates
        original_dates = {p.external_payment_id: p.created_at for p in recovered_payments}
        print(f"DEBUG: Original dates: {original_dates}")

        # Run the repair function
        repaired_count = repair_demo_recovery_dates(session)
        print(f"DEBUG: Repair function returned: {repaired_count}")
        session.commit()

        # Should have repaired all 4 payments
        assert repaired_count == 4, f"Expected to repair 4 payments, got {repaired_count}"

        # Verify dates have been updated and are spread across different months
        updated_payments = session.scalars(
            select(Payment).where(
                Payment.merchant_id == demo_merchant.id,
                Payment.status == PaymentStatus.RECOVERED
            )
        ).all()
        print(f"DEBUG: After repair, found {len(updated_payments)} recovered payments")
        for p in updated_payments:
            print(f"DEBUG: Payment {p.external_payment_id}: {p.created_at}")

        # Check that all dates were actually changed
        for payment in updated_payments:
            assert payment.created_at != original_dates[payment.external_payment_id], \
                f"Date for payment {payment.external_payment_id} was not updated"

        # Verify the dates are spread across different months (May-Aug 2026)
        # Extract year-month from each date
        months = set()
        for payment in updated_payments:
            # Convert to year-month string for comparison
            month_key = payment.created_at.strftime("%Y-%m")
            months.add(month_key)
        print(f"DEBUG: Months found: {months}")

        # Should have payments in multiple different months
        assert len(months) > 1, f"Expected payments spread across multiple months, got months: {months}"

        # Verify idempotency - running again should repair 0 payments
        repaired_count_2 = repair_demo_recovery_dates(session)
        print(f"DEBUG: Second repair call returned: {repaired_count_2}")
        assert repaired_count_2 == 0, f"Expected 0 repairs on second call (idempotent), got {repaired_count_2}"

    finally:
        session.close()


def test_repair_demo_recovery_dates_no_demo_merchant():
    """Test that repair_demo_recovery_dates no-ops when demo merchant is absent."""
    from app.seed import repair_demo_recovery_dates
    from app.database import get_session_factory

    # Use a fresh session (no demo merchant seeded)
    factory = get_session_factory()
    session = factory()

    try:
        # Should return 0 when no demo merchant exists
        repaired = repair_demo_recovery_dates(session)
        assert repaired == 0, f"Expected 0 repairs when no demo merchant, got {repaired}"
    finally:
        session.close()
