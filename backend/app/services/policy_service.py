"""Policy service — validated storage of merchant rule sets.

Phase 2 stores policies only; the enforcement engine (AI recommendation →
policy validation → approval/block/escalation → safe execution) lands in
Phase 5.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import MerchantPolicy
from app.repositories import PolicyRepository
from app.schemas.policy_schemas import PolicyResponse, PolicyUpsertRequest


class PolicyService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.policies = PolicyRepository(session)

    def get_policies(self, merchant_id: uuid.UUID) -> PolicyResponse | None:
        policy = self.policies.get_for_merchant(merchant_id)
        return self._to_response(policy) if policy else None

    def upsert_policies(self, merchant_id: uuid.UUID, request: PolicyUpsertRequest) -> PolicyResponse:
        policy = MerchantPolicy(
            merchant_id=merchant_id,
            maximum_retries=request.maximum_retries,
            recovery_window_days=request.recovery_window_days,
            minimum_ai_confidence=request.minimum_ai_confidence,
            high_value_threshold=request.high_value_threshold,
            prevent_duplicate_recovery=request.prevent_duplicate_recovery,
            require_policy_approval=request.require_policy_approval,
            maintain_audit_log=request.maintain_audit_log,
            escalate_high_value=request.escalate_high_value,
            failure_rules=request.failure_rules,
        )
        saved = self.policies.upsert_for_merchant(merchant_id, policy)
        # Request-scoped sessions from get_db() do not auto-commit; without
        # this a policy update would roll back when the session closes.
        self._session.commit()
        return self._to_response(saved)

    def _to_response(self, policy: MerchantPolicy) -> PolicyResponse:
        return PolicyResponse(
            policy_version=policy.version,
            maximum_retries=policy.maximum_retries,
            recovery_window_days=policy.recovery_window_days,
            minimum_ai_confidence=float(policy.minimum_ai_confidence),
            high_value_threshold=float(policy.high_value_threshold),
            prevent_duplicate_recovery=policy.prevent_duplicate_recovery,
            require_policy_approval=policy.require_policy_approval,
            maintain_audit_log=policy.maintain_audit_log,
            escalate_high_value=policy.escalate_high_value,
            failure_rules=dict(policy.failure_rules),
        )
