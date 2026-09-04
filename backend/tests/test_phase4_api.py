"""Phase 4 integration tests — service + API against the seeded test DB.

Runs inside transaction-scoped sessions (rolled back per test), so dev data is
never touched and analyses here never leak into other tests.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import AuditEvent, Payment, RecoveryDecision
from app.models.enums import ActorType, AuditEventType, RecommendedAction
from app.repositories import IntelligenceRepository, PaymentRepository
from app.services.recovery_intelligence_service import RecoveryIntelligenceService
from app.utils.errors import AppError
from app.utils.tokens import create_token

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def _payment(db_session, external_id: str) -> Payment:
    return db_session.scalars(
        select(Payment).where(Payment.external_payment_id == external_id)
    ).first()


def test_analyze_persists_full_decision(db_session, merchant_id):
    before = db_session.scalars(select(RecoveryDecision)).all()
    response = RecoveryIntelligenceService(db_session).analyze(merchant_id, "PAY_82931", now=NOW)

    after = db_session.scalars(select(RecoveryDecision)).all()
    assert len(after) == len(before) + 1
    decision = after[-1]
    assert decision.payment_id == _payment(db_session, "PAY_82931").id
    assert decision.diagnosis
    assert decision.ai_confidence == Decimal(str(response.confidence))
    assert decision.recovery_probability == Decimal(str(response.probability))
    assert decision.recommended_action == RecommendedAction(response.recommended_action)
    assert decision.expected_recovery_amount.as_tuple().exponent == -2
    assert decision.optimal_recovery_at is not None
    assert decision.model_version == "recoverai-v1"
    assert decision.signals and isinstance(decision.signals, list)
    assert decision.explanation.startswith("RecoverAI recommends")
    assert decision.optimal_window in ("NOW", "+12H", "+1D", "+2D")
    assert decision.data_sufficiency in ("HIGH", "MEDIUM", "LOW")


def test_repeated_analysis_appends_versions_and_keeps_old_rows(db_session, merchant_id):
    service = RecoveryIntelligenceService(db_session)
    first = service.analyze(merchant_id, "PAY_82931", now=NOW)
    second = service.analyze(
        merchant_id, "PAY_82931",
        now=datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc),
    )

    assert first.decision_id != second.decision_id
    # Monotonic per-payment versions: current = highest version_number.
    assert second.version_number == first.version_number + 1
    decisions = (
        db_session.scalars(
            select(RecoveryDecision)
            .where(RecoveryDecision.payment_id == _payment(db_session, "PAY_82931").id)
            .order_by(RecoveryDecision.version_number)
        ).all()
    )
    assert len(decisions) >= 2
    assert [d.version_number for d in decisions] == sorted(d.version_number for d in decisions)
    assert str(decisions[-1].id) == second.decision_id


def test_analysis_writes_three_ai_audits_with_metadata(db_session, merchant_id):
    payment_id = _payment(db_session, "PAY_82931").id
    response = RecoveryIntelligenceService(db_session).analyze(merchant_id, "PAY_82931", now=NOW)

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.payment_id == payment_id)
    ).all()
    new = [
        e for e in events
        if e.event_type in (AuditEventType.AI_DIAGNOSIS, AuditEventType.RECOVERY_PREDICTION,
                            AuditEventType.ACTION_SELECTED)
        and e.meta and e.meta.get("decision_id") == response.decision_id
    ]
    assert {e.event_type for e in new} == {
        AuditEventType.AI_DIAGNOSIS, AuditEventType.RECOVERY_PREDICTION, AuditEventType.ACTION_SELECTED,
    }
    for e in new:
        assert e.actor_type == ActorType.AI_ENGINE
        assert e.meta["model_version"] == "recoverai-v1"
        assert e.meta["data_sufficiency"] == response.data_sufficiency
    by_type = {e.event_type: e for e in new}
    assert by_type[AuditEventType.ACTION_SELECTED].meta["action"] == response.recommended_action
    assert by_type[AuditEventType.ACTION_SELECTED].meta["window"] == response.optimal_window
    assert by_type[AuditEventType.RECOVERY_PREDICTION].meta["probability"] == response.probability


def test_feature_context_is_leakage_safe(db_session):
    """The current payment must be excluded from its own history."""
    from app.models import Merchant, PaymentFailure

    repo = IntelligenceRepository(db_session)
    payments = PaymentRepository(db_session)
    merchant_id = db_session.scalars(select(Merchant.id)).first()
    payment = payments.get_by_external_id(merchant_id, "PAY_82931")
    failure = payments.list_latest_failures([payment.id])[payment.id]

    ctx = repo.feature_context(payment, failure)

    manual = db_session.execute(
        select(Payment.id)
        .join(PaymentFailure, PaymentFailure.payment_id == Payment.id)
        .where(
            Payment.merchant_id == merchant_id,
            Payment.id != payment.id,
            PaymentFailure.occurred_at < failure.occurred_at,
        )
    ).scalars().all()
    assert ctx.history.total_failures == len(manual)


# --- HTTP error contract ----------------------------------------------------


def test_http_analyze_success_and_error_codes(client, merchant_id, db_session):
    from app.repositories import MerchantRepository
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    ok = client.post("/api/recoveries/PAY_82961/analyze")  # QUEUED seed row
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["is_current"] is True
    assert 0.0 <= body["probability"] <= 1.0
    assert body["confidence"] != body["probability"]
    assert body["recommended_action"] in {
        "RETRY", "PAYMENT_UPDATE", "CUSTOMER_NOTIFICATION", "ESCALATE", "STOP",
    }

    cases = {
        "PAY_MISSING": (404, "PAYMENT_NOT_FOUND"),
        "PAY_82845": (409, "ALREADY_RECOVERED"),   # RECOVERED seed
        "PAY_82956": (409, "UNSUPPORTED_STATE"),   # HALTED seed
        "PAY_82931": None,                          # analyzable control
    }
    for payment_id, (status, code) in [(k, v) for k, v in cases.items() if v]:
        resp = client.post(f"/api/recoveries/{payment_id}/analyze")
        assert resp.status_code == status, (payment_id, resp.text)
        assert resp.json()["error"]["code"] == code


def test_execute_boundary_now_policy_checked(client, merchant_id, db_session):
    from app.repositories import MerchantRepository
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    """Since Phase 5, execute runs the policy engine (never a 501 stub).

    Seeded PAY_82931 is SCHEDULED → payment_state check fails → BLOCKED,
    deterministically, with no provider involvement.
    """
    resp = client.post("/api/recoveries/PAY_82931/execute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "BLOCKED"
    assert body["status"] == "BLOCKED"
    assert any(c["check_name"] == "payment_state" and c["status"] == "FAIL"
               for c in body["checks"])


def test_rank_failed_payments_orders_by_expected_recovery_value(db_session, merchant_id):
    service = RecoveryIntelligenceService(db_session)
    ranked = service.rank_failed_payments(merchant_id)
    if len(ranked) < 2:
        # Ensure at least two ranked candidates exist regardless of seed shape.
        service.analyze(merchant_id, "PAY_82931", now=NOW)
        service.analyze(merchant_id, "PAY_82981", now=NOW)
        ranked = service.rank_failed_payments(merchant_id)
    ervs = [d.expected_recovery_amount for _, d in ranked]
    assert ervs == sorted(ervs, reverse=True)
    assert all(isinstance(e, Decimal) for e in ervs)


def test_no_failure_data_error(client, db_session, merchant_id):
    """An analyzable-status payment without any failure row → NO_FAILURE_DATA."""
    from app.repositories import MerchantRepository
    merchant = MerchantRepository(db_session).get_default_merchant()
    assert merchant is not None
    client.headers["Authorization"] = f"Bearer {create_token(str(merchant.id))}"
    import uuid

    from app.models import Customer
    from app.models.enums import PaymentMethod, PaymentStatus

    merchant_uuid = uuid.UUID(merchant_id)
    customer = db_session.scalars(
        select(Customer).where(Customer.merchant_id == merchant_uuid)
    ).first()
    db_session.add(Payment(
        merchant_id=merchant_uuid,
        customer_id=customer.id,
        external_payment_id="PAY_TEST_NO_FAILURE",
        amount=Decimal("1000.00"),
        currency="INR",
        method=PaymentMethod.UPI,
        status=PaymentStatus.QUEUED,
    ))
    db_session.flush()

    response = client.post("/api/recoveries/PAY_TEST_NO_FAILURE/analyze")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_FAILURE_DATA"
