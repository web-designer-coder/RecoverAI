"""Recovery timing engine — chooses the optimal retry window deterministically.

Candidate windows are fixed (NOW / +12H / +1D / +2D). Each window gets a
category-based multiplier applied to the base probability; when historical
time-bucket performance exists (>= 10 observations), it modulates the bucket
windows instead of the default assumption. The window with the highest
expected recovery value wins; ties break to the EARLIEST window.

Fallbacks (documented): with no usable history the multipliers below are pure,
documented domain defaults — never invented per-request data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.intelligence.features import RecoveryFeatures
from app.models.enums import FailureCategory

WINDOW_LABELS = ("NOW", "+12H", "+1D", "+2D")
_WINDOW_OFFSETS = {
    "NOW": timedelta(0),
    "+12H": timedelta(hours=12),
    "+1D": timedelta(days=1),
    "+2D": timedelta(days=2),
}

# Domain-default multipliers: how each category's recovery odds shift by wait.
# Insufficient funds typically resolves on salary/credit cycles (+12H best);
# network failures succeed immediately once connectivity returns.
_CATEGORY_WINDOW_MULTIPLIER = {
    "NOW":   {FailureCategory.NETWORK_FAILURE: 1.05, FailureCategory.INSUFFICIENT_FUNDS: 0.90,
              FailureCategory.EXPIRED_CARD: 0.80, FailureCategory.INVALID_DETAILS: 0.85,
              FailureCategory.BANK_DECLINE: 0.70, FailureCategory.OTHER: 0.95},
    "+12H":  {FailureCategory.NETWORK_FAILURE: 1.00, FailureCategory.INSUFFICIENT_FUNDS: 1.15,
              FailureCategory.EXPIRED_CARD: 0.95, FailureCategory.INVALID_DETAILS: 1.00,
              FailureCategory.BANK_DECLINE: 0.90, FailureCategory.OTHER: 1.05},
    "+1D":   {FailureCategory.NETWORK_FAILURE: 0.95, FailureCategory.INSUFFICIENT_FUNDS: 1.10,
              FailureCategory.EXPIRED_CARD: 1.05, FailureCategory.INVALID_DETAILS: 1.00,
              FailureCategory.BANK_DECLINE: 0.95, FailureCategory.OTHER: 1.00},
    "+2D":   {FailureCategory.NETWORK_FAILURE: 0.90, FailureCategory.INSUFFICIENT_FUNDS: 1.00,
              FailureCategory.EXPIRED_CARD: 1.00, FailureCategory.INVALID_DETAILS: 0.95,
              FailureCategory.BANK_DECLINE: 0.95, FailureCategory.OTHER: 0.95},
}

# Historical time-bucket modulation applied when the merchant has enough
# observations for the failure's own bucket.
_BUCKET_MODULATION_RANGE = 0.08  # ±8% at most


@dataclass(frozen=True)
class WindowEvaluation:
    label: str
    probability: float
    expected_recovery_value: Decimal
    at: datetime


@dataclass(frozen=True)
class RecoveryWindowResult:
    optimal_window: str
    optimal_at: datetime
    evaluations: list[WindowEvaluation] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)


def evaluate_windows(
    features: RecoveryFeatures,
    *,
    base_probability: float,
    amount: Decimal,
    now: datetime,
) -> RecoveryWindowResult:
    """Score every candidate window; pick argmax(expected recovery value)."""
    bucket_modulation = 1.0
    if (
        features.bucket_recovery_rate is not None
        and features.bucket_observations >= 10
    ):
        # Historical bucket performance vs a neutral 50% reference — bounded.
        bucket_modulation = 1.0 + (
            (features.bucket_recovery_rate - 0.5) * 2 * _BUCKET_MODULATION_RANGE
        )

    evaluations: list[WindowEvaluation] = []
    for label in WINDOW_LABELS:
        multiplier = _CATEGORY_WINDOW_MULTIPLIER[label][features.failure_category]
        if label != "NOW":
            multiplier *= bucket_modulation
        window_probability = min(0.95, max(0.01, base_probability * multiplier))
        erv = (amount * Decimal(str(round(window_probability, 4)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        evaluations.append(
            WindowEvaluation(
                label=label,
                probability=round(window_probability, 4),
                expected_recovery_value=erv,
                at=now + _WINDOW_OFFSETS[label],
            )
        )

    # Highest ERV wins; ties go to the earliest window (list is time-ordered).
    best = max(evaluations, key=lambda w: w.expected_recovery_value)

    signals = [
        {
            "name": "Optimal window",
            "value": f"{best.label} ({_human_offset(best.at - now)})",
            "impact": "positive",
            "category": "timing",
        },
        {
            "name": "Time bucket",
            "value": features.bucket_name or "n/a",
            "impact": "neutral" if features.bucket_recovery_rate is None else (
                "positive" if bucket_modulation >= 1.0 else "negative"
            ),
            "category": "timing",
        },
    ]
    return RecoveryWindowResult(
        optimal_window=best.label,
        optimal_at=best.at,
        evaluations=evaluations,
        signals=signals,
    )


def _human_offset(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    return "now" if minutes == 0 else f"+{minutes // 60}h" if minutes % 60 == 0 else f"+{minutes}m"
