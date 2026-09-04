"""Policy check library — reusable, pure, individually testable.

Every check takes the PolicyContext (plus any rule values it needs) and
returns a PolicyCheckResult. No I/O, no randomness; identical inputs produce
identical results. The evaluator composes them in a fixed documented order.
"""

from datetime import datetime, timedelta, timezone

from app.models.enums import PaymentStatus, RecommendedAction
from app.policy.models import CheckStatus, PolicyCheckResult, PolicyContext

# States from which a recovery action may be authorized at all.
EXECUTABLE_PAYMENT_STATES = {
    PaymentStatus.FAILED,
    PaymentStatus.QUEUED,
    PaymentStatus.NEEDS_ACTION,
}

# Action statuses considered "active or done" for duplicate protection.
# SUCCEEDED blocks forever (money already moved); CANCELLED/FAILED/BLOCKED/
# ESCALATED actions do not prevent a fresh attempt.
BLOCKING_ACTION_STATUSES = {
    "PENDING",
    "VERIFYING_POLICY",
    "APPROVED",
    "SCHEDULED",
    "PROCESSING",
    "SUCCEEDED",
}

# Intrinsically compatible failure-category → action pairs. The AI's
# recommendation must fall inside this set; policy failure_rules stay a
# merchant-tuning matrix and are NOT force-matched here (documented in
# docs/policy-engine.md).
_COMPATIBLE_ACTIONS: dict[str, set[str]] = {
    "INSUFFICIENT_FUNDS": {"RETRY", "CUSTOMER_NOTIFICATION"},
    "NETWORK_FAILURE": {"RETRY", "CUSTOMER_NOTIFICATION"},
    "EXPIRED_CARD": {"PAYMENT_UPDATE", "STOP"},
    "INVALID_DETAILS": {"PAYMENT_UPDATE", "CUSTOMER_NOTIFICATION", "STOP"},
    "BANK_DECLINE": {"STOP", "ESCALATE", "PAYMENT_UPDATE"},
    "OTHER": {a.value for a in RecommendedAction},
}


def check_payment_state(ctx: PolicyContext) -> PolicyCheckResult:
    status = ctx.payment.status
    if status in EXECUTABLE_PAYMENT_STATES:
        return PolicyCheckResult(
            "payment_state", CheckStatus.PASS,
            f"Payment state {status.value} is eligible for recovery.",
        )
    reasons = {
        PaymentStatus.RECOVERED: "Payment is already recovered.",
        PaymentStatus.HALTED: "Recovery was halted by an operator.",
        PaymentStatus.AUTHORIZED: "Funds are authorized; capture flow owns this payment.",
        PaymentStatus.PROCESSING: "A provider transition is already in flight.",
        PaymentStatus.SCHEDULED: "Recovery is already scheduled for this payment.",
    }
    return PolicyCheckResult(
        "payment_state", CheckStatus.FAIL,
        reasons.get(status, f"Payment state {status.value} is not recoverable."),
        severity="critical",
        metadata={"state": status.value},
    )


def check_failure_exists(ctx: PolicyContext) -> PolicyCheckResult:
    if ctx.payment_failure is not None:
        return PolicyCheckResult(
            "failure_exists", CheckStatus.PASS, "A persisted failure exists to recover from."
        )
    return PolicyCheckResult(
        "failure_exists", CheckStatus.FAIL,
        "No failure data recorded for this payment.", severity="critical",
    )


def check_ai_decision_exists(ctx: PolicyContext) -> PolicyCheckResult:
    decision = ctx.recovery_decision
    if decision is None:
        return PolicyCheckResult(
            "ai_decision_exists", CheckStatus.FAIL,
            "No recovery decision exists. Run analysis first.", severity="critical",
        )
    return PolicyCheckResult(
        "ai_decision_exists", CheckStatus.PASS,
        f"AI decision present (model {decision.model_version}).",
        metadata={"model_version": decision.model_version},
    )


def check_ai_decision_current(ctx: PolicyContext) -> PolicyCheckResult:
    if ctx.recovery_decision is None:
        return PolicyCheckResult(
            "ai_decision_current", CheckStatus.NOT_APPLICABLE, "No decision to check."
        )
    if ctx.decision_is_current:
        return PolicyCheckResult(
            "ai_decision_current", CheckStatus.PASS, "Evaluated decision is the latest version."
        )
    return PolicyCheckResult(
        "ai_decision_current", CheckStatus.FAIL,
        "The referenced AI decision is outdated. Re-analyze before executing.",
        severity="critical",
    )


def check_retry_limit(ctx: PolicyContext, maximum_retries: int) -> PolicyCheckResult:
    """``retry_count`` counts FAILED PAYMENT ATTEMPTS (payments.attempt_number):
    every provider-facing attempt that failed. Customer notifications and
    payment-update requests are NOT retries — they never hit the gateway.
    With maximum_retries = 3: attempts 0/1/2 pass, attempt 3 blocks."""
    if ctx.retry_count >= maximum_retries:
        return PolicyCheckResult(
            "retry_limit", CheckStatus.FAIL,
            f"Retry limit reached ({ctx.retry_count} of {maximum_retries} allowed).",
            metadata={"retry_count": ctx.retry_count, "maximum_retries": maximum_retries},
        )
    return PolicyCheckResult(
        "retry_limit", CheckStatus.PASS,
        f"Retry {ctx.retry_count} of maximum {maximum_retries}.",
        metadata={"retry_count": ctx.retry_count, "maximum_retries": maximum_retries},
    )


