"""Explanation generation — deterministic first, LLM optional.

The deterministic provider renders the structured signals into one readable
sentence. An optional LLM provider may REWRITE the explanation for readability
but structurally cannot alter the decision: it only receives the already-final
probability/confidence/action/timing plus the signal list, and its output is
stored as prose. If the optional provider fails, we silently fall back.
"""

import logging
from typing import Protocol

from app.intelligence.actions import recoverability_band
from app.intelligence.diagnosis import DiagnosisResult
from app.intelligence.features import RecoveryFeatures
from app.models.enums import RecommendedAction

logger = logging.getLogger("recoverai.explanation")

_ACTION_LEAD = {
    RecommendedAction.RETRY: "RecoverAI recommends a retry",
    RecommendedAction.PAYMENT_UPDATE: "RecoverAI recommends requesting an updated payment method",
    RecommendedAction.CUSTOMER_NOTIFICATION: "RecoverAI recommends notifying the customer",
    RecommendedAction.ESCALATE: "RecoverAI recommends escalating this payment for review",
    RecommendedAction.STOP: "RecoverAI recommends stopping further recovery attempts",
}


class ExplanationProvider(Protocol):
    def explain(
        self,
        features: RecoveryFeatures,
        diagnosis: DiagnosisResult,
        *,
        probability: float,
        confidence: float,
        action: RecommendedAction,
        window_label: str,
        signals: list[dict],
    ) -> str: ...


class DeterministicExplanationProvider:
    """Template rendering over structured signals — always available."""

    def explain(
        self,
        features: RecoveryFeatures,
        diagnosis: DiagnosisResult,
        *,
        probability: float,
        confidence: float,
        action: RecommendedAction,
        window_label: str,
        signals: list[dict],
    ) -> str:
        lead = _ACTION_LEAD[action]
        reasons: list[str] = []

        # Reasons must support the chosen action's direction: positive history
        # evidence never justifies a STOP, and vice versa.
        if action == RecommendedAction.STOP:
            if diagnosis.is_hard_decline:
                reasons.append(
                    "provider evidence indicates a hard, non-recoverable decline"
                )
            else:
                reasons.append("expected recovery value does not justify further attempts")
        elif action == RecommendedAction.ESCALATE:
            reasons.append("automated signals alone are not conclusive enough to act")

        band = features.customer_history_band
        if (
            not reasons
            and band == "HIGH"
            and action in (RecommendedAction.RETRY, RecommendedAction.CUSTOMER_NOTIFICATION)
        ):
            reasons.append("this customer has a strong history of successful recoveries")
        elif band == "LOW":
            reasons.append("this customer's previous recovery attempts have mostly failed")

        if (
            features.category_recovery_rate is not None
            and features.category_recovery_rate >= 0.6
            and features.category_observations >= 5
            and action in (
                RecommendedAction.RETRY,
                RecommendedAction.CUSTOMER_NOTIFICATION,
                RecommendedAction.PAYMENT_UPDATE,
            )
        ):
            reasons.append(
                f"{features.failure_category.value.lower().replace('_', ' ')} failures "
                f"recover {features.category_recovery_rate:.0%} of the time historically"
            )

        positive = [s for s in signals if s["impact"] == "positive"]
        if action in (
            RecommendedAction.RETRY,
            RecommendedAction.CUSTOMER_NOTIFICATION,
            RecommendedAction.PAYMENT_UPDATE,
        ) and not reasons:
            # Fall back to whatever the model found encouraging, de-duplicated
            # by signal name and humanized (no raw enum tokens in prose).
            names: list[str] = []
            seen: set[str] = set()
            for s in positive:
                label = s["name"].lower()
                if label not in seen:
                    seen.add(label)
                    names.append(label)
                if len(names) == 2:
                    break
            reasons.append(
                f"the strongest supporting evidence is {' and '.join(names)}"
                if names else "the available evidence points to this action"
            )

        if not reasons:
            reasons.append("the available evidence is limited but points to this action")

        return f"{lead} because {', and '.join(reasons)}."


class LLMExplanationProvider:
    """Optional readability layer. NOT required for the system to work; wired
    to an external API in a later phase if ever needed. It receives ONLY the
    final decision + signals, so it cannot change the outcome, and any failure
    falls back to the deterministic provider."""

    def __init__(self, fallback: ExplanationProvider) -> None:
        self._fallback = fallback

    def explain(self, *args, **kwargs) -> str:  # pragma: no cover — no external API in Phase 4
        logger.info("LLM explanation requested; falling back to deterministic provider")
        return self._fallback.explain(*args, **kwargs)


def default_provider() -> ExplanationProvider:
    return DeterministicExplanationProvider()
