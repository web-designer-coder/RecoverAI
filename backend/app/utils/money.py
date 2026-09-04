"""Money conversion between provider minor units and our NUMERIC storage.

Razorpay (and most gateways) transmit amounts as integers in the currency's
smallest unit: for INR, ₹8,499.00 arrives as ``849900`` paise.

This module is the SINGLE conversion point — no handler may divide by 100
itself. Currencies differ in minor-unit exponent (ISO 4217): INR/USD use 2,
JPY has zero, KWD uses 3. We encode that explicitly instead of assuming /100
everywhere.

Storage convention (Phase 2 money policy): NUMERIC(14,2) in major units,
Python `Decimal` end-to-end. Floats never touch money.
"""

from decimal import Decimal

# ISO 4217 minor-unit exponents for currencies this system may realistically
# handle. INR is primary; the map exists so a future currency cannot silently
# inherit India's /100 behaviour.
_MINOR_UNITS: dict[str, int] = {
    "INR": 2,  # paise
    "USD": 2,  # cents
    "EUR": 2,
    "GBP": 2,
    "AED": 2,
    "JPY": 0,  # zero-decimal
    "KRW": 0,  # zero-decimal
    "KWD": 3,  # fils
}


def minor_units_for_currency(currency: str) -> int:
    """Return the ISO 4217 minor-unit exponent (e.g. INR -> 2)."""
    try:
        return _MINOR_UNITS[currency.upper()]
    except KeyError:
        raise ValueError(
            f"Unsupported currency '{currency}'. Extend utils.money._MINOR_UNITS "
            "explicitly before accepting it."
        ) from None


def from_provider_minor_units(amount: int, currency: str) -> Decimal:
    """Convert a provider integer amount (e.g. 849900 paise) to major units
    as an exact Decimal (₹8499.00)."""
    if amount < 0:
        raise ValueError("Provider amounts are never negative.")
    exponent = minor_units_for_currency(currency)
    value = Decimal(amount) if exponent else Decimal(amount)
    return value.scaleb(-exponent).quantize(Decimal(1).scaleb(-exponent))


def to_provider_minor_units(amount: Decimal, currency: str) -> int:
    """Convert our stored Decimal major units back to provider minor units
    (₹8499.00 -> 849900). Raises on precision loss beyond the minor unit."""
    exponent = minor_units_for_currency(currency)
    scaled = Decimal(amount).scaleb(exponent)
    result = int(scaled)
    if Decimal(result) != scaled:
        raise ValueError(f"Amount {amount} {currency} has sub-minor-unit precision.")
    return result
