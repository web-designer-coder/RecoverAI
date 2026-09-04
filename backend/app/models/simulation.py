"""Simulation record — inputs and headline outcomes of one batch simulation.

Phase 2 stores records only; the simulation engine arrives in Phase 6.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import _uuid_pk

if TYPE_CHECKING:
    from app.models.merchant import Merchant


class Simulation(Base):
    __tablename__ = "simulations"
    __table_args__ = (Index("ix_simulations_merchant_id", "merchant_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )

    transactions: Mapped[int] = mapped_column(Integer, nullable=False)
    average_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    failure_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)  # 0..1
    recovery_window_days: Mapped[int] = mapped_column(Integer, nullable=False)

    static_recovery_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    ai_recovery_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    static_recovered_revenue: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    ai_recovered_revenue: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    incremental_revenue: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)

    # Full action breakdown etc., stored from Phase 6 onwards.
    result_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="simulations")
