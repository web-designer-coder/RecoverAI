"""Application error type mapped to the consistent API error envelope."""

from app.models.enums import FailureCategory


class AppError(Exception):
    """Raised by services; rendered by the global exception handler as
    {"error": {"code": ..., "message": ...}} with an appropriate status."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def payment_not_found(payment_id: str) -> AppError:
    return AppError(
        code="PAYMENT_NOT_FOUND",
        message=f"Payment {payment_id} was not found.",
        status_code=404,
    )


def merchant_not_found() -> AppError:
    return AppError(
        code="MERCHANT_NOT_FOUND",
        message="No merchant is configured. Run `python -m app.seed` first.",
        status_code=503,
    )


def unauthorized(message: str = "Authentication required") -> AppError:
    return AppError(
        code="UNAUTHORIZED",
        message=message,
        status_code=401,
    )


def not_implemented(feature: str, phase: str) -> AppError:
    return AppError(
        code="NOT_IMPLEMENTED_YET",
        message=f"{feature} is not implemented for this phase; it arrives in {phase}.",
        status_code=501,
    )


CATEGORY_LABELS: dict[str, str] = {
    FailureCategory.INSUFFICIENT_FUNDS.value: "Insufficient Funds",
    FailureCategory.EXPIRED_CARD.value: "Expired Card",
    FailureCategory.NETWORK_FAILURE.value: "Network Failure",
    FailureCategory.BANK_DECLINE.value: "Bank Decline",
    FailureCategory.INVALID_DETAILS.value: "Invalid Details",
    FailureCategory.OTHER.value: "Other",
}
