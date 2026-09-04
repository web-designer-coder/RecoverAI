"""Policy service — loads context, runs the evaluator, persists the outcome.

This is the ONLY entry point other services should use for authorization.
It owns database access; evaluator/checks stay pure. Every evaluation appends
one immutable PolicyEvaluation row plus audit events, and commits.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import PolicyEvaluation
from app.models.enums import ActorType, AuditCategory, AuditEventType
from app.models.policy import MerchantPolicy
from app.policy.evaluator import evaluate
from app.policy.models import PolicyContext, PolicyDecision
from app.repositories import (
    AuditRepository,
    PaymentRepository,
    PolicyRepository,
    RecoveryRepository,
)

logger = logging.getLogger("recoverai.policy")


class PolicyService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.payments = PaymentRepository(session)
        self.policies = PolicyRepository(session)
        self.recovery = RecoveryRepository(session)
        self.audit = AuditRepository(session)

    def evaluate_for_payment(
        self,
        merchant_id: uuid.UUID,
        external_payment_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[PolicyDecision, PolicyEvaluation]:
        """Full authorization run for a payment's CURRENT AI decision.

        Raises AppError PAYMENT_NOT_FOUND / NO_RECOVERY_DECISION /
        POLICY_NOT_CONFIGURED. Never approves silently.
        """
        from app.utils.errors import AppError, payment_not_found

        now = now or datetime.now(timezone.utc)
        payment = self.payments.get_by_external_id(merchant_id, external_payment_id)
        if payment is None:
            raise payment_not_found(external_payment_id)

        decision = self.recovery.latest_decisions([payment.id], merchant_id).get(payment.id)
        if decision is None:
            raise AppError(
                code="NO_RECOVERY_DECISION",
                message=f"Payment {external_payment_id} has no AI recovery decision. "
                        "Run analysis first — policy validation never triggers analysis.",
                status_code=409,
            )

        rules = self.policies.get_for_merchant(merchant_id)
        # Note: a missing policy is NOT an error here by design — the evaluator
        # turns it into a BLOCKED decision with POLICY_NOT_CONFIGURED so the
        # outcome is persisted and auditable like any other block.

        failure = self.payments.list_latest_failures([payment.id]).get(payment.id)
        actions = self.recovery.actions_for_payments([payment.id], merchant_id).get(payment.id, [])

        context = PolicyContext(
            payment=payment,
            payment_failure=failure,
            recovery_decision=decision,
            decision_is_current=True,  # loaded via latest_decisions → current by construction
            policy_rules=rules,
            existing_recovery_actions=actions,
            retry_count=payment.attempt_number,
            payment_age_days=max(
                0.0, (now - payment.created_at).total_seconds() / 86400.0
            ),
            recovery_window_at=decision.optimal_recovery_at,
            ai_confidence=float(decision.ai_confidence) if decision.ai_confidence is not None else None,
            recovery_probability=(
                float(decision.recovery_probability)
                if decision.recovery_probability is not None else None
            ),
            recommended_action=decision.recommended_action,
            payment_amount=payment.amount,
            failure_category=failure.failure_category.value if failure else None,
            now=now,
        )

        result = evaluate(context)
        evaluation = self._persist(payment, decision, rules, result)

        self._audit(payment, decision, result)
        self._session.commit()

        logger.info(
            "policy evaluated payment=%s action=%s policy=%s outcome=%s",
            external_payment_id,
            decision.recommended_action.value if decision.recommended_action else "?",
            result.policy_version,
            result.decision,
        )
        return result, evaluation

    # -- internals -----------------------------------------------------------

    def _persist(self, payment, decision, rules: MerchantPolicy | None,
                 result: PolicyDecision) -> PolicyEvaluation:
        row = PolicyEvaluation(
            payment_id=payment.id,
            recovery_decision_id=decision.id,
            policy_id=rules.id if rules else None,
            policy_version=result.policy_version,
            decision=result.decision,
            allowed=result.allowed,
            checks=[c.to_dict() for c in result.checks],
            reason=result.reason[:500],
            evaluated_at=result.evaluated_at,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def _audit(self, payment, decision, result: PolicyDecision) -> None:
        metadata = {
            "policy_version": result.policy_version,
            "decision_id": str(decision.id),
            "model_version": decision.model_version,
            "checks": [c.to_dict() for c in result.checks],
        }
        common = dict(
            merchant_id=payment.merchant_id,
            payment_id=payment.id,
            actor_type=ActorType.SYSTEM,
        )
        self.audit.append(
            **common,
            event_type=AuditEventType.POLICY_CHECK,
            category=AuditCategory.POLICY,
            summary=f"Policy check — {payment.external_payment_id}: {result.decision}",
            metadata=metadata,
        )
        if result.decision == "BLOCKED":
            self.audit.append(
                **common,
                event_type=AuditEventType.POLICY_BLOCKED,
                category=AuditCategory.POLICY,
                summary=f"Recovery blocked by policy — {payment.external_payment_id}",
                metadata={**metadata, "reason": result.reason},
            )
        elif result.decision == "ESCALATED":
            self.audit.append(
                **common,
                event_type=AuditEventType.POLICY_ESCALATED,
                category=AuditCategory.POLICY,
                summary=f"Recovery escalated by policy — {payment.external_payment_id}",
                metadata={**metadata, "reason": result.reason},
            )
