"""Development seed — reproduces the RecoverAI demo environment in PostgreSQL.

Source of truth: src/lib/mock-data.ts from the frontend repo (same payments,
customers, amounts, statuses, policies and audit narrative — including
PAY_82931 / ₹8,499).

Run:
    python -m app.seed            # seed if empty
    python -m app.seed --reset    # wipe demo data and reseed
"""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.utils.password_hash import hash_password


def _dec(value: float) -> Decimal:
    """Exact decimal from a float literal (money/rates are never floats at rest)."""
    return Decimal(str(value))

from app.models import (
    AuditEvent,
    Customer,
    Merchant,
    MerchantPolicy,
    Payment,
    PaymentFailure,
    RecoveryAction,
    RecoveryDecision,
    Simulation,
)
from app.models.enums import (
    ActorType,
    AuditCategory,
    AuditEventType,
    FailureCategory,
    PaymentMethod,
    PaymentStatus,
    Priority,
    RecommendedAction,
    RecoveryActionStatus,
)

MERCHANT_NAME = "RecoverAI Demo Merchant"
MERCHANT_EMAIL = "ops@merchant.in"
DEMO_PASSWORD = "demo1234"

# ---------------------------------------------------------------- time helpers

_NOW = datetime.now(timezone.utc)


def _hours_ago(h: float) -> datetime:
    return _NOW - timedelta(hours=h)


def _hours_ahead(h: float) -> datetime:
    return _NOW + timedelta(hours=h)


# ---------------------------------------------------------------- domain seeds
# Mirrors of seedPayments in src/lib/mock-data.ts (frontend is source of truth).
# Tuple order: external id, customer, amount ₹, method, status, priority,
# retry_count, probability, confidence, action, recommended_at(h offset),
# expected_recovery, created_at(h), failed_at(h), next_action_at(h|None),
# failure_reason, failure_category

