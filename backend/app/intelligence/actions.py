"""Action recommender — deterministic, policy-free.

AI recommends; policy decides (Phase 5 enforces). This module never reads
merchant policies, never checks retry limits against configured caps and never
authorizes execution. It maps diagnosis + probability + context to one of the
five canonical actions.
"""

from dataclasses import dataclass

from app.intelligence.diagnosis import DiagnosisResult
from app.intelligence.features import RecoveryFeatures
from app.models.enums import FailureCategory, RecommendedAction

# Probability thresholds for the retry/notification/escalate ladder.
RETRY_THRESHOLD = 0.45
NOTIFY_THRESHOLD = 0.25


@dataclass(frozen=True)
class ActionRecommendation:
    action: RecommendedAction
    rationale: str


def recommend_action(
    features: RecoveryFeatures,
    diagnosis: DiagnosisResult,
    probability: float,
) -> ActionRecommendation:
    # 1. Hard / non-recoverable declines: stop wasting attempts.
    if diagnosis.is_hard_decline:
        return ActionRecommendation(
            RecommendedAction.STOP,
            "Hard decline evidence — further automated attempts are unlikely to succeed.",
        )
    if features.failure_category.value == "BANK_DECLINE":
        if probability < 0.20:
            return ActionRecommendation(
                RecommendedAction.STOP,
                "Bank decline with low recovery odds — halting is the efficient choice.",
            )
        return ActionRecommendation(
            RecommendedAction.ESCALATE,
            "Bank decline needs human review of decline semantics before retrying.",
        )

    # 2. Instrument problems: money can't arrive until details change.
    if features.failure_category == FailureCategory.EXPIRED_CARD:
        return ActionRecommendation(
            RecommendedAction.PAYMENT_UPDATE,
            "The card appears expired — a refreshed payment method is required first.",
        )

    if features.failure_category == FailureCategory.INVALID_DETAILS:
        return ActionRecommendation(
            RecommendedAction.PAYMENT_UPDATE,
            "Incorrect instrument details — customer must supply corrected credentials.",
        )

    # 3. Recoverable failure modes ladder by estimated probability.
    if probability >= RETRY_THRESHOLD:
        return ActionRecommendation(
            RecommendedAction.RETRY,
            "Recoverable failure mode with solid recovery odds — a retry is the "
            "cheapest next step.",
        )
    if probability >= NOTIFY_THRESHOLD:
        return ActionRecommendation(
            RecommendedAction.CUSTOMER_NOTIFICATION,
            "Moderate recovery odds — prompting the customer improves success "
            "without burning gateway attempts.",
        )
    return ActionRecommendation(
        RecommendedAction.ESCALATE,
        "Low confidence in automated recovery — escalate for manual review.",
    )


def recoverability_band(probability: float) -> str:
    if probability >= RETRY_THRESHOLD:
        return "HIGH"
    if probability >= NOTIFY_THRESHOLD:
        return "MEDIUM"
    return "LOW"
