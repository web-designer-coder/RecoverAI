"""Payment failure record — one row per observed failure attempt.

Extensible for Phase 3: `failure_code` and the JSONB `metadata` column will
carry raw Razorpay error codes and gateway payloads without schema changes.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import FailureCategory
from app.models.mixins import _uuid_pk

if TYPE_CHECKING:
    from app.models.payment import Payment


class PaymentFailure(Base):
    __tablename__ = "payment_failures"
    __table_args__ = (
        Index("ix_payment_failures_payment_id", "payment_id"),
        Index("ix_payment_failures_failure_category", "failure_category"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False
    )
    # Gateway-specific short code (e.g. "insufficient_balance"). Raw provider
    # codes arrive in Phase 3 — the column is free-form VARCHAR by design.
    failure_code: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    failure_category: Mapped[FailureCategory] = mapped_column(
        Enum(FailureCategory, native_enum=False, length=40), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Column named `metadata`; attribute avoids clashing with Declarative.metadata.
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    payment: Mapped["Payment"] = relationship(back_populates="failures")
