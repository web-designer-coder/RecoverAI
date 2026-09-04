"""Audit event — append-oriented governance record.

Append-only by architecture AND by database: a trigger created in the initial
migration rejects UPDATE/DELETE on this table (SQLSTATE 55006). The ORM model
deliberately has no updated_at and no mutable helpers; only `audit_repository.append()`
and read queries exist.

No AI chain-of-thought is ever stored here — concise summaries and explainable
metadata only.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ActorType, AuditCategory, AuditEventType
from app.models.mixins import _uuid_pk

if TYPE_CHECKING:
    from app.models.merchant import Merchant


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_merchant_id", "merchant_id"),
        Index("ix_audit_events_payment_id", "payment_id"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    # SET NULL — deleting a payment must never erase audit history.
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL")
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(AuditEventType, native_enum=False, length=40), nullable=False
    )
    category: Mapped[AuditCategory] = mapped_column(
        Enum(AuditCategory, native_enum=False, length=32), nullable=False
    )
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, native_enum=False, length=16), default=ActorType.SYSTEM, nullable=False
    )
    actor_id: Mapped[Optional[str]] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="audit_events")
