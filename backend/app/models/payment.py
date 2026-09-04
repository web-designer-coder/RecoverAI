"""Payment model.

Money policy: `amount` is NUMERIC(14,2) in rupees (₹8,499 → 8499.00).
Floating point is never used for storage; conversion to paise integers for the
Razorpay contract happens explicitly at the integration boundary in Phase 3.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import PaymentMethod, PaymentStatus, Priority
from app.models.mixins import TimestampMixin, _uuid_pk

if TYPE_CHECKING:
    from app.models.action import RecoveryAction
    from app.models.customer import Customer
    from app.models.decision import RecoveryDecision
    from app.models.failure import PaymentFailure
    from app.models.merchant import Merchant


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("merchant_id", "external_payment_id", name="uq_payments_merchant_external"),
        Index("ix_payments_merchant_id", "merchant_id"),
        Index("ix_payments_external_payment_id", "external_payment_id"),
        Index("ix_payments_customer_id", "customer_id"),
        Index("ix_payments_status", "status"),
        Index("ix_payments_provider_order_id", "provider_order_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    # Gateway/provider identifier (e.g. PAY_82931 today; a Razorpay payment id
    # in Phase 3). Internal PKs stay opaque UUIDs.
    external_payment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, native_enum=False, length=32),
        name="payment_method",
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=32), nullable=False
    )
    # Number of recovery attempts made so far (frontend `retry_count`).
    attempt_number: Mapped[int] = mapped_column(default=0, nullable=False)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, native_enum=False, length=16), default=Priority.MEDIUM, nullable=False
    )
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Phase 3 — provider state preserved alongside the internal domain status.
    # `status` remains RecoverAI's own lifecycle; these columns keep the raw
    # Razorpay view so reconciliation can compare without guessing.
    provider_order_id: Mapped[str | None] = mapped_column(String(64))
    provider_status: Mapped[str | None] = mapped_column(String(32))
    # Sanitized provider metadata only — never card data, CVV or credentials.
    provider_metadata: Mapped[dict | None] = mapped_column(JSONB)

    merchant: Mapped["Merchant"] = relationship(back_populates="payments")
    customer: Mapped["Customer"] = relationship(back_populates="payments")
    failures: Mapped[List["PaymentFailure"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )
    decisions: Mapped[List["RecoveryDecision"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )
    actions: Mapped[List["RecoveryAction"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
        foreign_keys="RecoveryAction.payment_id",
    )
    recovered_actions: Mapped[List["RecoveryAction"]] = relationship(
        back_populates="recovered_payment",
        foreign_keys="RecoveryAction.recovered_payment_id",
    )
