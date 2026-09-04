"""Payment reconciliation foundation — provider state vs local state.

Reusable service boundary only (no scheduled worker yet, per Phase 3 scope):
given a provider payment id it fetches current truth from Razorpay, compares
it to our stored status, applies safe transitions through the same
precedence rules as webhook ingestion, and audits any change it makes.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Merchant
from app.models.enums import ActorType, AuditCategory, AuditEventType, PaymentStatus
from app.services.payment_ingestion_service import PaymentIngestionService, plan_transition
from app.services.providers.razorpay_client import RazorpayClient, build_razorpay_client

logger = logging.getLogger("recoverai.reconciliation")


@dataclass(frozen=True)
class ReconciliationResult:
    provider_payment_id: str
    provider_status: str | None
    local_status_before: PaymentStatus | None
    local_status_after: PaymentStatus | None
    changed: bool
    note: str


# Provider payment.status → internal target status. Provider states we do not
# model yet (refunds, disputes) map to None = "observe only".
_PROVIDER_STATUS_MAP: dict[str, PaymentStatus | None] = {
    "captured": PaymentStatus.RECOVERED,
    "authorized": PaymentStatus.AUTHORIZED,
    "failed": PaymentStatus.FAILED,
    "created": None,
    "pending": None,
    "refunded": None,
    "partially_refunded": None,
}


class PaymentReconciliationService:
    def __init__(self, session: Session, client: RazorpayClient | None = None) -> None:
        self._session = session
        self._ingestion = PaymentIngestionService(session)
        self._client = client  # lazily built when None (requires credentials)

    def reconcile(self, merchant: Merchant, provider_payment_id: str) -> ReconciliationResult:
        if self._client is None:
            self._client = build_razorpay_client()
        provider_payment = self._client.get_payment(provider_payment_id)

        payment = self._ingestion.payments.get_by_external_id(merchant.id, provider_payment_id)
        before: PaymentStatus | None = payment.status if payment else None
        provider_status = provider_payment.get("status")
        target = _PROVIDER_STATUS_MAP.get(str(provider_status).lower())

        if payment is None or target is None:
            note = (
                "PAYMENT_NOT_LOCAL" if payment is None else f"PROVIDER_STATE_OBSERVED_{str(provider_status).upper()}"
            )
            return ReconciliationResult(
                provider_payment_id, provider_status, before, before, False, note
            )

        transition = plan_transition(payment.status, target)
        if not transition.applied:
            return ReconciliationResult(
                provider_payment_id, provider_status, before, before, False, transition.note
            )

        payment.status = target
        self._ingestion.sync_provider_fields(payment, provider_payment)
        if target == PaymentStatus.RECOVERED:
            payment.next_action_at = None
        self._ingestion.audit.append(
            merchant_id=merchant.id,
            payment_id=payment.id,
            event_type=AuditEventType.PROVIDER_SYNC,
            category=AuditCategory.INGESTION,
            summary=(
                f"Reconciled from provider — {before.value if before else 'NEW'} → {target.value}"
            ),
            actor_type=ActorType.SYSTEM,
            metadata={
                "provider": "razorpay",
                "payment_id": provider_payment_id,
                "provider_status": provider_status,
                "processing_result": "RECONCILED",
            },
        )
        logger.info("Reconciled %s: %s -> %s", provider_payment_id, before, target)
        return ReconciliationResult(
            provider_payment_id, provider_status, before, target, True, "RECONCILED"
        )
