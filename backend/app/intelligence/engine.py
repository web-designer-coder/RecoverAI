"""Recovery intelligence engine — orchestrates the deterministic pipeline.

    features → diagnosis → probability → confidence → timing → action → explanation

Pure and synchronous: no DB, no clock (time is injected), no randomness.
The same inputs always yield the same AnalysisResult.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.intelligence import actions as actions_mod
from app.intelligence.diagnosis import DiagnosisResult, diagnose
from app.intelligence.explanation import DeterministicExplanationProvider
from app.intelligence.features import FeatureExtractor, FeatureContext, RecoveryFeatures
from app.intelligence.probability import (
    MODEL_VERSION,
    ProbabilityResult,
    compute_confidence,
    score_recovery_probability,
)
from app.intelligence.timing import RecoveryWindowResult, evaluate_windows


@dataclass(frozen=True)
class AnalysisResult:
    features: RecoveryFeatures
    diagnosis: DiagnosisResult
    probability: ProbabilityResult
    ai_confidence: float
    recommended_action: str
    action_rationale: str
    optimal_window: str
    optimal_at: datetime
    expected_recovery_value: Decimal
    data_sufficiency: str
    signals: list[dict]
    explanation: str
    model_version: str


class RecoveryIntelligenceEngine:
    def __init__(self) -> None:
        self._features = FeatureExtractor()
        self._explainer = DeterministicExplanationProvider()

    def analyze(self, context: FeatureContext, *, now: datetime) -> AnalysisResult:
        features = self._features.extract(context)

        diagnosis = diagnose(features)

        # Action is derived first so probability can apply its guardrail.
        provisional_probability = score_recovery_probability(features, diagnosis)
        recommendation = actions_mod.recommend_action(
            features, diagnosis, provisional_probability.probability
        )
        probability = score_recovery_probability(
            features, diagnosis, recommended_action_hint=recommendation.action
        )

        confidence, confidence_signals = compute_confidence(
            features, diagnosis, probability
        )

        timing = evaluate_windows(
            features,
            base_probability=probability.probability,
            amount=features.amount,
            now=now,
        )

        erv = next(
            w.expected_recovery_value for w in timing.evaluations
            if w.label == timing.optimal_window
        )

        signals = (
            diagnosis.signals
            + probability.contributions
            + confidence_signals
            + timing.signals
        )

        explanation = self._explainer.explain(
            features,
            diagnosis,
            probability=probability.probability,
            confidence=confidence,
            action=recommendation.action,
            window_label=timing.optimal_window,
            signals=signals,
        )

        return AnalysisResult(
            features=features,
            diagnosis=diagnosis,
            probability=probability,
            ai_confidence=confidence,
            recommended_action=recommendation.action.value,
            action_rationale=recommendation.rationale,
            optimal_window=timing.optimal_window,
            optimal_at=timing.optimal_at,
            expected_recovery_value=erv,
            data_sufficiency=features.sufficiency.value,
            signals=signals,
            explanation=explanation,
            model_version=MODEL_VERSION,
        )


def build_feature_context(**kwargs) -> FeatureContext:
    """Explicit constructor so callers can't forget leakage-relevant fields."""
    return FeatureContext(**kwargs)
