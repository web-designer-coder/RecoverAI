"""Recovery action — an actual or scheduled bounded recovery step.

Nothing executes automatically in Phase 2; rows are created only by seeding or
explicit operator endpoints.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import RecoveryActionStatus, RecommendedAction
from app.models.mixins import TimestampMixin, _uuid_pk

if TYPE_CHECKING:
    from app.models.decision import RecoveryDecision
    from app.models.payment import Payment


class RecoveryAction(TimestampMixin, Base):
    __tablename__ = "recovery_actions"
    __table_args__ = (
        Index("ix_recovery_actions_payment_id", "payment_id"),
        Index("ix_recovery_actions_status", "status"),
        Index("ix_recovery_actions_scheduled_at", "scheduled_at"),
        # Database-level duplicate protection: at most one ACTIVE action per
        # payment (PENDING/VERIFYING_POLICY/APPROVED/SCHEDULED/PROCESSING).
        # Succeeded actions block re-execution at the application layer.
        Index(
            "uq_active_action_per_payment",
            "payment_id",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING', 'VERIFYING_POLICY', 'APPROVED', 'SCHEDULED', 'PROCESSING')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recovery_decisions.id")
    )
    # Phase 5: the policy evaluation that authorized this action — every
    # execution is traceable to the exact rules that allowed it.
    policy_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_evaluations.id")
    )
    action_type: Mapped[RecommendedAction] = mapped_column(
        Enum(RecommendedAction, native_enum=False, length=40), nullable=False
    )
    status: Mapped[RecoveryActionStatus] = mapped_column(
        Enum(RecoveryActionStatus, native_enum=False, length=32),
        default=RecoveryActionStatus.PENDING,
        nullable=False,
    )
    # Idempotency key for execution requests (e.g. PAY_x:decision_id:RETRY).
    # UNIQUE at the database level so retries of the same request can never
    # create two provider actions.
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    # Future gateway reference (Razorpay order/payment id) — opaque string now.
    external_reference: Mapped[str | None] = mapped_column(String(128))
    # The payment id of the successful payment via the payment link (if applicable).
    recovered_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id")
    )

    payment: Mapped["Payment"] = relationship(
        back_populates="actions", foreign_keys=[payment_id]
    )
    decision: Mapped[Optional["RecoveryDecision"]] = relationship(back_populates="actions")
    recovered_payment: Mapped[Optional["Payment"]] = relationship(
        back_populates="recovered_actions", foreign_keys=[recovered_payment_id]
    )
