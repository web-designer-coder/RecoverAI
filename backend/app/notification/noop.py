"""No-op notification provider.

Use this in development and test when no real provider is configured.
It does NOT claim delivery — ACTION_REQUIRED is the truthful state.
"""
import logging

from app.notification.provider import (
    NotificationProvider,
    NotificationRequest,
    NotificationResult,
    NotificationStatus,
)

logger = logging.getLogger("recoverai.notification")


class NoOpNotificationProvider(NotificationProvider):
    """No external delivery is performed. Always returns ACTION_REQUIRED.

    Production should configure a real provider (SMTP/SMS/push) before enabling
    external notification delivery.
    """

    def send(self, request: NotificationRequest) -> NotificationResult:
        logger.info(
            "notification no-op: no provider configured — "
            "payment=%s action=%s",
            request.payment_id,
            request.action_type,
        )
        return NotificationResult(
            status=NotificationStatus.ACTION_REQUIRED,
            message=(
                "No notification provider configured. "
                "Production must set NOTIFICATION_PROVIDER with real credentials. "
                "No external delivery was attempted."
            ),
        )
