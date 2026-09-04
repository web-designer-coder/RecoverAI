"""Razorpay REST client (Test Mode) — read-only provider API access.

Used for reconciliation/verification only; webhook ingestion is the primary
event mechanism and never goes through this client.

Security:
- Credentials come exclusively from settings (RAZORPAY_KEY_ID / KEY_SECRET).
- The httpx auth pair is attached per-request and never logged.
- Every failure mode (4xx / 5xx / timeout / connection error) maps to a
  structured exception carrying a safe message — no secrets, no raw auth data.
"""

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("recoverai.razorpay")

DEFAULT_TIMEOUT_SECONDS = 10.0


class RazorpayClientError(Exception):
    """Structured provider error. `code` is safe to expose; `detail` stays
    in server logs only."""

    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider_status_code: int | None = None
        self.status_code = status_code


class RazorpayNotConfigured(RazorpayClientError):
    def __init__(self) -> None:
        super().__init__(
            code="RAZORPAY_NOT_CONFIGURED",
            message="Razorpay credentials are not configured for this environment.",
            status_code=503,
        )


class RazorpayNotFound(RazorpayClientError):
    def __init__(self, payment_id: str) -> None:
        super().__init__(
            code="PROVIDER_PAYMENT_NOT_FOUND",
            message=f"Payment {payment_id} does not exist at the provider.",
            status_code=404,
        )
        self.provider_status_code = 404


class RazorpayAuthError(RazorpayClientError):
    def __init__(self) -> None:
        super().__init__(
            code="PROVIDER_AUTH_ERROR",
            message="Provider rejected the configured credentials.",
            status_code=502,
        )


class RazorpayTimeout(RazorpayClientError):
    def __init__(self) -> None:
        super().__init__(
            code="PROVIDER_TIMEOUT",
            message="The provider API did not respond in time.",
            status_code=504,
        )


class RazorpayUnavailable(RazorpayClientError):
    def __init__(self, provider_status: int | None) -> None:
        super().__init__(
            code="PROVIDER_ERROR",
            message="The provider API returned an unexpected response.",
            status_code=502,
        )
        self.provider_status_code = provider_status


class RazorpayClient:
    """Thin authenticated wrapper over GET https://api.razorpay.com/v1/payments/:id."""

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self._key_id = key_id if key_id is not None else settings.razorpay_key_id
        self._key_secret = (
            key_secret if key_secret is not None else settings.razorpay_key_secret
        )
        if not (self._key_id and self._key_secret):
            raise RazorpayNotConfigured()
        self._timeout = timeout
        # transport injection exists for tests (httpx.MockTransport); the app
        # always uses real connections.
        kwargs: dict[str, Any] = {
            "base_url": "https://api.razorpay.com/v1",
            "timeout": self._timeout,
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.Client(**kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RazorpayClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def get_payment(self, payment_id: str) -> dict[str, Any]:
        """Fetch one payment by provider id. Raises structured errors."""
        url = f"/payments/{payment_id}"
        try:
            response = self._client.get(url, auth=(self._key_id, self._key_secret))
        except httpx.TimeoutException:
            logger.warning("Razorpay GET %s timed out after %.1fs", url, self._timeout)
            raise RazorpayTimeout() from None
        except httpx.HTTPError as exc:
            # Log the exception class only — never headers/auth material.
            logger.warning("Razorpay GET %s failed: %s", url, exc.__class__.__name__)
            raise RazorpayUnavailable(None) from None

        if response.status_code == 404:
            raise RazorpayNotFound(payment_id)
        if response.status_code == 401:
            logger.error("Razorpay rejected credentials (HTTP 401).")
            raise RazorpayAuthError()
        if response.status_code >= 400:
            logger.warning("Razorpay GET %s -> HTTP %d", url, response.status_code)
            raise RazorpayUnavailable(response.status_code)

        return response.json()

    def create_payment_link(
        self,
        *,
        amount_minor_units: int,
        currency: str,
        reference_id: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a Razorpay Payment Link (POST /payment_links).

        This is the one genuinely supported, safe, server-side recovery
        operation in Test Mode: it does NOT charge anything by itself — the
        customer completes the payment and the result arrives later via
        webhook (payment.captured), preserving event-driven correctness.

        Returns the raw link payload (id / short_url). Never logged with
        credentials.
        """
        url = "/payment_links"
        payload = {
            "amount": amount_minor_units,
            "currency": currency,
            "reference_id": reference_id,
            "description": description,
        }
        try:
            response = self._client.post(
                url, json=payload, auth=(self._key_id, self._key_secret)
            )
        except httpx.TimeoutException:
            logger.warning("Razorpay POST %s timed out after %.1fs", url, self._timeout)
            raise RazorpayTimeout() from None
        except httpx.HTTPError as exc:
            logger.warning("Razorpay POST %s failed: %s", url, exc.__class__.__name__)
            raise RazorpayUnavailable(None) from None

        if response.status_code == 401:
            logger.error("Razorpay rejected credentials (HTTP 401).")
            raise RazorpayAuthError()
        if response.status_code >= 400:
            logger.warning("Razorpay POST %s -> HTTP %d", url, response.status_code)
            raise RazorpayUnavailable(response.status_code)

        return response.json()


def build_razorpay_client() -> RazorpayClient:
    """Factory used by services; fails fast when credentials are missing."""
    return RazorpayClient()
