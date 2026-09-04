"""Razorpay webhook processing pipeline.

Order of operations (each step gates the next):

    1. verify HMAC-SHA256 signature against the EXACT raw request bytes
    2. parse JSON and validate minimal shape
    3. register the delivery in `webhook_events` (idempotency key:
       provider + x-razorpay-event-id)
    4. dispatch to a handler; handler + event row commit atomically
    5. on failure: rollback everything, mark the event FAILED in its own
       transaction, return non-2xx so Razorpay retries

Signature verification is now done by the caller (the webhook endpoint) to support
merchant-specific webhook secrets. The caller must verify the signature before
invoking this service.

Payload policy: only the SHA-256 hash of the raw body is stored.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Merchant, WebhookEvent
from app.models.webhook import WebhookStatus
from app.services.payment_ingestion_service import PaymentIngestionService

logger = logging.getLogger("recoverai.webhook")

SIGNATURE_HEADER = "x-razorpay-signature"
EVENT_ID_HEADER = "x-razorpay-event-id"

# Events this phase handles. Everything else is acknowledged (2xx) as
# UNSUPPORTED_EVENT so Razorpay stops retrying, without touching domain data.
SUPPORTED_EVENTS = {
    "payment.failed": "handle_payment_failed",
    "payment.captured": "handle_payment_captured",
    "payment.authorized": "handle_payment_authorized",
    "payment_link.paid": "handle_payment_link_paid",
}


class InvalidSignatureError(Exception):
    """Raised when the webhook signature does not verify."""


class InvalidPayloadError(Exception):
    """Raised when the body is not parseable or misses required fields."""


def compute_signature(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, signature: str | None, secret: str) -> None:
    """Constant-time verification against the exact raw bytes received."""
    if not secret:
        # No secret configured → nothing can be verified → refuse processing.
        raise InvalidSignatureError("Webhook secret is not configured")
    if not signature:
        raise InvalidSignatureError("Missing signature header")
    expected = compute_signature(raw_body, secret)
    if not hmac.compare_digest(expected, signature.strip()):
        raise InvalidSignatureError("Signature mismatch")


class RazorpayWebhookService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._ingestion = PaymentIngestionService(session)

    # -- entry point -----------------------------------------------------------

    def handle(
        self,
        *,
        merchant: Merchant,
        raw_body: bytes,
        signature: str | None,
        event_id: str | None,
    ) -> dict[str, str]:
        """Process one delivery. Assumes signature has already been verified by the caller.
        Returns a small ack dict for the route;
        raises AppError subclasses only for client mistakes (4xx).
        """
        # 1. Signature verification already done by caller.
        # 2. parse JSON and validate minimal shape.
        payload_hash = hashlib.sha256(raw_body).hexdigest()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidPayloadError(f"Body is not valid JSON ({exc.__class__.__name__})") from None

        if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
            raise InvalidPayloadError("Payload must include an 'event' string")

        if not event_id or not event_id.strip():
            raise InvalidPayloadError(f"Missing {EVENT_ID_HEADER} header")
        event_id = event_id.strip()
        event_type = payload["event"]

        # 3. idempotency gate.
        event = self._register_event(event_id, event_type, payload_hash)
        if event is None:
            return {"status": "duplicate", "result": "DUPLICATE_EVENT"}

        # order.paid is intentionally deferred (Phase 3 §13): captured events
        # already correlate payments by provider payment id, and order-scoped
        # duplication would add double-count risk without new information.
        handler_name = SUPPORTED_EVENTS.get(event_type)
        if handler_name is None:
            self._finish_event(event, WebhookStatus.PROCESSED, "UNSUPPORTED_EVENT")
            return {"status": "ignored", "result": "UNSUPPORTED_EVENT"}

        # payment_link.paid carries a different payload shape: payload.payment_link.entity
        # but also includes the linked payment details under payload.payment.entity
        # for correlation. Normalize both shapes.
        if event_type == "payment_link.paid":
            # For payment_link events, the link entity is primary; the linked
            # payment (if completed) appears in nested structures.
            link_entity = payload.get("payload", {}).get("payment_link", {}).get("entity")
            payment_payload = payload.get("payload", {}).get("payment", {}).get("entity")
            # If no direct payment entity but link has reference to completed payment,
            # synthesize from link notes.
            if not isinstance(payment_payload, dict) or "id" not in payment_payload:
                if isinstance(link_entity, dict) and "id" in link_entity:
                    # The completed payment id comes from the link's entity id
                    # when the event is a paid confirmation (provider treats it as a completed payment).
                    payment_payload = link_entity
        else:
            payment_payload = payload.get("payload", {}).get("payment", {}).get("entity")
        if not isinstance(payment_payload, dict) or "id" not in payment_payload:
            raise InvalidPayloadError("Missing payload.payment.entity.id")
        # Handlers work on a normalized shape: {event, payment(entity), _event_id}.
        normalized: dict[str, Any] = {
            "event": event_type,
            "payment": payment_payload,
            "_event_id": event_id,
        }

        try:
            handler = getattr(self._ingestion, handler_name)
            outcome = handler(merchant, normalized)
            self._finish_event(
                event, WebhookStatus.PROCESSED, outcome.transition.note or "PROCESSED"
            )
            self._session.commit()
        except Exception:
            # Never acknowledge a partially processed event. Roll back every
            # domain write, then record the failure in its own transaction.
            self._session.rollback()
            logger.exception("Webhook %s (%s) processing failed", event_id, event_type)
            self._mark_failed(event_id, event_type, payload_hash)
            raise

        logger.info(
            "Webhook %s %s processed: %s", event_id, event_type, outcome.transition.note
        )
        return {"status": "processed", "result": outcome.transition.note or "PROCESSED"}

    # -- internals ---------------------------------------------------------------

    def _register_event(
        self, event_id: str, event_type: str, payload_hash: str
    ) -> WebhookEvent | None:
        """Insert the delivery row. Returns None when it was already processed.

        A previously FAILED/RECEIVED row is reused so a retry can complete.
        """
        existing = (
            self._session.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == "razorpay",
                WebhookEvent.provider_event_id == event_id,
            )
            .one_or_none()
        )
        if existing is not None:
            if existing.status == WebhookStatus.PROCESSED:
                logger.info("Duplicate webhook delivery ignored: %s", event_id)
                return None
            # Retry path: reset the stale row in place.
            existing.event_type = event_type
            existing.payload_hash = payload_hash
            existing.status = WebhookStatus.RECEIVED
            existing.error_message = None
            self._session.flush()
            return existing

        event = WebhookEvent(
            provider="razorpay",
            provider_event_id=event_id,
            event_type=event_type,
            status=WebhookStatus.RECEIVED,
            payload_hash=payload_hash,
        )
        self._session.add(event)
        try:
            self._session.flush()  # surface unique violations inside this transaction
        except IntegrityError:
            # Concurrent delivery inserted the same event_id between our query
            # and flush.  Roll back the failed insert, then re-query — if the
            # other transaction already marked it PROCESSED we treat this as a
            # duplicate; otherwise hand back the existing row for retry.
            self._session.rollback()
            existing = (
                self._session.query(WebhookEvent)
                .filter(
                    WebhookEvent.provider == "razorpay",
                    WebhookEvent.provider_event_id == event_id,
                )
                .one_or_none()
            )
            if existing is None:
                # Extremely unlikely: row vanished after rollback. Re-raise.
                raise
            if existing.status == WebhookStatus.PROCESSED:
                logger.info("Duplicate webhook delivery ignored (race): %s", event_id)
                return None
            # Retry path: reset the stale row in place.
            existing.event_type = event_type
            existing.payload_hash = payload_hash
            existing.status = WebhookStatus.RECEIVED
            existing.error_message = None
            self._session.flush()
            return existing
        return event

    def _finish_event(
        self, event: WebhookEvent, status: WebhookStatus, result: str
    ) -> None:
        event.status = status
        event.result = result[:32]
        event.processed_at = datetime.now(timezone.utc)

    def _mark_failed(
        self, event_id: str, event_type: str, payload_hash: str
    ) -> None:
        """Standalone transaction: persist the FAILED marker after a rollback."""
        session = self._session
        try:
            existing = (
                session.query(WebhookEvent)
                .filter(
                    WebhookEvent.provider == "razorpay",
                    WebhookEvent.provider_event_id == event_id,
                )
                .one_or_none()
            )
            if existing is None:
                existing = WebhookEvent(
                    provider="razorpay",
                    provider_event_id=event_id,
                    event_type=event_type,
                    payload_hash=payload_hash,
                )
                session.add(existing)
            existing.status = WebhookStatus.FAILED
            existing.error_message = "Processing failed; waiting for provider retry."
            existing.processed_at = None
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Could not record FAILED state for webhook %s", event_id)