SEED_PAYMENTS: list[dict] = [
    dict(pid="PAY_82931", cust="CUST_0482", amount=8499, method="UPI", status="SCHEDULED",
         priority="HIGH", retries=1, prob=0.74, conf=0.91, action="RETRY", rec_h=38,
         expected=6282, created_h=-30, failed_h=-6, next_h=38,
         reason="Insufficient balance in linked account", category="INSUFFICIENT_FUNDS"),
    dict(pid="PAY_82944", cust="CUST_1173", amount=15250, method="CARD", status="NEEDS_ACTION",
         priority="HIGH", retries=0, prob=0.82, conf=0.94, action="PAYMENT_UPDATE", rec_h=4,
         expected=12505, created_h=-52, failed_h=-9, next_h=4,
         reason="Card expired at time of charge", category="EXPIRED_CARD"),
    dict(pid="PAY_82950", cust="CUST_0908", amount=4299, method="NET_BANKING", status="SCHEDULED",
         priority="MEDIUM", retries=1, prob=0.88, conf=0.90, action="RETRY", rec_h=2,
         expected=3783, created_h=-20, failed_h=-3, next_h=2,
         reason="Network timeout at issuing bank", category="NETWORK_FAILURE"),
    dict(pid="PAY_82956", cust="CUST_0341", amount=27900, method="CARD", status="HALTED",
         priority="LOW", retries=3, prob=0.07, conf=0.96, action="STOP", rec_h=-1,
         expected=0, created_h=-96, failed_h=-70, next_h=None,
         reason="Issuer declined — do not honour", category="BANK_DECLINE"),
    dict(pid="PAY_82961", cust="CUST_1266", amount=6750, method="UPI", status="QUEUED",
         priority="MEDIUM", retries=0, prob=0.69, conf=0.86, action="RETRY", rec_h=26,
         expected=4658, created_h=-14, failed_h=-2, next_h=26,
         reason="Insufficient balance in linked account", category="INSUFFICIENT_FUNDS"),
    dict(pid="PAY_82902", cust="CUST_0517", amount=12999, method="CARD", status="NEEDS_ACTION",
         priority="MEDIUM", retries=1, prob=0.58, conf=0.81, action="NOTIFY", rec_h=6,
         expected=7539, created_h=-40, failed_h=-12, next_h=6,
         reason="Incorrect CVV provided", category="INVALID_DETAILS"),
    dict(pid="PAY_82876", cust="CUST_0230", amount=9850, method="UPI", status="PROCESSING",
         priority="HIGH", retries=2, prob=0.71, conf=0.88, action="RETRY", rec_h=-3,
         expected=6994, created_h=-60, failed_h=-28, next_h=-3,
         reason="Network timeout at issuing bank", category="NETWORK_FAILURE"),
    dict(pid="PAY_82845", cust="CUST_0764", amount=21200, method="NET_BANKING", status="RECOVERED",
         priority="HIGH", retries=2, prob=0.77, conf=0.92, action="RETRY", rec_h=-20,
         expected=16324, created_h=-3000, failed_h=-72, next_h=None,
         reason="Insufficient balance in linked account", category="INSUFFICIENT_FUNDS"),
    dict(pid="PAY_82831", cust="CUST_1099", amount=3450, method="CARD", status="RECOVERED",
         priority="MEDIUM", retries=1, prob=0.80, conf=0.93, action="PAYMENT_UPDATE", rec_h=-26,
         expected=2760, created_h=-2200, failed_h=-96, next_h=None,
         reason="Card expired at time of charge", category="EXPIRED_CARD"),
    dict(pid="PAY_82970", cust="CUST_1418", amount=56999, method="CARD", status="NEEDS_ACTION",
         priority="HIGH", retries=0, prob=0.22, conf=0.78, action="ESCALATE", rec_h=1,
         expected=12540, created_h=-8, failed_h=-1, next_h=1,
         reason="Transaction flagged by risk engine", category="BANK_DECLINE"),
    dict(pid="PAY_82810", cust="CUST_0685", amount=7899, method="UPI", status="RECOVERED",
         priority="MEDIUM", retries=1, prob=0.66, conf=0.84, action="RETRY", rec_h=-44,
         expected=5213, created_h=-1400, failed_h=-120, next_h=None,
         reason="Insufficient balance in linked account", category="INSUFFICIENT_FUNDS"),
    dict(pid="PAY_82975", cust="CUST_0877", amount=11250, method="NET_BANKING", status="QUEUED",
         priority="MEDIUM", retries=0, prob=0.85, conf=0.89, action="RETRY", rec_h=10,
         expected=9563, created_h=-5, failed_h=-1, next_h=10,
         reason="Network timeout at issuing bank", category="NETWORK_FAILURE"),
    dict(pid="PAY_82788", cust="CUST_0422", amount=19499, method="CARD", status="HALTED",
         priority="LOW", retries=2, prob=0.11, conf=0.90, action="STOP", rec_h=-30,
         expected=0, created_h=-200, failed_h=-150, next_h=None,
         reason="Issuer declined — do not honour", category="BANK_DECLINE"),
    dict(pid="PAY_82981", cust="CUST_1350", amount=9150, method="CARD", status="QUEUED",
         priority="LOW", retries=0, prob=0.63, conf=0.83, action="NOTIFY", rec_h=8,
         expected=5765, created_h=-3, failed_h=-1, next_h=8,
         reason="Incorrect expiry date on file", category="INVALID_DETAILS"),
    dict(pid="PAY_82760", cust="CUST_0911", amount=26750, method="UPI", status="RECOVERED",
         priority="HIGH", retries=2, prob=0.79, conf=0.91, action="RETRY", rec_h=-60,
         expected=21133, created_h=-700, failed_h=-160, next_h=None,
         reason="Insufficient balance in linked account", category="INSUFFICIENT_FUNDS"),
    dict(pid="PAY_82988", cust="CUST_1503", amount=5399, method="UPI", status="SCHEDULED",
         priority="LOW", retries=1, prob=0.81, conf=0.87, action="RETRY", rec_h=14,
         expected=4373, created_h=-10, failed_h=-4, next_h=14,
         reason="Network timeout at issuing bank", category="NETWORK_FAILURE"),
]

FAILURE_CODES = {
    "INSUFFICIENT_FUNDS": "insufficient_balance",
    "EXPIRED_CARD": "card_expired",
    "NETWORK_FAILURE": "gateway_timeout",
    "BANK_DECLINE": "do_not_honour",
    "INVALID_DETAILS": "invalid_cvv_or_expiry",
    "OTHER": "unspecified",
}

CATEGORY_LABELS = {
    "INSUFFICIENT_FUNDS": "Insufficient Funds",
    "EXPIRED_CARD": "Expired Card",
    "NETWORK_FAILURE": "Network Failure",
    "BANK_DECLINE": "Bank Decline",
    "INVALID_DETAILS": "Invalid Details",
    "OTHER": "Other",
}

