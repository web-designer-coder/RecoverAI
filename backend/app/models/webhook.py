"""Webhook event ledger — persistent idempotency for provider deliveries.

Every Razorpay webhook delivery is registered here before processing. The
UNIQUE(provider, provider_event_id) constraint is the idempotency backbone:
a replayed delivery can never create a second payment failure, audit event or
state transition.

Payload policy (Phase 3, §18): we store only the SHA-256 hash of the raw body,
never the payload itself. The hash is enough to prove two deliveries carried
identical bytes while keeping this table free of payment data. Retention
intent: debugging rows may be pruned after ~30 days once a retention worker
exists (not built in this phase).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import _uuid_pk


class WebhookStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"      # registered, processing not yet confirmed
    PROCESSED = "PROCESSED"    # handled successfully (result says how)
    FAILED = "FAILED"          # processing raised; safe to retry


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_webhook_events_provider_event"),
        Index("ix_webhook_events_provider", "provider"),
        Index("ix_webhook_events_status", "status"),
        Index("ix_webhook_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(32), default="razorpay", nullable=False)
    # Primary deduplication key: the x-razorpay-event-id delivery header.
    provider_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WebhookStatus] = mapped_column(
        Enum(WebhookStatus, native_enum=False, length=16), default=WebhookStatus.RECEIVED,
        nullable=False,
    )
    # How processing ended: PROCESSED | DUPLICATE_EVENT | UNSUPPORTED_EVENT |
    # STALE_IGNORED | ALREADY_RECOVERED ... (free-form short token).
    result: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    # SHA-256 of the exact raw request bytes — no sensitive payload stored.
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
