"""Merchant policy persistence."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MerchantPolicy


class PolicyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_merchant(self, merchant_id: uuid.UUID) -> MerchantPolicy | None:
        stmt = select(MerchantPolicy).where(MerchantPolicy.merchant_id == merchant_id)
        return self._session.scalars(stmt).first()

    def upsert_for_merchant(self, merchant_id: uuid.UUID, policy: MerchantPolicy) -> MerchantPolicy:
        """Replace the merchant's active rule set, bumping the policy version so
        historical evaluations/actions keep pointing at what actually applied."""
        existing = self.get_for_merchant(merchant_id)
        if existing is None:
            policy.merchant_id = merchant_id
            policy.version = 1
            self._session.add(policy)
            return policy
        for field in (
            "maximum_retries",
            "recovery_window_days",
            "minimum_ai_confidence",
            "high_value_threshold",
            "prevent_duplicate_recovery",
            "require_policy_approval",
            "maintain_audit_log",
            "escalate_high_value",
            "failure_rules",
        ):
            setattr(existing, field, getattr(policy, field))
        existing.version = (existing.version or 0) + 1
        return existing
