"""Notification provider abstraction.

No external provider is configured by default. Production must set
NOTIFICATION_PROVIDER=... with real credentials. Without it, notifications
remain internal CUSTOMER_ACTION_REQUIRED state — never falsely delivered.
"""
from dataclasses import dataclass, field
from enum import Enum


class NotificationStatus(str, Enum):
    ACTION_REQUIRED = "ACTION_REQUIRED"      # internal — customer must act
    DELIVERY_REQUESTED = "DELIVERY_REQUESTED"  # submission attempted
    DELIVERED = "DELIVERED"                # provider confirmed
    FAILED = "FAILED"                      # provider returned error


@dataclass
class NotificationRequest:
    merchant_id: str
    payment_id: str
    action_type: str
    reference_id: str
    message: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class NotificationResult:
    status: NotificationStatus
    message: str = ""
    external_reference: str | None = None
    metadata: dict = field(default_factory=dict)


class NotificationProvider:
    def send(self, request: NotificationRequest) -> NotificationResult:
        raise NotImplementedError("Notification provider must implement send()")
