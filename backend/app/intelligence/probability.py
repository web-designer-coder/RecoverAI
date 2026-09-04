"""Recovery probability model — recoverai-v1.

Transparent additive scoring over extracted features. Fully deterministic:
no randomness, no network, no LLM. The formula and every weight below are
documented in backend/docs/recovery-intelligence.md; changing them requires a
model-version bump (recoverai-v2 …) so historical decisions stay auditable.

Probability convention: internal float in 0..1 (0.74 = 74%). Serialization to
percent happens only at the presentation boundary — never mixed.
"""

from dataclasses import dataclass, field

from app.intelligence.diagnosis import DiagnosisResult
from app.intelligence.features import DataSufficiency, RecoveryFeatures
from app.models.enums import FailureCategory, PaymentMethod, RecommendedAction

MODEL_VERSION = "recoverai-v1"

BASE_PROBABILITY = 0.35

# Additive category signal: how much each failure type moves recovery odds
# relative to the base. Insufficient funds is transient; hard bank declines
# are not.
CATEGORY_SIGNAL = {
    FailureCategory.INSUFFICIENT_FUNDS: +0.20,
    FailureCategory.NETWORK_FAILURE: +0.15,
    FailureCategory.INVALID_DETAILS: +0.00,
    FailureCategory.EXPIRED_CARD: -0.05,
    FailureCategory.BANK_DECLINE: -0.25,
    FailureCategory.OTHER: -0.05,
}

METHOD_SIGNAL = {
    PaymentMethod.UPI: +0.05,
    PaymentMethod.CARD: +0.03,
    PaymentMethod.NET_BANKING: +0.02,
    PaymentMethod.WALLET: +0.01,
    PaymentMethod.OTHER: 0.00,
}

# Retry decay: first retries are cheap and effective; later ones are not.
def _retry_signal(retry_count: int) -> float:
    if retry_count <= 0:
        return 0.08
    if retry_count == 1:
        return 0.04
    if retry_count == 2:
        return -0.06
    return -0.18


# Amount effect relative to the merchant's average failed payment.
def _amount_signal(ratio: float | None) -> float:
    if ratio is None:
        return 0.0
    if ratio < 1.0:
        return 0.04
    if ratio <= 5.0:
        return 0.0
    return -0.06


PROBABILITY_FLOOR = 0.01
PROBABILITY_CEILING = 0.95


@dataclass(frozen=True)
class ProbabilityResult:
    probability: float                # 0..1
    model_version: str
    contributions: list[dict] = field(default_factory=list)


def score_recovery_probability(
    features: RecoveryFeatures,
    diagnosis: DiagnosisResult,
    recommended_action_hint: RecommendedAction | None = None,
) -> ProbabilityResult:
    """Compute the recovery probability from documented weights.

    ``recommended_action_hint`` exists only for the sanity invariant that a
    STOP-recommended (hard decline) payment cannot score high; it never adds
    probability on its own.
    """
    contributions: list[tuple[str, float, dict]] = []

    def add(name: str, value: str, delta: float, category: str) -> None:
        contributions.append((
            name,
            delta,
            {"name": name, "value": value, "impact": _impact(delta), "category": category},
        ))

    add(
        "Failure category",
        features.failure_category.value,
        CATEGORY_SIGNAL[features.failure_category],
        "history",
    )
    add("Payment method", features.method.value, METHOD_SIGNAL[features.method], "context")

    history = features.history
    customer_band = features.customer_history_band
    if history.customer_failures >= 3:
        # Centered so ~50% historical performance contributes nothing.
        customer_delta = (history.customer_recovery_rate - 0.5) * 0.20
    else:
        customer_delta = 0.0
    add("Customer recovery history", customer_band, customer_delta, "history")

    retry_delta = _retry_signal(features.retry_count)
    retry_value = f"{features.retry_count} previous attempt(s)"
    add("Retry attempt", retry_value, retry_delta, "context")

    amount_delta = _amount_signal(features.amount_ratio)
    amount_value = (
        f"{features.amount_ratio:.2f}× average" if features.amount_ratio is not None
        else "no comparison history"
    )
    add("Amount vs history", amount_value, amount_delta, "context")

    if features.category_observations >= 5 and features.category_recovery_rate is not None:
        category_rate_delta = (features.category_recovery_rate - 0.5) * 0.10
        rate_text = (
            f"{features.category_recovery_rate:.0%} over {features.category_observations}"
        )
    elif features.category_observations > 0:
        # Observed but below the sample-size floor — shown honestly as unused.
        category_rate_delta = 0.0
        rate_text = (
            f"only {features.category_observations} observation(s) — below sample threshold"
        )
    else:
        category_rate_delta = 0.0
        rate_text = "unseen category"
    add("Category recovery rate", rate_text, category_rate_delta, "history")

    probability = BASE_PROBABILITY + sum(delta for _, delta, _ in contributions)

    # Hard-decline guardrail: non-recoverable evidence caps the estimate.
    if diagnosis.is_hard_decline or (
        diagnosis.failure_category == FailureCategory.BANK_DECLINE
        and probability > 0.30
    ):
        probability = min(probability, 0.15)

    probability = max(PROBABILITY_FLOOR, min(PROBABILITY_CEILING, probability))

    return ProbabilityResult(
        probability=round(probability, 4),
        model_version=MODEL_VERSION,
        contributions=[entry[2] for entry in contributions],
    )


def compute_confidence(
    features: RecoveryFeatures,
    diagnosis: DiagnosisResult,
    probability_result: ProbabilityResult,
) -> tuple[float, list[dict]]:
    """AI confidence — how sure the model is about its own estimate.

    Distinct from probability by design. Driven by data sufficiency,
    classification certainty, historical sample size and the spread of the
    individual signal contributions (agreement).
    """
    sufficiency = features.sufficiency

    confidence = 0.50
    confidence += sufficiency.confidence_bonus          # up to +0.30
    confidence += (diagnosis.confidence - 0.60) * 0.5   # classification certainty ±0.18
    if features.history.total_failures >= 10:
        confidence += 0.05
    if features.attempt_observations >= 5 and features.attempt_recovery_rate is not None:
        confidence += 0.04

    # Agreement: signals pulling in one direction (relative to zero) raise
    # confidence; contradictory evidence lowers it.
    deltas = [
        {"positive": 1.0, "negative": -1.0}.get(c["impact"], 0.0)
        for c in probability_result.contributions
    ]
    active = [d for d in deltas if d != 0.0]
    if active:
        dominant = abs(sum(active)) / len(active)
        confidence += dominant * 0.08
        if any(d * sum(active) < 0 for d in active):
            confidence -= 0.05

    confidence = round(max(0.30, min(0.97, confidence)), 4)

    signals = [{
        "name": "Data sufficiency",
        "value": sufficiency.value,
        "impact": "positive" if sufficiency is DataSufficiency.HIGH else "neutral",
        "category": "confidence",
    }]
    return confidence, signals


def _impact(delta: float) -> str:
    if delta > 0.001:
        return "positive"
    if delta < -0.001:
        return "negative"
    return "neutral"
