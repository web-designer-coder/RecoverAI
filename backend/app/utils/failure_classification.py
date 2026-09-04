"""Deterministic normalization of Razorpay failure data into domain categories.

This is NOT the AI engine (Phase 4). It is a pure, rule-based translation of
provider error fields into the six FailureCategory values the rest of the
system already uses. Uncertain input maps to OTHER — never a confident guess.
"""

from app.models.enums import FailureCategory

# Razorpay's standard error reasons (payment.error_reason) plus gateway
# decline codes seen in Test Mode. Keys are matched case-insensitively.
_REASON_MAP: dict[str, FailureCategory] = {
    "insufficient_fund": FailureCategory.INSUFFICIENT_FUNDS,
    "insufficient_funds": FailureCategory.INSUFFICIENT_FUNDS,
    "card_expired": FailureCategory.EXPIRED_CARD,
    "expired_card": FailureCategory.EXPIRED_CARD,
    "invalid_cvv": FailureCategory.INVALID_DETAILS,
    "incorrect_cvv": FailureCategory.INVALID_DETAILS,
    "cvv_invalid": FailureCategory.INVALID_DETAILS,
    "invalid_card_number": FailureCategory.INVALID_DETAILS,
    "invalid_expiry": FailureCategory.INVALID_DETAILS,
    "authentication_failed": FailureCategory.INVALID_DETAILS,
    "network_error": FailureCategory.NETWORK_FAILURE,
    "gateway_timeout": FailureCategory.NETWORK_FAILURE,
    "timeout": FailureCategory.NETWORK_FAILURE,
    "do_not_honour": FailureCategory.BANK_DECLINE,
    "issuer_declined": FailureCategory.BANK_DECLINE,
    "bank_declined": FailureCategory.BANK_DECLINE,
    "blocked_by_risk": FailureCategory.BANK_DECLINE,
}

# Keyword fallbacks for free-text error_description / error_source.
_KEYWORDS: tuple[tuple[tuple[str, ...], FailureCategory], ...] = (
    (("insufficient", "no balance", "low balance"), FailureCategory.INSUFFICIENT_FUNDS),
    (("expired",), FailureCategory.EXPIRED_CARD),
    (("timeout", "timed out", "network", "connection", "unreachable"),
     FailureCategory.NETWORK_FAILURE),
    (("cvv", "expiry date", "card number", "invalid details", "authentication"),
     FailureCategory.INVALID_DETAILS),
    (("declined by bank", "issuer", "bank decline", "do not honour", "risk"),
     FailureCategory.BANK_DECLINE),
)


def classify_failure(
    error_reason: str | None,
    error_description: str | None = None,
    error_source: str | None = None,
) -> FailureCategory:
    """Map provider failure fields to a domain category.

    Order of evidence: structured reason code first, then description text.
    Anything unmatched returns OTHER rather than pretending confidence.
    """
    if error_reason:
        normalized = error_reason.strip().lower().replace(" ", "_")
        direct = _REASON_MAP.get(normalized)
        if direct is not None:
            return direct
        # Snake-cased reason may still contain a keyword ("bank_declined_...").
        for keywords, category in _KEYWORDS:
            if any(k.replace(" ", "_") in normalized for k in keywords):
                return category

    haystack_parts = [part for part in (error_description, error_source) if part]
    if haystack_parts:
        haystack = " ".join(haystack_parts).lower()
        for keywords, category in _KEYWORDS:
            if any(keyword in haystack for keyword in keywords):
                return category

    return FailureCategory.OTHER


def map_provider_method(method: str | None) -> "PaymentMethod":
    """Translate a Razorpay `method` value into our PaymentMethod enum."""
    from app.models.enums import PaymentMethod

    mapping = {
        "upi": PaymentMethod.UPI,
        "card": PaymentMethod.CARD,
        "netbanking": PaymentMethod.NET_BANKING,
        "wallet": PaymentMethod.WALLET,
    }
    if method is None:
        return PaymentMethod.OTHER
    return mapping.get(method.strip().lower(), PaymentMethod.OTHER)
