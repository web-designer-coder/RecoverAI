"""Phase 3 webhook security, idempotency, ingestion and ordering tests.

All requests use signed synthetic fixtures (tests/rzp_fixtures.py); no live
Razorpay credentials are involved.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditEvent, Payment, PaymentFailure, WebhookEvent
from app.models.enums import AuditEventType, PaymentStatus
from app.seed import MERCHANT_NAME
from tests.rzp_fixtures import WEBHOOK_SECRET, canonical, event, post, sign


def _merchant(db_session: Session):
    from app.models import Merchant

    return db_session.scalars(
        select(Merchant).where(Merchant.name == MERCHANT_NAME)
    ).one()


def _payment(db_session: Session, pay_id: str) -> Payment | None:
    merchant = _merchant(db_session)
    return db_session.scalars(
        select(Payment).where(
            Payment.merchant_id == merchant.id,
            Payment.external_payment_id == pay_id,
        )
    ).one_or_none()


def _failures(db_session: Session, pay_id: str) -> list[PaymentFailure]:
    payment = _payment(db_session, pay_id)
    if payment is None:
        return []
    return list(payment.failures)


def _audits(db_session: Session, pay_id: str, event_type: AuditEventType | None = None) -> list[AuditEvent]:
    merchant = _merchant(db_session)
    payment = _payment(db_session, pay_id)
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.merchant_id == merchant.id)
        .order_by(AuditEvent.created_at)
    )
    if payment is not None:
        stmt = stmt.where(AuditEvent.payment_id == payment.id)
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    return list(db_session.scalars(stmt))


# ===========================================================================
# Webhook security
# ===========================================================================

class TestWebhookSecurity:
    def test_valid_signature_accepted(self, client, db_session):
        payload = event("payment.failed", "pay_TEST_SEC_OK")
        response = post(client, payload, event_id="evt_sec_ok_1",
                        signature=sign(canonical(payload)))
        assert response.status_code == 200
        assert response.json()["status"] == "processed"
        assert _payment(db_session, "pay_TEST_SEC_OK") is not None

    def test_invalid_signature_rejected(self, client, db_session):
        payload = event("payment.failed", "pay_TEST_SEC_BAD")
        response = post(client, payload, event_id="evt_sec_bad_1",
                        signature="0" * 64)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_SIGNATURE"
        assert _payment(db_session, "pay_TEST_SEC_BAD") is None
        # No ledger entry either — invalid deliveries are never registered.
        ledger = db_session.scalar(
            select(WebhookEvent).where(WebhookEvent.provider_event_id == "evt_sec_bad_1")
        )
        assert ledger is None

    def test_modified_payload_rejected(self, client):
        """Signature computed over the original body must not validate for a
        tampered body — proves verification uses the exact raw bytes."""
        payload = event("payment.failed", "pay_TEST_SEC_TAMPER")
        original_raw = canonical(payload)
        tampered = dict(payload)
        tampered["payload"] = {
            "payment": {"entity": {**payload["payload"]["payment"]["entity"], "amount": 1}}
        }
        response = post(client, tampered, event_id="evt_tamper_1",
                        signature=sign(original_raw))
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_SIGNATURE"

    def test_missing_signature_rejected(self, client):
        response = post(client, event("payment.failed"), event_id="evt_nosig",
                        signature=None)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_SIGNATURE"

    def test_missing_event_id_rejected(self, client, db_session):
        """Without an idempotency key nothing may be processed or stored."""
        payload = event("payment.failed", "pay_TEST_NOEVT")
        response = post(client, payload, event_id="", signature=sign(canonical(payload)))
        assert response.status_code == 400
        assert _payment(db_session, "pay_TEST_NOEVT") is None


# ===========================================================================
# Idempotency
# ===========================================================================

class TestIdempotency:
    def test_duplicate_delivery_does_not_duplicate_records(self, client, db_session):
        payload = event("payment.failed", "pay_TEST_DUP")
        raw = canonical(payload)

        first = post(client, payload, event_id="evt_dup_same", signature=sign(raw))
        assert first.status_code == 200
        assert first.json()["result"] == "PROCESSED"

        second = post(client, payload, event_id="evt_dup_same", signature=sign(raw))
        assert second.status_code == 200  # duplicates are ACKed, not errored
        assert second.json()["result"] == "DUPLICATE_EVENT"

        assert len(_failures(db_session, "pay_TEST_DUP")) == 1
        failed_audits = _audits(db_session, "pay_TEST_DUP", AuditEventType.PAYMENT_FAILED)
        assert len(failed_audits) == 1
        payment = _payment(db_session, "pay_TEST_DUP")
        assert payment.attempt_number == 1  # one attempt, despite two deliveries


# ===========================================================================
# payment.failed mapping
# ===========================================================================

class TestPaymentFailedIngestion:
    def test_creates_payment_and_failure(self, client, db_session):
        payload = event("payment.failed", "pay_TEST_FAIL_001",
                        error_reason="insufficient_fund")
        response = post(client, payload, event_id="evt_fail_001",
                        signature=sign(canonical(payload)))
        assert response.status_code == 200

        payment = _payment(db_session, "pay_TEST_FAIL_001")
        assert payment is not None
        assert payment.status == PaymentStatus.FAILED

        failures = _failures(db_session, "pay_TEST_FAIL_001")
        assert len(failures) == 1
        failure = failures[0]
        assert failure.failure_code == "insufficient_fund"
        assert failure.attempt_number == 1

    def test_amount_conversion_from_paise(self, client, db_session):
        from decimal import Decimal

        post(client, event("payment.failed", "pay_TEST_AMT", amount=849900),
             event_id="evt_amt", signature=sign(canonical(event("payment.failed", "pay_TEST_AMT", amount=849900))))
        payment = _payment(db_session, "pay_TEST_AMT")
        assert payment.amount == Decimal("8499.00")  # 849900 paise → ₹8,499.00

    def test_method_mapping(self, client, db_session):
        from app.models.enums import PaymentMethod

        payload = event("payment.failed", "pay_TEST_METHOD", method="netbanking")
        post(client, payload, event_id="evt_method", signature=sign(canonical(payload)))
        assert _payment(db_session, "pay_TEST_METHOD").method == PaymentMethod.NET_BANKING

    def test_normalized_failure_category(self, client, db_session):
        from app.models.enums import FailureCategory

        payload = event("payment.failed", "pay_TEST_CAT",
                        error_reason="card_expired",
                        error_description="Card expired at time of charge")
        post(client, payload, event_id="evt_cat", signature=sign(canonical(payload)))
        failures = _failures(db_session, "pay_TEST_CAT")
        assert failures[0].failure_category == FailureCategory.EXPIRED_CARD

    def test_unknown_failure_maps_to_other(self, client, db_session):
        from app.models.enums import FailureCategory

        payload = event("payment.failed", "pay_TEST_OTHER",
                        error_reason="something_novel",
                        error_description="Completely unknown gateway text")
        post(client, payload, event_id="evt_other", signature=sign(canonical(payload)))
        failures = _failures(db_session, "pay_TEST_OTHER")
        assert failures[0].failure_category == FailureCategory.OTHER

    def test_audit_event_created_with_concise_metadata(self, client, db_session):
        payload = event("payment.failed", "pay_TEST_AUDIT")
        post(client, payload, event_id="evt_audit", signature=sign(canonical(payload)))
        audits = _audits(db_session, "pay_TEST_AUDIT", AuditEventType.PAYMENT_FAILED)
        assert len(audits) == 1
        audit = audits[0]
        meta = audit.meta or {}
        assert meta.get("provider") == "razorpay"
        assert meta.get("provider_event_id") == "evt_audit"
        assert meta.get("processing_result") == "CREATED"


# ===========================================================================
# payment.captured / authorized
# ===========================================================================

class TestPaymentCaptured:
    def test_captured_marks_recovered_with_audit(self, client, db_session):
        payload = event("payment.captured", "pay_TEST_CAP",
                        status="captured", error_reason=None)
        post(client, payload, event_id="evt_cap_1", signature=sign(canonical(payload)))

        payment = _payment(db_session, "pay_TEST_CAP")
        assert payment.status == PaymentStatus.RECOVERED
        assert len(_audits(db_session, "pay_TEST_CAP", AuditEventType.PAYMENT_RECOVERED)) == 1

    def test_duplicate_capture_does_not_double_count(self, client, db_session):
        payload = event("payment.captured", "pay_TEST_CAP2",
                        status="captured", error_reason=None)
        raw = canonical(payload)
        post(client, payload, event_id="evt_cap2_a", signature=sign(raw))
        # Same successful flow, different delivery id (e.g. Razorpay replay variant)
        post(client, payload, event_id="evt_cap2_b", signature=sign(raw))

        recovered = _audits(db_session, "pay_TEST_CAP2", AuditEventType.PAYMENT_RECOVERED)
        assert len(recovered) == 1  # no double counting
        assert _payment(db_session, "pay_TEST_CAP2").status == PaymentStatus.RECOVERED

    def test_order_paid_intentionally_unsupported(self, client, db_session):
        """order.paid is deferred by design (correlation happens on payment id);
        it must be acknowledged without creating anything."""
        payload = {
            "event": "order.paid",
            "payload": {"order": {"entity": {"id": "order_TEST_X", "amount": 100000}}},
        }
        response = post(client, payload, event_id="evt_orderpaid",
                        signature=sign(canonical(payload)))
        assert response.status_code == 200
        assert response.json()["result"] == "UNSUPPORTED_EVENT"


class TestPaymentAuthorized:
    def test_authorized_is_not_recovered(self, client, db_session):
        payload = event("payment.authorized", "pay_TEST_AUTH",
                        status="authorized", error_reason=None)
        post(client, payload, event_id="evt_auth_1", signature=sign(canonical(payload)))

        payment = _payment(db_session, "pay_TEST_AUTH")
        assert payment.status == PaymentStatus.AUTHORIZED
        assert payment.status != PaymentStatus.RECOVERED
        assert len(_audits(db_session, "pay_TEST_AUTH", AuditEventType.PAYMENT_AUTHORIZED)) == 1


# ===========================================================================
# Event ordering
# ===========================================================================

class TestOrdering:
    def test_stale_failed_after_captured_does_not_downgrade(self, client, db_session):
        captured = event("payment.captured", "pay_TEST_ORDER",
                         status="captured", error_reason=None)
        post(client, captured, event_id="evt_ord_cap", signature=sign(canonical(captured)))
        assert _payment(db_session, "pay_TEST_ORDER").status == PaymentStatus.RECOVERED

        stale_failed = event("payment.failed", "pay_TEST_ORDER")
        response = post(client, stale_failed, event_id="evt_ord_fail",
                        signature=sign(canonical(stale_failed)))
        assert response.status_code == 200
        assert response.json()["result"] == "STALE_IGNORED"

        payment = _payment(db_session, "pay_TEST_ORDER")
        assert payment.status == PaymentStatus.RECOVERED          # state preserved
        assert list(payment.failures) == []                       # no failure row written
        assert _audits(db_session, "pay_TEST_ORDER", AuditEventType.PAYMENT_FAILED) == []

        ledger = db_session.scalar(
            select(WebhookEvent).where(WebhookEvent.provider_event_id == "evt_ord_fail")
        )
        assert ledger.result == "STALE_IGNORED"

    def test_different_events_never_treated_as_duplicates(self, client, db_session):
        """Two genuinely distinct deliveries must each process."""
        p1 = event("payment.failed", "pay_TEST_MULTI_A")
        p2 = event("payment.captured", "pay_TEST_MULTI_B", status="captured",
                   error_reason=None)
        r1 = post(client, p1, event_id="evt_multi_1", signature=sign(canonical(p1)))
        r2 = post(client, p2, event_id="evt_multi_2", signature=sign(canonical(p2)))
        assert r1.json()["status"] == "processed"
        assert r2.json()["status"] == "processed"


# ===========================================================================
# Database-level guarantees
# ===========================================================================

class TestDatabaseGuarantees:
    def test_webhook_event_unique_constraint(self, db_session):
        db_session.add(WebhookEvent(
            provider="razorpay", provider_event_id="evt_uq_x",
            event_type="payment.failed", payload_hash="a" * 64,
        ))
        db_session.commit()
        db_session.add(WebhookEvent(
            provider="razorpay", provider_event_id="evt_uq_x",
            event_type="payment.failed", payload_hash="b" * 64,
        ))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_transaction_rollback_prevents_partial_processing(self, client, db_session, monkeypatch):
        """If processing dies midway, nothing partial survives; the retry then
        succeeds cleanly."""
        calls = {"n": 0}

        from app.services.payment_ingestion_service import PaymentIngestionService

        original = PaymentIngestionService.handle_payment_failed

        def flaky(self, merchant, payload):
            result = original(self, merchant, payload)
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated mid-processing crash")
            return result

        monkeypatch.setattr(PaymentIngestionService, "handle_payment_failed", flaky)

        payload = event("payment.failed", "pay_TEST_ROLLBACK")
        raw = canonical(payload)

        broken = post(client, payload, event_id="evt_rb_1", signature=sign(raw))
        assert broken.status_code == 500  # non-2xx → provider will retry

        # No half-created rows.
        assert _payment(db_session, "pay_TEST_ROLLBACK") is None
        ledger = db_session.scalar(
            select(WebhookEvent).where(WebhookEvent.provider_event_id == "evt_rb_1")
        )
        assert ledger is not None and ledger.status.value == "FAILED"

        monkeypatch.setattr(PaymentIngestionService, "handle_payment_failed", original)
        retried = post(client, payload, event_id="evt_rb_1", signature=sign(raw))
        assert retried.status_code == 200
        assert retried.json()["result"] == "PROCESSED"
        assert _payment(db_session, "pay_TEST_ROLLBACK") is not None
        assert len(_failures(db_session, "pay_TEST_ROLLBACK")) == 1
