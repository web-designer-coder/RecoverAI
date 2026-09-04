"""Feature extraction — structured inputs for the recovery models.

Every feature carries a documented neutral/default value for when the
underlying data does not exist yet. Historical features are computed by the
caller (IntelligenceRepository) with leakage protection: only records that
existed BEFORE the current failure are counted, and the current payment is
always excluded from its own history.
"""

import enum
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.models.enums import FailureCategory, PaymentMethod


class DataSufficiency(str, enum.Enum):
    """How much historical evidence backs a decision.

    HIGH   — merchant-wide failure history is large enough for stable rates
             (>= 20 prior failures) AND the specific category has >= 5 observations.
    MEDIUM — moderate evidence (>= 8 failures, category seen before).
    LOW    — thin history; baseline values are used and confidence is reduced.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def confidence_bonus(self) -> float:
        return {"HIGH": 0.30, "MEDIUM": 0.15, "LOW": 0.0}[self.value]


@dataclass(frozen=True)
class HistoryStats:
    """Aggregate counts over past payments (leakage-safe)."""

    total_failures: int = 0          # failed payments observed before this one
    recovered: int = 0               # of those, how many were later recovered
    customer_failures: int = 0       # this customer's earlier failed payments
    customer_recovered: int = 0      # of those, recovered
    previous_retry_successes: int = 0  # recovered on attempt >= 2
    avg_amount: Decimal | None = None  # mean amount of prior failed payments

    @property
    def recovery_rate(self) -> float:
        return self.recovered / self.total_failures if self.total_failures else 0.0

    @property
    def customer_recovery_rate(self) -> float:
        return self.customer_recovered / self.customer_failures if self.customer_failures else 0.0


@dataclass(frozen=True)
class RecoveryFeatures:
    # --- direct payment attributes -----------------------------------------
    payment_id: str
    amount: Decimal
    currency: str
    method: PaymentMethod
    failure_category: FailureCategory
    failure_code: str
    failure_reason: str
    retry_count: int                 # attempts made so far (payment.attempt_number)
    payment_age_hours: float         # created_at → failure time
    hours_since_previous_attempt: float | None
    occurred_hour: int               # 0–23 local-to-merchant approximation (UTC)
    occurred_weekday: int            # 0=Monday … 6=Sunday

    # --- derived / historical ------------------------------------------------
    history: HistoryStats = field(default_factory=HistoryStats)

    # Category-level recovery rate across the merchant's history (None = unseen).
    category_recovery_rate: float | None = None
    category_observations: int = 0
    method_recovery_rate: float | None = None
    method_observations: int = 0
    attempt_recovery_rate: float | None = None   # recovery rate at this attempt number
    attempt_observations: int = 0

    # Time-bucket performance where enough data exists; else None → fallback.
    bucket_recovery_rate: float | None = None
    bucket_name: str = ""           # morning/afternoon/evening/night
    bucket_observations: int = 0

    # Amount relative to the average failed payment (1.0 = exactly average;
    # None when no history exists to compare against).
    amount_ratio: float | None = None

    @property
    def sufficiency(self) -> DataSufficiency:
        h = self.history
        if h.total_failures >= 20 and self.category_observations >= 5:
            return DataSufficiency.HIGH
        if h.total_failures >= 8 and self.category_observations >= 1:
            return DataSufficiency.MEDIUM
        return DataSufficiency.LOW

    @property
    def customer_history_band(self) -> str:
        """HIGH/MEDIUM/LOW/NO_HISTORY band for signals & explanation."""
        if self.history.customer_failures == 0:
            return "NO_HISTORY"
        rate = self.history.customer_recovery_rate
        if rate >= 0.6:
            return "HIGH"
        if rate >= 0.3:
            return "MEDIUM"
        return "LOW"


@dataclass(frozen=True)
class FeatureContext:
    """Everything the extractor needs, already loaded from PostgreSQL."""

    external_payment_id: str
    amount: Decimal
    currency: str
    method: PaymentMethod
    category: FailureCategory
    failure_code: str
    failure_reason: str
    retry_count: int
    created_at: datetime
    occurred_at: datetime
    last_attempt_at: datetime | None
    history: HistoryStats
    category_recovery_rate: float | None
    category_observations: int
    method_recovery_rate: float | None
    method_observations: int
    attempt_recovery_rate: float | None
    attempt_observations: int
    bucket_recovery_rate: float | None
    bucket_observations: int
    amount_ratio: float | None


# Canonical time-of-day buckets (UTC approximation of merchant-local time),
# shared with the repository so history queries group identically.
BUCKET_HOURS: dict[str, tuple[int, ...]] = {
    "morning": tuple(range(6, 12)),
    "afternoon": tuple(range(12, 17)),
    "evening": tuple(range(17, 22)),
    "night": (22, 23, 0, 1, 2, 3, 4, 5),
}


def time_bucket(hour: int) -> str:
    for name, hours in BUCKET_HOURS.items():
        if hour in hours:
            return name
    raise ValueError(f"invalid hour {hour}")  # pragma: no cover


def _bucket(hour: int) -> str:
    return time_bucket(hour)


class FeatureExtractor:
    """Pure transformation from FeatureContext → RecoveryFeatures."""

    def extract(self, ctx: FeatureContext) -> RecoveryFeatures:
        return RecoveryFeatures(
            payment_id=ctx.external_payment_id,
            amount=ctx.amount,
            currency=ctx.currency,
            method=ctx.method,
            failure_category=ctx.category,
            failure_code=ctx.failure_code,
            failure_reason=ctx.failure_reason,
            retry_count=ctx.retry_count,
            payment_age_hours=max(
                0.0, (ctx.occurred_at - ctx.created_at).total_seconds() / 3600.0
            ),
            hours_since_previous_attempt=(
                max(0.0, (ctx.occurred_at - ctx.last_attempt_at).total_seconds() / 3600.0)
                if ctx.last_attempt_at is not None
                else None
            ),
            occurred_hour=ctx.occurred_at.hour,
            occurred_weekday=ctx.occurred_at.weekday(),
            history=ctx.history,
            category_recovery_rate=ctx.category_recovery_rate,
            category_observations=ctx.category_observations,
            method_recovery_rate=ctx.method_recovery_rate,
            method_observations=ctx.method_observations,
            attempt_recovery_rate=ctx.attempt_recovery_rate,
            attempt_observations=ctx.attempt_observations,
            bucket_recovery_rate=ctx.bucket_recovery_rate,
            bucket_name=_bucket(ctx.occurred_at.hour),
            bucket_observations=ctx.bucket_observations,
            amount_ratio=ctx.amount_ratio,
        )
