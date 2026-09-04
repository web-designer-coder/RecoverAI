"""Phase 2 acceptance tests.

Covers the ten required cases: health, database connectivity, merchant/seed,
payment retrieval, recovery retrieval, payment-not-found, policy retrieval,
audit retrieval, dashboard aggregation and duplicate-external-payment
protection — plus the audit-trail immutability guarantee.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditEvent, Merchant, MerchantPolicy, Payment
from app.repositories import MerchantRepository, PaymentRepository
from app.utils.tokens import create_token
from app.seed import MERCHANT_NAME


# 1. Health endpoint ---------------------------------------------------------
def test_health_endpoint(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


# 2. Database connection ------------------------------------------------------
def test_database_connection(db_session: Session) -> None:
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1


# 3. Merchant created by seed --------------------------------------------------
def test_merchant_seeded(db_session: Session) -> None:
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    assert merchant.name == MERCHANT_NAME
    policy = db_session.scalars(
        select(MerchantPolicy).where(MerchantPolicy.merchant_id == merchant.id)
    ).one()
    assert policy.maximum_retries == 3
    # 16 payments mirroring src/lib/mock-data.ts
    payments = db_session.scalars(select(Payment)).all()
    assert len(payments) == 16


# 4. Payment retrieval --------------------------------------------------------
def test_payment_retrieval(db_session: Session, client) -> None:
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    repo = PaymentRepository(db_session)
    payment = repo.get_by_external_id(merchant.id, "PAY_82931")
    assert payment is not None
    assert payment.amount == Decimal("8499.00")
    token = create_token(str(merchant.id))
    client.headers["Authorization"] = f"Bearer {token}"
    listed = client.get("/api/recoveries", params={"search": "PAY_82931"})
    assert listed.status_code == 200
    assert [p["payment_id"] for p in listed.json()] == ["PAY_82931"]


# 5. Recovery detail retrieval -------------------------------------------------
def test_recovery_detail_retrieval(db_session: Session, client) -> None:
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    response = client.get("/api/recoveries/PAY_82931")
    assert response.status_code == 200
    body = response.json()
    assert body["payment_id"] == "PAY_82931"
    assert body["customer_id"] == "CUST_0482"
    assert body["amount"] == 8499.0
    assert body["decision"]["confidence"] == pytest.approx(0.91)
    assert body["decision"]["recommended_action"] == "RETRY"
    assert len(body["actions"]) >= 1
    assert body["actions"][0]["action_type"] == "RETRY"


# 6. Payment not found --------------------------------------------------------
def test_payment_not_found(db_session: Session, client) -> None:
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    response = client.get("/api/recoveries/PAY_DOES_NOT_EXIST")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "PAYMENT_NOT_FOUND"
    assert "PAY_DOES_NOT_EXIST" in error["message"]


# 7. Policy retrieval ----------------------------------------------------------
def test_policy_retrieval(db_session: Session, client) -> None:
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    response = client.get("/api/policies")
    assert response.status_code == 200
    policy = response.json()
    assert policy["maximum_retries"] == 3
    assert policy["recovery_window_days"] == 14
    # NOTIFY is normalised to the canonical CUSTOMER_NOTIFICATION token.
    assert policy["failure_rules"]["INVALID_DETAILS"] == "CUSTOMER_NOTIFICATION"


# 8. Audit retrieval ------------------------------------------------------------
def test_audit_retrieval(db_session: Session, client) -> None:
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    response = client.get("/api/audit", params={"limit": 50})
    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 12
    # External payment references are resolved, never raw UUIDs.
    assert all(e["payment_id"].startswith("PAY_") for e in events if e["payment_id"])
    per_payment = client.get("/api/recoveries/PAY_82931/audit")
    assert per_payment.status_code == 200
    assert len(per_payment.json()) >= 5


# 9. Dashboard aggregation -------------------------------------------------------
def test_dashboard_aggregation(db_session: Session, client) -> None:
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    kpis = body["kpis"]
    # Seed: 4 RECOVERED of 16 → recovery rate 25%.
    assert kpis["active_recoveries"] == 4  # SCHEDULED payments
    assert kpis["payments_at_risk"] > 0
    assert kpis["recovery_rate"] == pytest.approx(25.0)
    assert kpis["revenue_at_risk"] > 0
    assert len(body["funnel"]) >= 3
    assert any(row["metric"] for row in body["ai_vs_static"])
    assert sum(item["count"] for item in body["failure_breakdown"]) >= 16


# 10. Duplicate external payment protection --------------------------------------
def test_duplicate_external_payment_protection(db_session: Session) -> None:
    merchant = db_session.scalars(select(Merchant).where(Merchant.name == MERCHANT_NAME)).one()
    existing = db_session.scalars(
        select(Payment).where(
            Payment.merchant_id == merchant.id,
            Payment.external_payment_id == "PAY_82931",
        )
    ).one()

    # Repository-level guard.
    assert PaymentRepository(db_session).external_id_exists(merchant.id, "PAY_82931")

    # Database-level guard: the unique constraint has the final say.
    duplicate = Payment(
        merchant_id=existing.merchant_id,
        customer_id=existing.customer_id,
        external_payment_id="PAY_82931",
        amount=Decimal("1.00"),
        currency="INR",
        method=existing.method,
        status=existing.status,
        attempt_number=0,
        priority=existing.priority,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# Bonus: append-only audit trail at the database level ---------------------------
def test_audit_events_are_append_only(db_session: Session) -> None:
    event = db_session.scalars(select(AuditEvent).limit(1)).one()
    event.summary = "tampered"
    with pytest.raises(DBAPIError):
        db_session.commit()
    db_session.rollback()
