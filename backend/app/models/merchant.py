"""Merchant model."""

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Environment, MerchantStatus
from app.models.mixins import TimestampMixin, _uuid_pk

if TYPE_CHECKING:
    from app.models.audit import AuditEvent
    from app.models.customer import Customer
    from app.models.payment import Payment
    from app.models.policy import MerchantPolicy
    from app.models.simulation import Simulation


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[MerchantStatus] = mapped_column(
        Enum(MerchantStatus, native_enum=False, length=32),
        default=MerchantStatus.ACTIVE,
        nullable=False,
    )
    # Phase 2 runs in TEST mode; LIVE is reserved for production onboarding.
    environment: Mapped[Environment] = mapped_column(
        Enum(Environment, native_enum=False, length=16),
        default=Environment.TEST,
        nullable=False,
    )

    # Authentication (hashed, never plaintext)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Razorpay Test Mode credentials (encrypted at rest)
    razorpay_key_id: Mapped[str] = mapped_column(String(100), nullable=True)
    razorpay_key_secret_encrypted: Mapped[str] = mapped_column(String(500), nullable=True)
    # Razorpay Webhook secret (encrypted at rest)
    razorpay_webhook_secret_encrypted: Mapped[str] = mapped_column(String(500), nullable=True)
    razorpay_webhook_configured: Mapped[bool] = mapped_column(default=False, nullable=False)

    customers: Mapped[List["Customer"]] = relationship(back_populates="merchant")
    payments: Mapped[List["Payment"]] = relationship(back_populates="merchant")
    policies: Mapped[List["MerchantPolicy"]] = relationship(back_populates="merchant")
    audit_events: Mapped[List["AuditEvent"]] = relationship(back_populates="merchant")
    simulations: Mapped[List["Simulation"]] = relationship(back_populates="merchant")