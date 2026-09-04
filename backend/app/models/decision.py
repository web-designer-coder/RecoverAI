"""Recovery decision — the (future) AI engine's output for a payment.

Phase 2 stores decisions only; every intelligence-bearing field is nullable so
rows can exist before the Phase 4 engine populates them. No chain-of-thought:
only concise diagnosis text and explainable numeric signals are persisted.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import RecommendedAction
from app.models.mixins import _uuid_pk

if TYPE_CHECKING:
    from app.models.action import RecoveryAction
    from app.models.payment import Payment


class RecoveryDecision(Base):
    __tablename__ = "recovery_decisions"
    __table_args__ = (Index("ix_recovery_decisions_payment_id", "payment_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False
    )
    # Human-readable one-line diagnosis ("Insufficient Funds").
    diagnosis: Mapped[str | None] = mapped_column(String(200))
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # 0..1
    recovery_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # 0..1
    recommended_action: Mapped[RecommendedAction | None] = mapped_column(
        Enum(RecommendedAction, native_enum=False, length=40)
    )
    expected_recovery_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    optimal_recovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str | None] = mapped_column(String(64))

    # Phase 4 intelligence fields — structured, auditable, no chain-of-thought.
    # signals holds concise evidence entries (name/value/impact/category);
    # explanation is the deterministic natural-language rendering.
    signals: Mapped[list | None] = mapped_column(JSONB)
    explanation: Mapped[str | None] = mapped_column(Text)
    optimal_window: Mapped[str | None] = mapped_column(String(16))
    data_sufficiency: Mapped[str | None] = mapped_column(String(8))
    # Append-only versioning: 1,2,3… per payment. The CURRENT version is the
    # highest version_number (timestamps alone can tie across transactions).
    version_number: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    payment: Mapped["Payment"] = relationship(back_populates="decisions")
    actions: Mapped[List["RecoveryAction"]] = relationship(back_populates="decision")
