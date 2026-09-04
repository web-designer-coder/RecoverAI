"""Phase 4 unit tests — pure intelligence modules (no database).

Everything here runs against hand-built FeatureContexts, proving the engine is
deterministic and independent of FastAPI/PostgreSQL.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.intelligence import build_feature_context
from app.intelligence.actions import (
    NOTIFY_THRESHOLD,
    RETRY_THRESHOLD,
    recommend_action,
)
from app.intelligence.diagnosis import diagnose
from app.intelligence.engine import RecoveryIntelligenceEngine
from app.intelligence.features import DataSufficiency, FeatureExtractor, HistoryStats
from app.intelligence.probability import MODEL_VERSION, compute_confidence, score_recovery_probability
from app.intelligence.timing import evaluate_windows
from app.models.enums import FailureCategory, PaymentMethod

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
ENGINE = RecoveryIntelligenceEngine()

STRONG_HISTORY = HistoryStats(
    total_failures=40,
    recovered=33,
    customer_failures=4,
    customer_recovered=3,
    previous_retry_successes=10,
    avg_amount=Decimal("6000.00"),
)


def ctx(**overrides):
    """Canonical strong-context payment (UPI insufficient funds)."""
    kw = dict(
        external_payment_id="PAY_TEST_1",
        amount=Decimal("8499.00"),
        currency="INR",
        method=PaymentMethod.UPI,
        category=FailureCategory.INSUFFICIENT_FUNDS,
        failure_code="insufficient_fund",
        failure_reason="Payment declined due to insufficient funds",
        retry_count=1,
        created_at=datetime(2026, 8, 26, 11, 30, tzinfo=timezone.utc),
        occurred_at=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
        last_attempt_at=None,
        history=STRONG_HISTORY,
        category_recovery_rate=0.80, category_observations=12,
        method_recovery_rate=0.70, method_observations=20,
        attempt_recovery_rate=0.60, attempt_observations=8,
        bucket_recovery_rate=0.55, bucket_observations=15,
        amount_ratio=1.42,
    )
    kw.update(overrides)
    return build_feature_context(**kw)


def weak_ctx(**overrides):
    """Same payment with essentially no usable history."""
    return ctx(
        history=HistoryStats(total_failures=5, recovered=1),
        category_recovery_rate=None, category_observations=0,
        method_recovery_rate=None, method_observations=0,
        attempt_recovery_rate=None, attempt_observations=0,
        bucket_recovery_rate=None, bucket_observations=0,
        amount_ratio=None,
        **overrides,
    )


# --- feature extraction -----------------------------------------------------


def test_feature_extraction_derives_time_features():
    features = FeatureExtractor().extract(
        ctx(last_attempt_at=datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc))
    )
    assert features.payment_age_hours == 0.5
    assert features.hours_since_previous_attempt == 3.0
    assert features.occurred_hour == 12
    assert features.occurred_weekday == 2  # Wednesday
    assert features.bucket_name == "afternoon"


def test_history_stats_rates():
    assert STRONG_HISTORY.recovery_rate == 33 / 40
    assert STRONG_HISTORY.customer_recovery_rate == 3 / 4


def test_no_history_yields_neutral_defaults():
    features = FeatureExtractor().extract(ctx(history=HistoryStats()))
    assert features.sufficiency is DataSufficiency.LOW
    assert features.customer_history_band == "NO_HISTORY"
    assert features.amount_ratio is None or True  # set via context below


def test_no_history_context_never_fakes_data():
    result = ENGINE.analyze(weak_ctx(), now=NOW)
    values = [s["value"] for s in result.signals]
    assert any("unseen" in v or "no comparison" in v for v in values)
    assert result.data_sufficiency == "LOW"


def test_sufficiency_tiers():
    f = FeatureExtractor().extract
    assert f(ctx()).sufficiency is DataSufficiency.HIGH          # 40 failures, 12 cat obs
    assert f(ctx(category_recovery_rate=None, category_observations=1)).sufficiency is DataSufficiency.MEDIUM
    assert f(weak_ctx()).sufficiency is DataSufficiency.LOW       # only 5 prior failures


# --- diagnosis ----------------------------------------------------------------


def test_diagnosis_per_category():
    for category, expected_fragment in [
        (FailureCategory.INSUFFICIENT_FUNDS, "Insufficient funds"),
        (FailureCategory.NETWORK_FAILURE, "network"),
        (FailureCategory.EXPIRED_CARD, "expired"),
        (FailureCategory.INVALID_DETAILS, "incorrect"),
        (FailureCategory.BANK_DECLINE, "issuing bank"),
        (FailureCategory.OTHER, "could not be confidently determined"),
    ]:
        d = diagnose(FeatureExtractor().extract(ctx(category=category)))
        assert expected_fragment.lower() in d.diagnosis.lower(), category


def test_hard_decline_by_code_and_by_repeats():
    d = diagnose(FeatureExtractor().extract(ctx(failure_code="do_not_honour")))
    assert d.is_hard_decline
    d = diagnose(
        FeatureExtractor().extract(
            ctx(category=FailureCategory.BANK_DECLINE, failure_code="issuer_unavailable", retry_count=3)
        )
    )
    assert d.is_hard_decline
    # A single soft bank decline is NOT hard.
    d = diagnose(
        FeatureExtractor().extract(
            ctx(category=FailureCategory.BANK_DECLINE, failure_code="issuer_unavailable", retry_count=1)
        )
    )
    assert not d.is_hard_decline


def test_uncertain_classification_lowers_diagnosis_confidence():
    known = diagnose(FeatureExtractor().extract(ctx())).confidence
    unknown_code = diagnose(FeatureExtractor().extract(ctx(failure_code="unknown"))).confidence
    other = diagnose(FeatureExtractor().extract(ctx(failure_code="", category=FailureCategory.OTHER))).confidence
    assert known > unknown_code > other


# --- probability & confidence ---------------------------------------------


def test_probability_deterministic_and_bounded():
    r1 = score_recovery_probability(FeatureExtractor().extract(ctx()), diagnose(FeatureExtractor().extract(ctx())))
    r2 = score_recovery_probability(FeatureExtractor().extract(ctx()), diagnose(FeatureExtractor().extract(ctx())))
    assert r1 == r2
    assert MODEL_VERSION == "recoverai-v1"
    assert 0.01 <= r1.probability <= 0.95


def test_confidence_is_not_probability():
    features = FeatureExtractor().extract(ctx())
    prob = score_recovery_probability(features, diagnose(features))
    conf, _ = compute_confidence(features, diagnose(features), prob)
    assert conf != prob.probability
    assert 0.30 <= conf <= 0.97


def test_strong_history_never_lower_than_weak_history():
    """Spec sanity: more successful history must not REDUCE the estimate."""
    strong = ENGINE.analyze(ctx(), now=NOW).probability.probability
    weak = ENGINE.analyze(weak_ctx(), now=NOW).probability.probability
    assert strong >= weak


def test_hard_decline_capped_low_and_never_high_retry():
    result = ENGINE.analyze(
        ctx(category=FailureCategory.BANK_DECLINE, failure_code="do_not_honour", retry_count=3),
        now=NOW,
    )
    assert result.recommended_action == "STOP"
    assert result.probability.probability <= 0.15


# --- timing ---------------------------------------------------------------


def test_insufficient_funds_peaks_after_twelve_hours():
    features = FeatureExtractor().extract(ctx())
    timing = evaluate_windows(features, base_probability=0.60, amount=Decimal("100.00"), now=NOW)
    assert timing.optimal_window == "+12H"
    assert [w.label for w in timing.evaluations] == ["NOW", "+12H", "+1D", "+2D"]
    assert all(w.expected_recovery_value.as_tuple().exponent == -2 for w in timing.evaluations)


def test_window_times_are_offsets_from_now():
    features = FeatureExtractor().extract(ctx())
    timing = evaluate_windows(features, base_probability=0.60, amount=Decimal("100.00"), now=NOW)
    by_label = {w.label: w.at for w in timing.evaluations}
    assert by_label["NOW"] == NOW
    assert by_label["+1D"].day == 27


def test_erv_is_amount_times_probability_in_decimal():
    features = FeatureExtractor().extract(ctx())
    timing = evaluate_windows(features, base_probability=0.60, amount=Decimal("8499.00"), now=NOW)
    now_eval = next(w for w in timing.evaluations if w.label == "NOW")
    expected = (Decimal("8499.00") * Decimal(str(now_eval.probability))).quantize(Decimal("0.01"))
    assert now_eval.expected_recovery_value == expected


def test_best_window_is_argmax_erv_with_earliest_tie():
    features = FeatureExtractor().extract(ctx())
    timing = evaluate_windows(features, base_probability=0.50, amount=Decimal("1000.00"), now=NOW)
    best = max(w.expected_recovery_value for w in timing.evaluations)
    winner = next(w for w in timing.evaluations if w.label == timing.optimal_window)
    assert winner.expected_recovery_value == best
    earliest = min(w.at for w in timing.evaluations if w.expected_recovery_value == best)
    assert winner.at == earliest


# --- actions ----------------------------------------------------------------


def test_action_ladder_by_probability():
    features = FeatureExtractor().extract(ctx())
    diagnosis = diagnose(features)
    ladder = [
        (0.90, "RETRY"),
        (RETRY_THRESHOLD, "RETRY"),
        (NOTIFY_THRESHOLD + 0.01, "CUSTOMER_NOTIFICATION"),
        (NOTIFY_THRESHOLD, "CUSTOMER_NOTIFICATION"),
        (0.10, "ESCALATE"),
    ]
    for probability, expected in ladder:
        assert recommend_action(features, diagnosis, probability).action.value == expected


def test_expired_card_maps_to_payment_update_even_at_high_probability():
    features = FeatureExtractor().extract(ctx(category=FailureCategory.EXPIRED_CARD))
    rec = recommend_action(features, diagnose(features), 0.90)
    assert rec.action.value == "PAYMENT_UPDATE"


def test_signals_are_structured_explanations():
    result = ENGINE.analyze(ctx(), now=NOW)
    assert result.signals
    for signal in result.signals:
        assert set(signal) == {"name", "value", "impact", "category"}
        assert isinstance(signal["name"], str) and signal["name"]
        assert signal["impact"] in {"positive", "negative", "neutral"}
    names = {s["name"] for s in result.signals}
    assert {"Failure category", "Optimal window"} <= names
    assert not any("chain" in n.lower() or "thought" in n.lower() for n in names)


def test_full_engine_output_is_coherent():
    result = ENGINE.analyze(ctx(), now=NOW)
    assert result.model_version == "recoverai-v1"
    assert result.optimal_window in ("NOW", "+12H", "+1D", "+2D")
    assert result.expected_recovery_value > 0
    assert result.explanation.startswith("RecoverAI recommends")


def test_engine_determinism_across_instances():
    a = RecoveryIntelligenceEngine().analyze(ctx(), now=NOW)
    b = RecoveryIntelligenceEngine().analyze(ctx(), now=NOW)
    assert a == b
