"""Deterministic failure diagnosis — rule-based, no ML, no LLM.

Translates the normalized failure category (+ provider evidence) into a
human-readable diagnosis with a classification confidence. Uncertain provider
data lowers diagnosis confidence instead of being dressed up as certainty.
"""

from dataclasses import dataclass, field

from app.models.enums import FailureCategory
from app.intelligence.features import RecoveryFeatures

# Provider failure codes treated as hard (non-recoverable) declines.
HARD_DECLINE_CODES = {
    "do_not_honour",
    "blocked_by_risk",
    "fraud_suspected",
    "card_reported_lost",  # not in our seed set; defensive for future codes
}

_DIAGNOSIS_TEXT = {
    FailureCategory.INSUFFICIENT_FUNDS: (
        "Insufficient funds / temporarily unavailable balance is the most likely cause."
    ),
    FailureCategory.NETWORK_FAILURE: (
        "Temporary network or bank connectivity failure is the most likely cause."
    ),
    FailureCategory.EXPIRED_CARD: (
        "The payment instrument appears expired or invalid."
    ),
    FailureCategory.INVALID_DETAILS: (
        "The payment instrument details appear incorrect (CVV/expiry/authentication)."
    ),
    FailureCategory.BANK_DECLINE: (
        "The issuing bank declined the transaction; recovery depends on decline semantics."
    ),
    FailureCategory.OTHER: (
        "The failure reason could not be confidently determined from provider data."
    ),
}


@dataclass(frozen=True)
class DiagnosisResult:
    diagnosis: str
    failure_category: FailureCategory
    confidence: float                 # certainty of the CLASSIFICATION, 0..1
    is_hard_decline: bool
    signals: list[dict] = field(default_factory=list)


def diagnose(features: RecoveryFeatures) -> DiagnosisResult:
    category = features.failure_category
    code = features.failure_code.strip().lower()
    is_hard = (
        code in HARD_DECLINE_CODES
        or (category == FailureCategory.BANK_DECLINE and features.retry_count >= 3)
    )

    # Classification certainty: a structured provider reason we recognize is
    # strong evidence; OTHER means the provider did not tell us much.
    if category == FailureCategory.OTHER:
        confidence = 0.45
    elif code in ("unknown", ""):
        confidence = 0.60
    else:
        confidence = 0.90
    if is_hard:
        confidence = min(0.97, confidence + 0.05)  # repeated hard evidence is clearer

    text = _DIAGNOSIS_TEXT[category]
    if is_hard and category == FailureCategory.BANK_DECLINE:
        text += " Evidence indicates a hard/non-recoverable decline."

    signals = [
        {
            "name": "Failure category",
            "value": category.value,
            "impact": "negative" if is_hard or category == FailureCategory.BANK_DECLINE
                      else ("positive" if category in (
                          FailureCategory.INSUFFICIENT_FUNDS, FailureCategory.NETWORK_FAILURE)
                          else "neutral"),
            "category": "diagnosis",
        },
        {
            "name": "Provider failure code",
            "value": code or "unspecified",
            "impact": "negative" if is_hard else "neutral",
            "category": "diagnosis",
        },
    ]
    return DiagnosisResult(
        diagnosis=text,
        failure_category=category,
        confidence=confidence,
        is_hard_decline=is_hard,
        signals=signals,
    )
