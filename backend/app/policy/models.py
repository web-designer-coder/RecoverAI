"""Policy engine core types — pure dataclasses, no database, no FastAPI.

Separation of responsibilities (Phase 5 architectural rule):

    AI RECOMMENDS  →  POLICY AUTHORIZES  →  EXECUTION EXECUTES  →  AUDIT RECORDS

The evaluator consumes a fully-loaded PolicyContext and returns a PolicyDecision.
It never queries the database; callers load everything up front.
"""

import enum
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.models import Payment, PaymentFailure, RecoveryAction, RecoveryDecision
from app.models.enums import RecommendedAction
from app.models.policy import MerchantPolicy


class CheckStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"                    # hard block — can never be downgraded
    ESCALATE = "ESCALATE"            # needs human/config path — no auto-approval
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class PolicyCheckResult:
    check_name: str
    status: CheckStatus
    message: str
    severity: str = "info"           # info | warning | critical
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "status": self.status.value,
            "message": self.message,
            "severity": self.severity,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class PolicyDecision:
    decision: str                    # APPROVED | BLOCKED | ESCALATED (PolicyOutcome value)
    allowed: bool
    reason: str
    checks: list[PolicyCheckResult]
    policy_version: str
    evaluated_at: datetime

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "allowed": self.allowed,
            "reason": self.reason,
            "checks": [c.to_dict() for c in self.checks],
            "policy_version": self.policy_version,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


@dataclass(frozen=True)
class PolicyContext:
    """Everything policy evaluation needs, loaded by the caller beforehand."""

    payment: Payment
    payment_failure: PaymentFailure | None
    recovery_decision: RecoveryDecision | None
    decision_is_current: bool         # decision is the payment's latest version
    policy_rules: MerchantPolicy | None
    existing_recovery_actions: list[RecoveryAction]

    # Convenience projections (kept explicit so checks stay declarative).
    retry_count: int
    payment_age_days: float
    recovery_window_at: datetime | None      # AI's optimal_recovery_at
    ai_confidence: float | None              # 0..1 — NEVER conflated with probability
    recovery_probability: float | None       # 0..1
    recommended_action: RecommendedAction | None
    payment_amount: Decimal
    failure_category: str | None
    now: datetime                            # injected UTC clock