# Action-status mapping used only by the seed narrative.
def _action_status_for(payment_status: str, action: str) -> RecoveryActionStatus:
    if payment_status == "RECOVERED":
        return RecoveryActionStatus.SUCCEEDED
    if payment_status == "SCHEDULED":
        return RecoveryActionStatus.SCHEDULED
    if payment_status == "PROCESSING":
        return RecoveryActionStatus.PROCESSING
    if payment_status == "HALTED":
        return RecoveryActionStatus.BLOCKED
    if payment_status == "NEEDS_ACTION":
        return RecoveryActionStatus.ESCALATED if action == "ESCALATE" else RecoveryActionStatus.PENDING
    return RecoveryActionStatus.PENDING


SEED_POLICIES = {
    "maximum_retries": 3,
    "recovery_window_days": 14,
    "minimum_ai_confidence": 70,
    "high_value_threshold": 50000,
    "failure_rules": {
        "INSUFFICIENT_FUNDS": "RETRY",
        "NETWORK_FAILURE": "RETRY",
        "EXPIRED_CARD": "PAYMENT_UPDATE",
        "INVALID_DETAILS": "CUSTOMER_NOTIFICATION",
        "BANK_DECLINE": "STOP",
        "OTHER": "ESCALATE",
    },
    "prevent_duplicate_recovery": True,
    "require_policy_approval": True,
    "maintain_audit_log": True,
    "escalate_high_value": True,
}

# Condensed mirrors of seedAudit (frontend remains source of truth).
SEED_AUDIT: list[dict] = [
    dict(h=-6, etype="PAYMENT_FAILED", cat="EXECUTION", pid="PAY_82931",
         summary="Payment failed — ₹8,499", amount=8499,
         meta={"Failure code": "insufficient_balance", "Payment method": "UPI"}),
    dict(h=-6 + 1 / 3600, etype="AI_DIAGNOSIS", cat="AI_DECISION", pid="PAY_82931",
         summary="Diagnosed as Insufficient Funds — 91% confidence",
         meta={"Confidence": "91%", "Failure nature": "Transient"}, actor="AI_ENGINE"),
    dict(h=-6 + 2 / 3600, etype="RECOVERY_PREDICTION", cat="AI_DECISION", pid="PAY_82931",
         summary="Recovery probability predicted at 74%",
         meta={"Predicted probability": "74%", "Expected recovery": "₹6,282"}, actor="AI_ENGINE"),
    dict(h=-6 + 3 / 3600, etype="ACTION_SELECTED", cat="AI_DECISION", pid="PAY_82931",
         summary="Action selected — Retry",
         meta={"Action": "RETRY", "Rationale": "Highest predicted success within policy window"},
         actor="AI_ENGINE"),
    dict(h=-6 + 4 / 3600, etype="POLICY_CHECK", cat="POLICY", pid="PAY_82931",
         summary="Policy check — Approved",
         meta={"Retry limit": "1 / 3", "Confidence threshold": "91% > 70%", "Result": "APPROVED"}),
    dict(h=-6 + 5 / 3600, etype="RECOVERY_SCHEDULED", cat="EXECUTION", pid="PAY_82931",
         summary="Retry scheduled for the optimal window",
         meta={"Action": "RETRY", "Channel": "UPI"}),
    dict(h=-20, etype="POLICY_CHECK", cat="POLICY", pid="PAY_82876",
         summary="Policy check — Approved", meta={"Retry limit": "2 / 3", "Result": "APPROVED"}),
    dict(h=-20 + 1 / 60, etype="RECOVERY_EXECUTED", cat="EXECUTION", pid="PAY_82876",
         summary="Retry executed — ₹9,850", amount=9850, meta={"Attempt": "3", "Channel": "UPI"}),
    dict(h=-26, etype="PAYMENT_RECOVERED", cat="RESULT", pid="PAY_82845",
         summary="Payment recovered — ₹21,200", amount=21200,
         meta={"Attempts": "2", "Time to recovery": "52h 14m"}),
    dict(h=-30, etype="CUSTOMER_NOTIFIED", cat="EXECUTION", pid="PAY_82831",
         summary="Customer notified — payment method update requested",
         meta={"Channel": "Email + SMS", "Reason": "EXPIRED_CARD"}),
    dict(h=-44, etype="PAYMENT_RECOVERED", cat="RESULT", pid="PAY_82831",
         summary="Payment recovered — ₹3,450", amount=3450,
         meta={"Attempts": "1", "Time to recovery": "41h 03m"}),
    dict(h=-70, etype="RECOVERY_HALTED", cat="RESULT", pid="PAY_82956",
         summary="Recovery halted — hard decline",
         meta={"Reason": "BANK_DECLINE (do not honour)", "Policy": "Hard decline handling → STOP"}),
]

