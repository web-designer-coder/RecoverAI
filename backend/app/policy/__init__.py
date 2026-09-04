"""RecoverAI policy engine — AI recommends, policy authorizes.

Independent of FastAPI routes: pure checks/evaluator plus one DB-facing
service. All authorization rules live here; nothing elsewhere in the
codebase may bypass them.
"""

from app.policy.evaluator import POLICY_ENGINE_VERSION, evaluate
from app.policy.models import (
    CheckStatus,
    PolicyCheckResult,
    PolicyContext,
    PolicyDecision,
)
from app.policy.service import PolicyService

__all__ = [
    "POLICY_ENGINE_VERSION",
    "PolicyService",
    "PolicyContext",
    "PolicyDecision",
    "PolicyCheckResult",
    "CheckStatus",
    "evaluate",
]
