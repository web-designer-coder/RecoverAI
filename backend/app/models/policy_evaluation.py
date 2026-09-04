"""Policy evaluation record — immutable history of every authorization run.

One row per policy evaluation. Recovery actions point to the evaluation that
authorized them, and evaluations point to the policy version used, so any
historical execution can be traced to the exact rules that allowed it.
Rows are never mutated or deleted (audit-style).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import _uuid_pk

if TYPE_CHECKING:
    from app.models.decision import RecoveryDecision
    from app.models.payment import Payment
    from app.models.policy import MerchantPolicy


class PolicyEvaluation(Base):
    __tablename__ = "policy_evaluations"
    __table_args__ = (
        Index("ix_policy_evaluations_payment_id", "payment_id"),
        Index("ix_policy_evaluations_decision_id", "recovery_decision_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False
    )
    # The AI decision version that was evaluated (nullable only if a future
    # evaluation type runs without one — executions require it).
    recovery_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recovery_decisions.id")
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="SET NULL")
    )
    # Snapshot of the policy version at evaluation time — policies may change
    # later but historical evaluations keep pointing at what actually applied.
    policy_version: Mapped[str | None] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # APPROVED/BLOCKED/ESCALATED
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checks: Mapped[list | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(String(500))
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    payment: Mapped["Payment"] = relationship(viewonly=True)
    decision_ref: Mapped["RecoveryDecision | None"] = relationship(viewonly=True)
    policy: Mapped["MerchantPolicy | None"] = relationship(viewonly=True)