SEED_SIMULATIONS = [
    dict(transactions=5000, average_amount=2400, failure_rate=0.12, window=14),
    dict(transactions=12000, average_amount=1850, failure_rate=0.09, window=21),
]

STATIC_RECOVERY_RATE = 53.0
AI_RECOVERY_RATE = 68.5


# ---------------------------------------------------------------- seeding logic

def _canonical_action(token: str) -> RecommendedAction:
    return RecommendedAction("CUSTOMER_NOTIFICATION" if token == "NOTIFY" else token)
def seed_merchants_data(session: Session, merchant: Merchant) -> None:
    """Seed demo dataset belonging ONLY to `merchant`. Idempotent by merchant scope."""
    existing_payments = session.scalars(
        select(Payment).where(Payment.merchant_id == merchant.id)
    ).first()
    if existing_payments is not None:
        return

    session.add(MerchantPolicy(merchant_id=merchant.id, **SEED_POLICIES))
    customers: dict[str, Customer] = {}
    payments_by_external: dict[str, Payment] = {}

    for s in SEED_PAYMENTS:
        customer = customers.get(s["cust"])
        if customer is None:
            customer = Customer(
                merchant_id=merchant.id,
                external_customer_id=s["cust"],
                name=f"Demo customer {s['cust'].split('_')[1]}",
                email=f"{s['cust'].lower()}@demo.in",
            )
            session.add(customer)
            customers[s["cust"]] = customer

        payment = Payment(
            merchant_id=merchant.id,
            customer=customer,
            external_payment_id=s["pid"],
            amount=_dec(s["amount"]),
            currency="INR",
            method=PaymentMethod(s["method"]),
            status=PaymentStatus(s["status"]),
            attempt_number=s["retries"],
            priority=Priority(s["priority"]),
            next_action_at=_hours_ahead(s["next_h"]) if s["next_h"] is not None else None,
            created_at=_hours_ago(-s["created_h"]),
        )
        session.add(payment)
        payments_by_external[s["pid"]] = payment

        session.add(PaymentFailure(
            payment=payment,
            failure_code=FAILURE_CODES[s["category"]],
            failure_reason=s["reason"],
            failure_category=FailureCategory(s["category"]),
            attempt_number=max(s["retries"], 1),
            occurred_at=_hours_ago(-s["failed_h"]),
            meta={"Gateway response": FAILURE_CODES[s["category"]]},
        ))

        session.add(RecoveryDecision(
            payment=payment,
            diagnosis=CATEGORY_LABELS[s["category"]],
            ai_confidence=_dec(s["conf"]),
            recovery_probability=_dec(s["prob"]),
            recommended_action=_canonical_action(s["action"]),
            expected_recovery_amount=_dec(s["expected"]),
            optimal_recovery_at=_hours_ahead(s["rec_h"]) if s["rec_h"] > 0 else _hours_ago(-s["rec_h"]),
            model_version="recoverai-demo-v0",
        ))

        action_status = _action_status_for(s["status"], s["action"])
        scheduled = _hours_ahead(s["next_h"]) if s["next_h"] is not None else (
            _hours_ahead(s["rec_h"]) if s["rec_h"] > 0 else _hours_ago(-s["rec_h"])
        )
        session.add(RecoveryAction(
            payment=payment,
            action_type=_canonical_action(s["action"]),
            status=action_status,
            scheduled_at=scheduled if action_status != RecoveryActionStatus.PENDING else None,
            started_at=scheduled if action_status in (
                RecoveryActionStatus.PROCESSING, RecoveryActionStatus.SUCCEEDED
            ) else None,
            completed_at=(
                scheduled + timedelta(hours=2)
                if action_status == RecoveryActionStatus.SUCCEEDED
                else None
            ),
        ))

    session.flush()

    for e in SEED_AUDIT:
        payment = payments_by_external[e["pid"]]
        session.add(AuditEvent(
            merchant_id=merchant.id,
            payment_id=payment.id,
            event_type=AuditEventType(e["etype"]),
            category=AuditCategory(e["cat"]),
            actor_type=ActorType(e.get("actor", "SYSTEM")),
            summary=e["summary"],
            amount=_dec(e["amount"]) if "amount" in e else None,
            meta=e["meta"],
            created_at=_hours_ago(-e["h"]),
        ))
    existing_failed = {e["pid"] for e in SEED_AUDIT if e["etype"] == "PAYMENT_FAILED"}
    for s in SEED_PAYMENTS:
        if s["pid"] in existing_failed:
            continue
        payment = payments_by_external[s["pid"]]
        session.add(AuditEvent(
            merchant_id=merchant.id,
            payment_id=payment.id,
            event_type=AuditEventType.PAYMENT_FAILED,
            category=AuditCategory.EXECUTION,
            summary=f"Payment failed — ₹{s['amount']:,}",
            amount=_dec(s["amount"]),
            meta={"Failure code": FAILURE_CODES[s["category"]], "Payment method": s["method"]},
            created_at=_hours_ago(-s["failed_h"]),
        ))

    for sim in SEED_SIMULATIONS:
        failed = round(sim["transactions"] * sim["failure_rate"])
        avg_recovered_value = sim["average_amount"] * 0.98
        static_count = round(failed * STATIC_RECOVERY_RATE / 100)
        ai_count = round(failed * AI_RECOVERY_RATE / 100)
        session.add(Simulation(
            merchant_id=merchant.id,
            transactions=sim["transactions"],
            average_amount=_dec(sim["average_amount"]),
            failure_rate=_dec(sim["failure_rate"]),
            recovery_window_days=sim["window"],
            static_recovery_rate=_dec(STATIC_RECOVERY_RATE),
            ai_recovery_rate=_dec(AI_RECOVERY_RATE),
            static_recovered_revenue=_dec(round(static_count * avg_recovered_value, 2)),
            ai_recovered_revenue=_dec(round(ai_count * avg_recovered_value, 2)),
            incremental_revenue=_dec(round((ai_count - static_count) * avg_recovered_value, 2)),
        ))
    session.flush()


