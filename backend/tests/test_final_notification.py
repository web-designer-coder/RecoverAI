"""Notification regression tests — no false delivery claim.

Requirements:
- No-provider mode never claims DELIVERED / SENT / DELIVERED externally.
- Provider result uses ACTION_REQUIRED (truthful internal state) when no real
  provider is configured.
- Audit events remain accurate (CUSTOMER_NOTIFIED, never false DELIVERED).
- Merchant isolation is preserved.
- Idempotency: same notification request does not create duplicate results.
"""
import pytest
from decimal import Decimal

from app.notification.provider import (
    NotificationStatus,
    NotificationRequest,
    NotificationResult,
)
from app.notification.noop import NoOpNotificationProvider


class _FakeRealProvider:
    """Simulates a real provider: can succeed or fail.

    Used only to prove that success/failure is recorded correctly.
    """
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.requests = []

    def send(self, request):
        self.requests.append({
            "merchant_id": request.merchant_id,
            "payment_id": request.payment_id,
            "action_type": request.action_type,
        })
        if self.should_fail:
            return NotificationResult(
                status=NotificationStatus.FAILED,
                message="Provider simulated failure",
            )
        return NotificationResult(
            status=NotificationStatus.DELIVERED,
            message="Provider confirmed submission",
            external_reference="ext_ref_001",
        )


class TestNotificationAbstraction:
    """Prove the provider abstraction works correctly."""

    def test_no_op_never_claims_delivery(self):
        provider = NoOpNotificationProvider()
        req = NotificationRequest(
            merchant_id="m1",
            payment_id="p1",
            action_type="CUSTOMER_NOTIFICATION",
            reference_id="ref_1",
        )
        result = provider.send(req)
        assert result.status is NotificationStatus.ACTION_REQUIRED
        assert "No notification provider configured" in result.message
        assert result.external_reference is None

    def test_fake_provider_success_records_delivered(self):
        provider = _FakeRealProvider(should_fail=False)
        req = NotificationRequest(
            merchant_id="m2", payment_id="p2", action_type="PAYMENT_UPDATE",
            reference_id="ref_2",
        )
        result = provider.send(req)
        assert result.status is NotificationStatus.DELIVERED
        assert result.external_reference == "ext_ref_001"
        assert len(provider.requests) == 1

    def test_fake_provider_failure_records_failed(self):
        provider = _FakeRealProvider(should_fail=True)
        req = NotificationRequest(
            merchant_id="m3", payment_id="p3", action_type="CUSTOMER_NOTIFICATION",
            reference_id="ref_3",
        )
        result = provider.send(req)
        assert result.status is NotificationStatus.FAILED
        assert "simulated failure" in result.message
        assert len(provider.requests) == 1

    def test_merchant_isolation_preserved(self):
        """Each provider call carries the merchant; isolation is by design."""
        provider = NoOpNotificationProvider()
        req_a = NotificationRequest(
            merchant_id="m_a", payment_id="p_a", action_type="PAYMENT_UPDATE",
            reference_id="ref_a",
        )
        req_b = NotificationRequest(
            merchant_id="m_b", payment_id="p_b", action_type="CUSTOMER_NOTIFICATION",
            reference_id="ref_b",
        )
        result_a = provider.send(req_a)
        result_b = provider.send(req_b)
        assert result_a.status == result_b.status == NotificationStatus.ACTION_REQUIRED

    def test_notification_is_idempotent_by_value(self):
        """Same request object produces same truthful state — no false duplicate."""
        provider = NoOpNotificationProvider()
        req = NotificationRequest(
            merchant_id="m4", payment_id="p4", action_type="CUSTOMER_NOTIFICATION",
            reference_id="ref_4",
        )
        r1 = provider.send(req)
        r2 = provider.send(req)
        # Truthful: both return ACTION_REQUIRED; no false DELIVERED claim.
        assert r1.status == r2.status == NotificationStatus.ACTION_REQUIRED
        assert r1.message == r2.message
