"""Phase 3 provider-client and reconciliation tests.

The Razorpay HTTP layer is exercised through httpx.MockTransport — no network
access, no live credentials (test keys are injected directly).
"""

import httpx
import pytest
from decimal import Decimal
from sqlalchemy import select

from app.models import Merchant, Payment, Customer
from app.models.enums import PaymentMethod, PaymentStatus, Priority
from app.seed import MERCHANT_NAME
from app.services.payment_reconciliation_service import (
    PaymentReconciliationService,
    ReconciliationResult,
)
from app.services.providers.razorpay_client import (
    RazorpayAuthError,
    RazorpayClient,
    RazorpayNotConfigured,
    RazorpayNotFound,
    RazorpayTimeout,
    RazorpayUnavailable,
)

TEST_KEY_ID = "rzp_test_1FAKEKEYID000000"
TEST_KEY_SECRET = "fake_test_secret_for_unit_tests"


def _client(handler) -> RazorpayClient:
    return RazorpayClient(
        key_id=TEST_KEY_ID,
        key_secret=TEST_KEY_SECRET,
        transport=httpx.MockTransport(handler),
    )


class TestRazorpayClient:
    def test_successful_fetch(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={
                "id": "pay_TEST_OK", "status": "captured", "amount": 849900,
                "currency": "INR", "method": "upi",
            })

        client = _client(handler)
        payment = client.get_payment("pay_TEST_OK")
        client.close()

        assert payment["id"] == "pay_TEST_OK"
        assert captured["path"] == "/v1/payments/pay_TEST_OK"
        # Basic auth is attached for the provider call.
        assert captured["auth"] is not None

    def test_not_found(self):
        client = _client(lambda request: httpx.Response(404, json={"error": {}}))
        with pytest.raises(RazorpayNotFound):
            client.get_payment("pay_TEST_MISSING")
        client.close()

    def test_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=request)

        client = _client(handler)
        with pytest.raises(RazorpayTimeout):
            client.get_payment("pay_TEST_SLOW")
        client.close()

    def test_authentication_failure(self):
        client = _client(lambda request: httpx.Response(401, json={}))
        with pytest.raises(RazorpayAuthError):
            client.get_payment("pay_TEST_AUTH")
        client.close()

    def test_server_error_is_structured(self):
        client = _client(lambda request: httpx.Response(503, json={}))
        with pytest.raises(RazorpayUnavailable):
            client.get_payment("pay_TEST_5XX")
        client.close()

    def test_missing_credentials_fail_fast(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setenv("RAZORPAY_KEY_ID", "")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
        get_settings.cache_clear()
        try:
            with pytest.raises(RazorpayNotConfigured):
                RazorpayClient()
        finally:
            get_settings.cache_clear()


# ===========================================================================
# Reconciliation service boundary (no worker — invoked directly)
# ===========================================================================

def _merchant(db_session) -> Merchant:
    return db_session.scalars(select(Merchant).where(Merchant.name == MERCHANT_NAME)).one()


def _seed_local_payment(db_session, pay_id: str, status: PaymentStatus) -> Payment:
    merchant = _merchant(db_session)
    customer = Customer(
        merchant_id=merchant.id,
        external_customer_id=f"CUST_RECON_{pay_id[-6:]}",
    )
    db_session.add(customer)
    db_session.flush()
    payment = Payment(
        merchant_id=merchant.id,
        customer_id=customer.id,
        external_payment_id=pay_id,
        amount=Decimal("1000.00"),
        currency="INR",
        method=PaymentMethod.UPI,
        status=status,
        attempt_number=0,
        priority=Priority.MEDIUM,
    )
    db_session.add(payment)
    db_session.commit()
    return payment


def _recon_client(provider_status: str) -> RazorpayClient:
    return _client(lambda request: httpx.Response(200, json={
        "id": "pay_TEST_RECON", "status": provider_status,
        "amount": 100000, "currency": "INR", "method": "upi",
    }))


class TestReconciliation:
    def test_reconciliation_updates_local_state_and_audits(self, db_session):
        from app.models import AuditEvent
        from app.models.enums import AuditEventType

        payment = _seed_local_payment(db_session, "pay_TEST_RECON", PaymentStatus.FAILED)
        merchant = _merchant(db_session)

        result = PaymentReconciliationService(db_session, _recon_client("captured")) \
            .reconcile(merchant, "pay_TEST_RECON")

        assert isinstance(result, ReconciliationResult)
        assert result.changed is True
        assert result.local_status_after == PaymentStatus.RECOVERED

        audit = db_session.scalar(
            select(AuditEvent)
            .where(AuditEvent.payment_id == payment.id)
            .where(AuditEvent.event_type == AuditEventType.PROVIDER_SYNC)
        )
        assert audit is not None
        assert (audit.meta or {}).get("processing_result") == "RECONCILED"

    def test_reconciliation_does_not_downgrade_recovered(self, db_session):
        _seed_local_payment(db_session, "pay_TEST_RECON2", PaymentStatus.RECOVERED)
        merchant = _merchant(db_session)

        result = PaymentReconciliationService(db_session, _recon_client("failed")) \
            .reconcile(merchant, "pay_TEST_RECON2")

        assert result.changed is False
        assert result.note == "STALE_IGNORED"
        assert result.local_status_after == PaymentStatus.RECOVERED