def seed_database(
    session: Session,
    merchant_name: str = MERCHANT_NAME,
    email: str = MERCHANT_EMAIL,
    password: str = DEMO_PASSWORD,
) -> Merchant:
    """Populate an EMPTY database with the demo environment.

    Idempotent: if a merchant with ``email`` already exists, its
    ``password_hash`` is back-filled when NULL (migrates legacy seed data)
    and the existing merchant is returned without creating duplicates.
    """
    existing = session.scalars(
        select(Merchant).where(Merchant.email == email)
    ).first()
    if existing is not None:
        # Migrate legacy seed merchants that were created without a password.
        if existing.password_hash is None:
            existing.password_hash = hash_password(password)
        return existing

    merchant = Merchant(
        name=merchant_name,
        email=email,
        password_hash=hash_password(password),
    )
    session.add(merchant)
    session.flush()
    seed_merchants_data(session, merchant)
    return merchant



def clear_demo_data(session: Session) -> int:
    """Delete all application rows in FK-safe order. Returns rowcount.

    audit_events carries a database trigger that rejects UPDATE/DELETE
    (append-only history). Only this explicit, deliberate reset path may
    bypass it — via ``session_replication_role = replica`` — never ordinary
    application traffic.
    """
    from sqlalchemy import text

    deleted = 0
    session.execute(text("SET session_replication_role = replica"))
    try:
        for model in (
            RecoveryAction,
            RecoveryDecision,
            PaymentFailure,
            AuditEvent,
            Payment,
            Simulation,
            MerchantPolicy,
            Customer,
            Merchant,
        ):
            n = session.query(model).delete()
            deleted += int(n or 0)
        session.flush()
    finally:
        session.execute(text("SET session_replication_role = DEFAULT"))
    return deleted


def main(reset: bool = False) -> int:
    factory = get_session_factory()
    session = factory()
    try:
        existing = session.scalars(select(Merchant)).first()
        if existing is not None and not reset:
            print(f"Database already contains demo data for '{existing.name}'.")
            print("Use --reset to wipe and reseed.")
            return 0
        if reset:
            removed = clear_demo_data(session)
            print(f"Cleared {removed} existing rows.")

        merchant = seed_database(session)
        session.commit()
        counts = {
            "customers": session.query(Customer).count(),
            "payments": session.query(Payment).count(),
            "audit_events": session.query(AuditEvent).count(),
            "policies": session.query(MerchantPolicy).count(),
            "simulations": session.query(Simulation).count(),
        }
        pretty = ", ".join(f"{k}={v}" for k, v in counts.items())
        print(f"Seeded merchant {merchant.name} ({merchant.environment.value} mode): {pretty}")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main(reset="--reset" in sys.argv))


