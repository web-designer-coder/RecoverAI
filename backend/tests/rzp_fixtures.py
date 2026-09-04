"""Sanitized Razorpay webhook fixtures + signing helpers (Test Mode style).

All values are synthetic test data — no real customer or payment information.
Signatures are computed over the exact raw bytes the test will send, mirroring
Razorpay's scheme: HMAC-SHA256(raw_body, webhook_secret), hex digest.
"""

import hashlib
import hmac
import json
from typing import Any

# Must match tests/conftest.py's RAZORPAY_WEBHOOK_SECRET env default.
WEBHOOK_SECRET = "test_webhook_secret_local_only"


def sign(raw_body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def canonical(payload: dict[str, Any]) -> bytes:
    """Serialize exactly once; the returned bytes are what gets signed+sent."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def payment_entity(
    pay_id: str = "pay_TEST_RECOVERAI_001",
    *,
    amount: int = 849900,
    currency: str = "INR",
    status: str = "failed",
    method: str = "upi",
    order_id: str | None = "order_TEST_RECOVERAI_001",
    created_at: int = 1756200000,
    error_reason: str | None = "insufficient_fund",
    error_description: str | None = "Insufficient funds in linked account",
    error_source: str | None = "bank",
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "id": pay_id,
        "amount": amount,
        "currency": currency,
        "status": status,
        "method": method,
        "created_at": created_at,
    }
    if order_id is not None:
        entity["order_id"] = order_id
    if error_reason is not None:
        entity["error_source"] = error_source
        entity["error_step"] = "payment_initiation"
        entity["error_reason"] = error_reason
        entity["error_description"] = error_description
    return entity


def event(
    event_type: str,
    pay_id: str = "pay_TEST_RECOVERAI_001",
    **entity_kwargs: Any,
) -> dict[str, Any]:
    return {
        "event": event_type,
        "payload": {"payment": {"entity": payment_entity(pay_id, **entity_kwargs)}},
    }


def post(client, payload: dict[str, Any], *, event_id: str, signature: str | None = None, raw: bytes | None = None):
    """POST a signed fixture. `raw` overrides the serialized body (for
    tampering tests); `signature=None` omits the header entirely."""
    body = raw if raw is not None else canonical(payload)
    headers = {"x-razorpay-event-id": event_id}
    if signature is not None:
        headers["x-razorpay-signature"] = signature
    return client.post(
        "/api/webhooks/razorpay", content=body,
        headers={**headers, "Content-Type": "application/json"},
    )
