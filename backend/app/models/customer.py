"""Customer model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import _uuid_pk

if TYPE_CHECKING:
    from app.models.merchant import Merchant
    from app.models.payment import Payment


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("merchant_id", "external_customer_id", name="uq_customers_merchant_external"),
        Index("ix_customers_merchant_id", "merchant_id"),
        Index("ix_customers_external_customer_id", "external_customer_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    external_customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="customers")
    payments: Mapped[List["Payment"]] = relationship(back_populates="customer")
