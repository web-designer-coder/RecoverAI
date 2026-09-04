"""Audit read service — append-only storage, read-only API."""

import uuid

from sqlalchemy.orm import Session

from app.repositories import AuditRepository, PaymentRepository
from app.schemas.audit_schemas import AuditEventResponse


class AuditService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.audit = AuditRepository(session)
        self.payments = PaymentRepository(session)

    def list_events(
        self,
        merchant_id: uuid.UUID,
        category: str | None = None,
        limit: int = 200,
    ) -> list[AuditEventResponse]:
        events = self.audit.list_events(merchant_id, category=category, limit=limit)
        return self._to_responses(merchant_id, events)

    def list_by_payment(self, merchant_id: uuid.UUID, payment_id: uuid.UUID) -> list[AuditEventResponse]:
        return self._to_responses(
            merchant_id, self.audit.list_by_payment(merchant_id, payment_id)
        )

    def _to_responses(self, merchant_id: uuid.UUID, events) -> list[AuditEventResponse]:
        # Translate internal UUIDs into the external identifiers the UI shows.
        # Batch-load all unique payment IDs in a single query (Phase 32 P1 fix).
        unique_payment_ids = list({
            e.payment_id for e in events if e.payment_id is not None
        })
        external_ids: dict[uuid.UUID, str] = {}
        if unique_payment_ids:
            from sqlalchemy import select
            from app.models import Payment
            stmt = select(Payment.id, Payment.external_payment_id).where(
                Payment.id.in_(unique_payment_ids),
                Payment.merchant_id == merchant_id,
            )
            for pid, ext_id in self._session.execute(stmt).all():
                external_ids[pid] = ext_id

        return [
            AuditEventResponse(
                id=str(e.id),
                timestamp=e.created_at,
                event_type=e.event_type.value,
                category=e.category.value,
                actor_type=e.actor_type.value,
                payment_id=external_ids.get(e.payment_id),
                summary=e.summary,
                amount=float(e.amount) if e.amount is not None else None,
                metadata=dict(e.meta or {}),
            )
            for e in events
        ]
