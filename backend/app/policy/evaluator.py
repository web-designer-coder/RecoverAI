"""Policy evaluator — composes the check library into one PolicyDecision.

Deterministic evaluation order (documented in docs/policy-engine.md):

    1. payment_state          6. retry_limit
    2. failure_exists         7. recovery_window
    3. ai_decision_exists     8. ai_confidence
    4. ai_decision_current    9. action_compatibility
    5. —                     10. duplicate_recovery
                            11. high_value
                            12. policy_approval

No short-circuiting: every applicable check runs, so the UI/audit see ALL
failures at once.

Decision precedence: any FAIL → BLOCKED; else any ESCALATE → ESCALATED;
else APPROVED. Hard blocks can therefore never be downgraded to escalation,
and escalation never overrides a block:

    BLOCKED  >  ESCALATED  >  APPROVED
"""

from app.models.enums import PolicyOutcome
from app.policy import checks
from app.policy.models import CheckStatus, PolicyCheckResult, PolicyContext, PolicyDecision

POLICY_ENGINE_VERSION = "policy-engine-v1"


def evaluate(ctx: PolicyContext) -> PolicyDecision:
    rules = ctx.policy_rules

    if rules is None:
        # Missing policy must fail safe — never silently approve.
        missing = PolicyCheckResult(
            "policy_exists", CheckStatus.FAIL,
            "POLICY_NOT_CONFIGURED — no merchant policy exists; refusing to approve.",
            severity="critical",
        )
        return PolicyDecision(
            decision=PolicyOutcome.BLOCKED.value,
            allowed=False,
            reason="No merchant policy is configured.",
            checks=[missing],
            policy_version="none",
            evaluated_at=ctx.now,
        )

    results = [
        checks.check_payment_state(ctx),
        checks.check_failure_exists(ctx),
        checks.check_ai_decision_exists(ctx),
        checks.check_ai_decision_current(ctx),
    ]
    # Rule-dependent checks only make sense with an AI decision present;
    # they still run and report NOT_APPLICABLE rather than being skipped.
    results += [
        checks.check_retry_limit(ctx, rules.maximum_retries),
        (
            checks.check_recovery_window(ctx, rules.recovery_window_days)
            if ctx.payment_failure is not None
            else PolicyCheckResult(
                "recovery_window", CheckStatus.NOT_APPLICABLE, "No failure to measure the window from."
            )
        ),
        checks.check_ai_confidence(ctx, rules.minimum_ai_confidence),
        checks.check_action_compatibility(ctx),
        checks.check_duplicate_recovery(ctx, rules.prevent_duplicate_recovery),
        checks.check_high_value(ctx, rules.high_value_threshold, rules.escalate_high_value),
        checks.check_policy_approval(ctx, rules.require_policy_approval),
    ]

    failed = [r for r in results if r.status is CheckStatus.FAIL]
    escalations = [r for r in results if r.status is CheckStatus.ESCALATE]

    if failed:
        decision = PolicyOutcome.BLOCKED.value
        allowed = False
        reason = f"Blocked by {len(failed)} check(s): " + ", ".join(r.check_name for r in failed) + "."
    elif escalations:
        decision = PolicyOutcome.ESCALATED.value
        allowed = False
        reason = "; ".join(r.message for r in escalations)
    else:
        decision = PolicyOutcome.APPROVED.value
        allowed = True
        reason = "All policy checks passed."

    return PolicyDecision(
        decision=decision,
        allowed=allowed,
        reason=reason,
        checks=results,
        policy_version=f"v{rules.version}",
        evaluated_at=ctx.now,
    )
