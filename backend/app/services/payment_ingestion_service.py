"""Payment ingestion — turns verified Razorpay webhook payloads into domain rows.

Responsibilities (Phase 3):
- locate or create the local Payment for a provider payment id
- apply status transitions through a deterministic precedence strategy so
  out-of-order deliveries can never downgrade a newer state
- persist PaymentFailure rows with normalized categories
- append concise audit events

This service contains NO recovery intelligence, NO policy execution and NO
notifications — those arrive in Phases 4–5. It only records reality.

Lifecycle mapping (documented decision, §12):
    provider authorized → PaymentStatus.AUTHORIZED
        Funds are held at the bank but NOT received. Deliberately distinct
        from RECOVERED; a payment is RECOVERED only on payment.captured.
    provider captured   → PaymentStatus.RECOVERED
    provider failed     → PaymentStatus.FAILED (+ PaymentFailure row)
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import Merchant, Payment, PaymentFailure, RecoveryAction
from app.models.enums import (
    ActorType,
    AuditCategory,
    AuditEventType,
    PaymentStatus,
    Priority,
    RecoveryActionStatus,
)
from app.repositories.audit_repository import AuditRepository
from app.repositories.payment_repository import PaymentRepository
from app.utils.failure_classification import classify_failure, map_provider_method
from app.utils.money import from_provider_minor_units

logger = logging.getLogger("recoverai.ingestion")


# ---------------------------------------------------------------------------
# Deterministic state-transition precedence (Phase 3 §6).
#
# Webhooks can arrive out of order. Transitions are only allowed "upward":
# a stale delivery must never pull a payment back into an older state.
# Higher number = newer knowledge about money movement.
_STATE_PRECEDENCE: dict[PaymentStatus, int] = {
    PaymentStatus.RECOVERED: 90,   # captured — money received (terminal top)
    PaymentStatus.AUTHORIZED: 70,  # funds held at bank
    PaymentStatus.PROCESSING: 50,  # internal: recovery in flight
    PaymentStatus.SCHEDULED: 40,
    PaymentStatus.QUEUED: 30,
    PaymentStatus.NEEDS_ACTION: 25,
    PaymentStatus.FAILED: 10,      # original failure observation
}

# Operator decisions (HALTED) are never overwritten by ingestion events;
# captured/RECOVERED is the one exception — received money outranks any
# operator state because it ends the recovery workflow factually.
_UNTOUCHABLE_BY_INGESTION = {PaymentStatus.HALTED}


@dataclass(frozen=True)
class TransitionResult:
    applied: bool
    previous_status: PaymentStatus | None
    new_status: PaymentStatus | None
    note: str


def plan_transition(current: PaymentStatus | None, incoming: PaymentStatus) -> TransitionResult:
    """Pure function deciding whether `incoming` may replace `current`.

    Rules:
    - RECOVERED (captured) always wins; re-captured is idempotent no-op.
    - AUTHORIZED applies unless the payment is already RECOVERED or HALTED.
    - FAILED applies only to brand-new payments or an existing FAILED record
      (a second failed attempt adds evidence, not a regression). It never
      overrides AUTHORIZED / RECOVERED / pipeline states.
    """
    if current == incoming:
        return TransitionResult(False, current, incoming, "NO_CHANGE")

    if incoming == PaymentStatus.RECOVERED:
        return TransitionResult(True, current, incoming, "PROCESSED")

    blocked = _UNTOUCHABLE_BY_INGESTION | {PaymentStatus.RECOVERED}
    if current in blocked:
        return TransitionResult(False, current, current, "STALE_IGNORED")

    if incoming == PaymentStatus.AUTHORIZED:
        if current is None:
            return TransitionResult(True, current, incoming, "PROCESSED")
        if _STATE_PRECEDENCE[current] < _STATE_PRECEDENCE[PaymentStatus.AUTHORIZED]:
            return TransitionResult(True, current, incoming, "PROCESSED")
        return TransitionResult(False, current, current, "STALE_IGNORED")

    if incoming == PaymentStatus.FAILED:
        if current is None or current == PaymentStatus.FAILED:
            return TransitionResult(True, current, incoming, "PROCESSED")
        return TransitionResult(False, current, current, "STALE_IGNORED")

    # Any other target status is not produced by webhook ingestion.
    return TransitionResult(False, current, current, "UNSUPPORTED_TRANSITION")


@dataclass(frozen=True)
class IngestionOutcome:
    payment_external_id: str
    transition: TransitionResult
    failure_created: bool


class PaymentIngestionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.payments = PaymentRepository(session)
        self.audit = AuditRepository(session)

    # -- public handlers -----------------------------------------------------

    def handle_payment_failed(self, merchant: Merchant, payload: dict[str, Any]) -> IngestionOutcome:
        payment_data = payload["payment"]
        external_id = payment_data["id"]
        amount = _extract_amount(payment_data)
        method = map_provider_method(payment_data.get("method"))
        category = classify_failure(
            payment_data.get("error_reason"),
            payment_data.get("error_description"),
            payment_data.get("error_source"),
        )

        payment = self.payments.get_by_external_id(merchant.id, external_id)
        if payment is None:
            payment = self._create_payment(
                merchant, payment_data, initial_status=PaymentStatus.FAILED
            )
            transition = TransitionResult(True, None, PaymentStatus.FAILED, "PROCESSED")
        else:
            transition = plan_transition(payment.status, PaymentStatus.FAILED)
            if transition.applied:
                payment.status = PaymentStatus.FAILED
            self.sync_provider_fields(payment, payment_data)
            # A failed delivery arriving after capture/authorization is stale:
            # write nothing to domain tables — the webhook ledger notes it.
            if transition.note == "STALE_IGNORED":
                return IngestionOutcome(external_id, transition, False)

        # Every distinct failed attempt is its own failure observation.
        payment.attempt_number += 1
        occurred_at = _extract_timestamp(payment_data.get("created_at")) or datetime.now(timezone.utc)
        failure = PaymentFailure(
            payment=payment,
            failure_code=payment_data.get("error_reason") or "unknown",
            failure_reason=(payment_data.get("error_description") or "Unspecified provider failure")[:500],
            failure_category=category,
            attempt_number=payment.attempt_number,
            occurred_at=occurred_at,
            meta=_sanitized_failure_meta(payment_data),
        )
        self._session.add(failure)

        self.audit.append(
            merchant_id=merchant.id,
            payment_id=payment.id,
            event_type=AuditEventType.PAYMENT_FAILED,
            category=AuditCategory.INGESTION,
            summary=f"Payment failed via Razorpay — ₹{amount:,.2f}",
            amount=amount,
            actor_type=ActorType.SYSTEM,
            metadata={
                "provider": "razorpay",
                "provider_event_id": payload.get("_event_id", ""),
                "event_type": payload.get("event", "payment.failed"),
                "payment_id": external_id,
                "processing_result": "CREATED" if transition.previous_status is None else transition.note,
                "failure_category": category.value,
            },
        )
        return IngestionOutcome(external_id, transition, True)

    def handle_payment_captured(self, merchant: Merchant, payload: dict[str, Any]) -> IngestionOutcome:
        payment_data = payload["payment"]
        external_id = payment_data["id"]
        amount = _extract_amount(payment_data)

        payment = self.payments.get_by_external_id(merchant.id, external_id)
        if payment is None:
            payment = self._create_payment(
                merchant, payment_data, initial_status=PaymentStatus.RECOVERED
            )
            transition = TransitionResult(True, None, PaymentStatus.RECOVERED, "PROCESSED")
        else:
            transition = plan_transition(payment.status, PaymentStatus.RECOVERED)
            if transition.applied:
                payment.status = PaymentStatus.RECOVERED
                payment.next_action_at = None
            self.sync_provider_fields(payment, payment_data)
            if not transition.applied and transition.note == "STALE_IGNORED":
                # Already RECOVERED — replayed capture must not re-count.
                transition = TransitionResult(False, transition.previous_status,
                                              transition.new_status, "ALREADY_RECOVERED")

        result = transition.note

        # Audit only on real transitions — replayed captures must not create
        # duplicate "recovered" history (no double counting).
        if transition.applied:
            self.audit.append(
                merchant_id=merchant.id,
                payment_id=payment.id,
                event_type=AuditEventType.PAYMENT_RECOVERED,
                category=AuditCategory.RESULT,
                summary=f"Payment recovered — ₹{amount:,.2f} (captured)",
                amount=amount,
                actor_type=ActorType.SYSTEM,
                metadata={
                    "provider": "razorpay",
                    "provider_event_id": payload.get("_event_id", ""),
                    "event_type": payload.get("event", "payment.captured"),
                    "payment_id": external_id,
                    "processing_result": result,
                },
            )
        return IngestionOutcome(external_id, transition, False)

    def handle_payment_authorized(self, merchant: Merchant, payload: dict[str, Any]) -> IngestionOutcome:
        payment_data = payload["payment"]
        external_id = payment_data["id"]

        payment = self.payments.get_by_external_id(merchant.id, external_id)
        if payment is None:
            payment = self._create_payment(
                merchant, payment_data, initial_status=PaymentStatus.AUTHORIZED
            )
            transition = TransitionResult(True, None, PaymentStatus.AUTHORIZED, "PROCESSED")
        else:
            transition = plan_transition(payment.status, PaymentStatus.AUTHORIZED)
            if transition.applied:
                payment.status = PaymentStatus.AUTHORIZED
            self.sync_provider_fields(payment, payment_data)

        if transition.applied:
            self.audit.append(
                merchant_id=merchant.id,
                payment_id=payment.id,
                event_type=AuditEventType.PAYMENT_AUTHORIZED,
                category=AuditCategory.INGESTION,
                summary="Payment authorized at provider — awaiting capture",
                actor_type=ActorType.SYSTEM,
                metadata={
                    "provider": "razorpay",
                    "provider_event_id": payload.get("_event_id", ""),
                    "event_type": payload.get("event", "payment.authorized"),
                    "payment_id": external_id,
                    "processing_result": transition.note,
                },
            )
        return IngestionOutcome(external_id, transition, False)

    def handle_payment_link_paid(self, merchant: Merchant, payload: dict[str, Any]) -> IngestionOutcome:
        """Phase 37 Point 6D -- Payment Link paid webhook correlation.
        Correlates payment_link.paid to RecoveryAction via external_reference.
        Stores new provider payment id in recovered_payment_id; updates original
        Payment to RECOVERED; records audit.
        """
        entity = payload.get("payment") or {}
        provider_payment_id = entity.get("id")
        reference_id = entity.get("reference_id") or (entity.get("notes") or {}).get("reference_id")

        if not provider_payment_id:
            raise ValueError("payment_link.paid missing entity.id")

        # 6D correlation: original failed Payment by reference (link reference_id = payment.external_payment_id)
        original = self.payments.get_by_external_id(merchant.id, reference_id) if reference_id else None
        if original is None:
            # No original to recover; record reality (new successful payment via link).
            original = self._create_payment(merchant, entity, initial_status=PaymentStatus.RECOVERED)

        # 6D: find RecoveryAction that launched this link (by external_reference / reference_id)
        from sqlalchemy import select
        stmt = select(RecoveryAction).where(RecoveryAction.payment_id == original.id)
        candidates = list(self._session.scalars(stmt))
        action = None
        for a in candidates:
            if a.external_reference == provider_payment_id or a.external_reference == reference_id:
                action = a
                break
        if action is None and candidates:
            action = candidates[-1]  # most recent action as fallback

        # 6D correlation result: store recovered provider payment in RecoveryAction.
        if action is not None:
            new_payment = self.payments.get_by_external_id(merchant.id, provider_payment_id)
            if new_payment is not None and action.recovered_payment_id is None:
                action.recovered_payment_id = new_payment.id
                action.status = RecoveryActionStatus.SUCCEEDED
                self._session.flush()

        # 6D: update original payment status and audit.
        if original.status != PaymentStatus.RECOVERED:
            original.status = PaymentStatus.RECOVERED
            original.next_action_at = None
            amount = _extract_amount(entity)
            self.audit.append(
                merchant_id=merchant.id,
                payment_id=original.id,
                event_type=AuditEventType.PAYMENT_RECOVERED,
                category=AuditCategory.RESULT,
                summary="Payment recovered via Payment Link -- " + str(amount),
                amount=amount,
                actor_type=ActorType.SYSTEM,
                metadata={
                    "provider": "razorpay",
                    "provider_event_id": payload.get("_event_id", ""),
                    "event_type": payload.get("event", "payment_link.paid"),
                    "payment_id": provider_payment_id,
                    "recovered_payment_id": str(original.id),
                    "reference_id": reference_id,
                    "processing_result": "PROCESSED",
                },
            )

        transition = TransitionResult(True, PaymentStatus.FAILED if original.attempt_number > 0 else None, PaymentStatus.RECOVERED, "PROCESSED")
        return IngestionOutcome(provider_payment_id, transition, False)

    # -- internals -------------------------------------------------------------

    def _create_payment(
        self,
        merchant: Merchant,
        payment_data: dict[str, Any],
        *,
        initial_status: PaymentStatus,
    ) -> Payment:
        """Create a local payment (plus placeholder customer) from provider data."""
        customer = self.payments.get_or_create_customer(
            merchant_id=merchant.id,
            external_customer_id=_customer_external_id(payment_data),
        )
        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            external_payment_id=payment_data["id"],
            amount=_extract_amount(payment_data),
            currency=payment_data.get("currency", "INR"),
            method=map_provider_method(payment_data.get("method")),
            status=initial_status,
            attempt_number=0,
            priority=Priority.MEDIUM,
            provider_order_id=payment_data.get("order_id"),
            provider_status=payment_data.get("status"),
        )
        self._session.add(payment)
        self._session.flush()  # assign PK before dependents reference it
        return payment

    def sync_provider_fields(self, payment: Payment, payment_data: dict[str, Any]) -> None:
        payment.provider_status = payment_data.get("status")
        order_id = payment_data.get("order_id")
        if order_id:
            payment.provider_order_id = order_id

    def find_by_provider_order_id(self, merchant: Merchant, order_id: str) -> Payment | None:
        """Correlation point for order-scoped events (e.g. order.paid)."""
        from sqlalchemy import select

        stmt = select(Payment).where(
            Payment.merchant_id == merchant.id,
            Payment.provider_order_id == order_id,
        )
        return self._session.scalars(stmt).first()


def _customer_external_id(payment_data: dict[str, Any]) -> str:
    """Best-effort stable customer key from provider data.

    Razorpay webhooks do not carry a first-class customer id here; notes may
    contain one. We never fabricate personal data — a deterministic anonymous
    key keeps FK constraints satisfied until Phase 7 maps real customers.
    """
    notes = payment_data.get("notes") or {}
    for key in ("customer_id", "external_customer_id"):
        value = notes.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:64]
    email = payment_data.get("email")
    if isinstance(email, str) and email.strip():
        # Opaque deterministic key (hashlib, not hash()) — the raw e-mail is
        # never stored on the payment or customer record here.
        digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        return f"CUST_RZP_{digest[:10].upper()}"
    return f"CUST_RZP_{payment_data['id'][-12:].upper()}"


def _extract_amount(payment_data: dict[str, Any]) -> Decimal:
    currency = payment_data.get("currency", "INR")
    return from_provider_minor_units(int(payment_data["amount"]), currency)


def _extract_timestamp(epoch_seconds: Any) -> datetime | None:
    if isinstance(epoch_seconds, (int, float)) and epoch_seconds > 0:
        return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return None


def _sanitized_failure_meta(payment_data: dict[str, Any]) -> dict[str, Any]:
    """Only diagnosis-relevant, non-sensitive fields survive into storage."""
    meta: dict[str, Any] = {"provider_status": payment_data.get("status")}
    for field in ("error_source", "error_step", "error_reason", "order_id"):
        value = payment_data.get(field)
        if value:
            meta[field] = value
    vpa = payment_data.get("vpa")
    if isinstance(vpa, str) and "@" in vpa:
        # Store only the bank/PSP half of a VPA — never the full handle.
        meta["vpa_host"] = vpa.split("@", 1)[1]
    return meta
