"""Merchant recovery policies.

The failure-category → action matrix is stored as a JSONB `failure_rules`
column. It is validated by `schemas/policy_schemas.FailureRuleMap` on the way
in and out, which keeps the representation maintainable without a join table
for six fixed categories.
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Numeric, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import RecommendedAction
from app.models.mixins import TimestampMixin, _uuid_pk

if TYPE_CHECKING:
    from app.models.merchant import Merchant


class MerchantPolicy(TimestampMixin, Base):
    __tablename__ = "policies"
    __table_args__ = (Index("ix_policies_merchant_id", "merchant_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    # One active policy set per merchant for this phase.
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, unique=True
    )
    # Bumped on every policy update; evaluations/actions snapshot the version
    # they used so rule changes never rewrite history.
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    maximum_retries: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # Percentage 0–100 (frontend `minConfidence`).
    minimum_ai_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    high_value_threshold: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    prevent_duplicate_recovery: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_policy_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    maintain_audit_log: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    escalate_high_value: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # {FailureCategory value: RecommendedAction value} — validated by schema.
    failure_rules: Mapped[dict] = mapped_column(JSONB, nullable=False)

    merchant: Mapped["Merchant"] = relationship(back_populates="policies")
