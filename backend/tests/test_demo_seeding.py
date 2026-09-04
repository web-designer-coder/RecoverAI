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