"""Provider execution abstraction — the ONLY path from policy approval to Razorpay.

Reality first (Phase 5 rule §22/23): a failed UPI/card payment cannot be
silently re-charged by an arbitrary "retry" API — no such generic operation
exists at Razorpay. What IS genuinely supported and safe server-side is
creating a Payment Link (POST /v1/payment_links): it moves no money itself;
the customer completes it and the outcome arrives later via webhook.

So the provider layer supports exactly:

    RETRY               → create payment link → PROCESSING (awaiting webhook)
    PAYMENT_UPDATE      → CUSTOMER_ACTION_REQUIRED (no provider call)
    CUSTOMER_NOTIFICATION → CUSTOMER_ACTION_REQUIRED (no provider call)
    ESCALATE / STOP     → never reach this layer (policy/execution handle)

Anything else would be demo theatrics, and is refused by design.
"""

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models.enums import RecommendedAction
from app.services.providers.razorpay_client import (
    RazorpayClient,
    build_razorpay_client,
)
from app.utils.money import to_provider_minor_units

logger = logging.getLogger("recoverai.provider")


class ExecutionStatus(str, enum.Enum):
    SUCCEEDED = "SUCCEEDED"                    # provider confirmed final success
    PROCESSING = "PROCESSING"                  # provider op accepted; result pending (webhook)
    CUSTOMER_ACTION_REQUIRED = "CUSTOMER_ACTION_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ProviderExecutionResult:
    status: ExecutionStatus
    message: str
    external_reference: str | None = None       # opaque provider id (never secrets)
    metadata: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(Protocol):
    def get_payment(self, provider_payment_id: str) -> dict[str, Any]: ...

    def execute_recovery(
        self,
        *,
        action_type: RecommendedAction,
        amount,
        currency: str,
        reference_id: str,
    ) -> ProviderExecutionResult: ...


class RazorpayPaymentProvider:
    """Razorpay Test Mode implementation over the existing Phase 3 client."""

    def __init__(self, client=None) -> None:
        # 39B-4: accept injected client (tests, reconciliation); create only when needed.
        self._client = client

    def get_payment(self, provider_payment_id: str) -> dict[str, Any]:
        return self._client.get_payment(provider_payment_id)

    def execute_recovery(
        self,
        *,
        action_type: RecommendedAction,
        amount,
        currency: str,
        reference_id: str,
    ) -> ProviderExecutionResult:
        # 39B-4: when no injected client (production path), create a fresh
        # client per call and close after use. When a client is injected
        # (tests, reconciliation), the caller owns the lifecycle.
        if self._client is None:
            client = build_razorpay_client()
            with client:
                return self._do_execute(client, action_type, amount, currency, reference_id)
        return self._do_execute(self._client, action_type, amount, currency, reference_id)

    def _do_execute(self, client, action_type, amount, currency, reference_id):
        if action_type is not RecommendedAction.RETRY:
            # Instrument/notification actions need the customer in the loop.
            return ProviderExecutionResult(
                status=ExecutionStatus.CUSTOMER_ACTION_REQUIRED,
                message=(
                    f"{action_type.value} requires the customer to act; RecoverAI "
                    "does not pretend to complete it server-side."
                ),
            )
        link = client.create_payment_link(
            amount_minor_units=to_provider_minor_units(amount, currency),
            currency=currency,
            reference_id=reference_id,
            description=f"RecoverAI recovery for {reference_id}",
        )
        return ProviderExecutionResult(
            status=ExecutionStatus.PROCESSING,
            message="Payment link created; recovery completes when the customer pays "
                    "(confirmed via webhook).",
            external_reference=str(link.get("id")),
            metadata={"short_url": str(link.get("short_url"))},
        )


def build_payment_provider() -> RazorpayPaymentProvider:
    """Fails fast (RazorpayNotConfigured) when credentials are missing."""
    return RazorpayPaymentProvider(build_razorpay_client())
