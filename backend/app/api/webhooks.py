"""Razorpay webhook endpoint.

The signature is verified against the EXACT raw request bytes — the body is
read via ``await request.body()`` before any parsing, never re-serialized.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.dependencies import DbSession
from app.repositories.payment_repository import MerchantRepository
from app.services.razorpay_webhook_service import (
    EVENT_ID_HEADER,
    SIGNATURE_HEADER,
    InvalidPayloadError,
    InvalidSignatureError,
    RazorpayWebhookService,
    verify_signature,  # Import the verify_signature function
)
from app.utils.errors import AppError

logger = logging.getLogger("recoverai.webhook")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@router.post(
    "/razorpay",
    summary="Razorpay webhook receiver (Test Mode)",
    description=(
        "Verifies the x-razorpay-signature HMAC against the raw request bytes, "
        "deduplicates deliveries by x-razorpay-event-id, then records the "
        "payment event transactionally. Returns 2xx for processed, duplicate "
        "and unsupported events; 4xx for invalid signatures/payloads; 5xx so "
        "the provider retries transient failures."
    ),
    responses={
        400: {"description": "Invalid signature or payload"},
        500: {"description": "Transient processing failure — provider should retry"},
    },
)
async def receive_razorpay_webhook(
    request: Request,
    session: DbSession,
) -> JSONResponse:
    # Raw bytes FIRST — verification must see exactly what Razorpay signed.
    raw_body = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER)
    event_id = request.headers.get(EVENT_ID_HEADER)

    # We'll try to find a merchant by verifying the signature with their webhook secret.
    merchant = None
    merchant_repo = MerchantRepository(session)

    # First, try to find a merchant with a specific webhook secret configured.
    candidates = merchant_repo.get_merchants_with_webhook_secret()
    for candidate in candidates:
        try:
            # Decrypt the webhook secret for this candidate.
            from app.utils.encryption import decrypt_value
            webhook_secret = decrypt_value(candidate.razorpay_webhook_secret_encrypted)
            # Verify the signature with this secret.
            verify_signature(raw_body, signature, webhook_secret)
            merchant = candidate
            break
        except Exception:
            # If decryption fails or signature verification fails, try the next candidate.
            continue

    # If we still don't have a merchant, return an error.
    if merchant is None:
        return _error("INVALID_SIGNATURE", "Webhook signature verification failed.", 400)

    # Now that we have a merchant, process the webhook.
    service = RazorpayWebhookService(session)
    try:
        ack = service.handle(
            merchant=merchant,
            raw_body=raw_body,
            signature=signature,
            event_id=event_id,
        )
    except InvalidSignatureError as exc:
        # This should not happen because we already verified the signature, but just in case.
        logger.warning("Rejected Razorpay webhook: %s", exc)
        return _error("INVALID_SIGNATURE", "Webhook signature verification failed.", 400)
    except InvalidPayloadError as exc:
        return _error("INVALID_PAYLOAD", str(exc), 400)
    except AppError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        # Transient/internal failure — non-2xx so Razorpay retries. Details
        # stay in server logs.
        logger.exception("Razorpay webhook processing failed")
        return _error(
            "DATABASE_ERROR",
            "Webhook could not be processed; the delivery will be retried.",
            500,
        )

    return JSONResponse(status_code=200, content=ack)