def check_recovery_window(ctx: PolicyContext, recovery_window_days: int) -> PolicyCheckResult:
    """UTC-only comparison against the failure time; local server time never
    participates."""
    deadline = _window_deadline(ctx.payment_failure.occurred_at, recovery_window_days)
    if ctx.now > deadline:
        return PolicyCheckResult(
            "recovery_window", CheckStatus.FAIL,
            f"Recovery window expired on {deadline.isoformat()}.",
            severity="critical",
            metadata={"deadline": deadline.isoformat(), "evaluated_at": ctx.now.isoformat()},
        )
    return PolicyCheckResult(
        "recovery_window", CheckStatus.PASS,
        f"Within the {recovery_window_days}-day recovery window "
        f"(deadline {deadline.date().isoformat()}).",
        metadata={"deadline": deadline.isoformat()},
    )


def check_ai_confidence(
    ctx: PolicyContext, minimum_confidence_percent: float
) -> PolicyCheckResult:
    confidence = ctx.ai_confidence
    if confidence is None:
        return PolicyCheckResult(
            "ai_confidence", CheckStatus.NOT_APPLICABLE, "No AI decision to evaluate."
        )
    minimum = float(minimum_confidence_percent)
    percent = confidence * 100  # convention boundary: stored 0..1 → compared as %
    if percent >= minimum:
        return PolicyCheckResult(
            "ai_confidence", CheckStatus.PASS,
            f"AI confidence {percent:.0f}% meets required {minimum:.0f}%.",
            metadata={"confidence": confidence, "required": minimum / 100},
        )
    return PolicyCheckResult(
        "ai_confidence", CheckStatus.FAIL,
        f"AI confidence {percent:.0f}% is below required {minimum:.0f}%.",
        metadata={"confidence": confidence, "required": minimum / 100},
    )


def check_action_compatibility(ctx: PolicyContext) -> PolicyCheckResult:
    action = ctx.recommended_action
    category = ctx.failure_category
    if action is None or category is None:
        return PolicyCheckResult(
            "action_compatibility", CheckStatus.NOT_APPLICABLE,
            "No recommendation to validate.",
        )
    compatible = _COMPATIBLE_ACTIONS.get(category, set())
    if action.value in compatible:
        return PolicyCheckResult(
            "action_compatibility", CheckStatus.PASS,
            f"{action.value} is compatible with {category}.",
        )
    return PolicyCheckResult(
        "action_compatibility", CheckStatus.FAIL,
        f"Recommended {action.value} is incompatible with {category}; "
        "the AI recommendation is never silently replaced.",
        metadata={"recommended_action": action.value, "failure_category": category},
    )


def check_duplicate_recovery(
    ctx: PolicyContext, prevent_duplicate_recovery: bool
) -> PolicyCheckResult:
    if not prevent_duplicate_recovery:
        return PolicyCheckResult(
            "duplicate_recovery", CheckStatus.NOT_APPLICABLE,
            "Duplicate protection disabled by policy.",
        )
    blocking = [
        a for a in ctx.existing_recovery_actions
        if a.status.value in BLOCKING_ACTION_STATUSES
    ]
    if blocking:
        statuses = sorted({a.status.value for a in blocking})
        return PolicyCheckResult(
            "duplicate_recovery", CheckStatus.FAIL,
            f"An active/succeeded recovery action already exists ({', '.join(statuses)}).",
            severity="critical",
            metadata={"active_action_count": len(blocking)},
        )
    return PolicyCheckResult(
        "duplicate_recovery", CheckStatus.PASS, "No active recovery action exists."
    )


def check_high_value(
    ctx: PolicyContext, high_value_threshold, escalate_high_value: bool
) -> PolicyCheckResult:
    amount = ctx.payment_amount
    if high_value_threshold is None or amount < high_value_threshold:
        return PolicyCheckResult(
            "high_value", CheckStatus.PASS,
            f"Amount ₹{amount} is below the high-value threshold.",
        )
    if escalate_high_value:
        return PolicyCheckResult(
            "high_value", CheckStatus.ESCALATE,
            "HIGH_VALUE_TRANSACTION — human approval required before execution.",
            severity="warning",
            metadata={
                "amount": str(amount),
                "threshold": str(high_value_threshold),
                "requirement": "HUMAN_APPROVAL_REQUIRED",
            },
        )
    return PolicyCheckResult(
        "high_value", CheckStatus.PASS,
        "High-value transaction with escalation disabled by policy — continuing.",
        severity="warning",
        metadata={"amount": str(amount), "threshold": str(high_value_threshold)},
    )


def check_policy_approval(ctx: PolicyContext, require_policy_approval: bool) -> PolicyCheckResult:
    if not require_policy_approval:
        return PolicyCheckResult(
            "policy_approval", CheckStatus.PASS, "Explicit approval not required by policy."
        )
    # No human approval platform exists yet — we NEVER pretend approval was
    # granted. Escalate instead.
    return PolicyCheckResult(
        "policy_approval", CheckStatus.ESCALATE,
        "Policy requires explicit approval; no automated approval is permitted.",
        severity="warning",
    )


def _window_deadline(occurred_at: datetime, days: int) -> datetime:
    deadline = occurred_at + timedelta(days=days)
    if deadline.tzinfo is None:  # defensive: storage is always tz-aware
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline
