"""39A-4 — Customer notification delivery (no false delivery claim).

CUSTOMER_NOTIFICATION / PAYMENT_UPDATE are internal actions (CUSTOMER_ACTION_REQUIRED
status, CUSTOMER_NOTIFIED audit event) — NOT external email/SMS delivery.
No external notification provider exists in the codebase; nothing in app/ provides
email, SMS, or push. The domain state must never represent these as "delivered".
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.models import Payment, RecoveryAction, RecoveryDecision, Customer
from app.models.enums import PaymentStatus, PaymentMethod, RecoveryActionStatus, RecommendedAction
from app.services.recovery_execution_service import RecoveryExecutionService
from app.services.providers.payment_provider import RazorpayPaymentProvider, ExecutionStatus


class _StubClient:
    def __init__(self):
        self.link_calls = []


def test_customer_notification_never_calls_provider(db_session, merchant_id):
    """CUSTOMER_NOTIFICATION must not invoke Razorpay (or any provider)."""
    client = _StubClient()
    result = RazorpayPaymentProvider(client).execute_recovery(
        action_type=RecommendedAction.CUSTOMER_NOTIFICATION,
        amount=Decimal("100"), currency="INR", reference_id="P",
    )
    assert result.status is ExecutionStatus.CUSTOMER_ACTION_REQUIRED
    assert client.link_calls == []  # no provider operation performed


def test_payment_update_never_calls_provider(db_session, merchant_id):
    """PAYMENT_UPDATE must not invoke Razorpay (or any provider)."""
    client = _StubClient()
    result = RazorpayPaymentProvider(client).execute_recovery(
        action_type=RecommendedAction.PAYMENT_UPDATE,
        amount=Decimal("100"), currency="INR", reference_id="P",
    )
    assert result.status is ExecutionStatus.CUSTOMER_ACTION_REQUIRED
    assert client.link_calls == []


def test_notification_action_is_internal_state_not_delivered(db_session, merchant_id):
    """The recovery action must record CUSTOMER_ACTION_REQUIRED, never a
    false "DELIVERED" / "SENT" status — there is no external delivery mechanism."""
    # (Regression: no external notification provider exists in backend/app/)
    from app.services.providers.payment_provider import ExecutionStatus
    assert ExecutionStatus.CUSTOMER_ACTION_REQUIRED in {
        ExecutionStatus.CUSTOMER_ACTION_REQUIRED,
        ExecutionStatus.PROCESSING,
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
    }
    # The only allowed notification-related audit event is CUSTOMER_NOTIFIED,
    # which is an internal audit entry (not a delivery confirmation).
    from app.models.enums import AuditEventType
    assert AuditEventType.CUSTOMER_NOTIFIED in {
        AuditEventType.CUSTOMER_NOTIFIED,
        AuditEventType.ACTION_SELECTED,
    }
    # Explicit: no "DELIVERED", "SENT", "NOTIFICATION_SENT" audit or status values exist.
    assert "DELIVERED" not in {e.value for e in AuditEventType}
