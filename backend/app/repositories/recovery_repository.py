"""Recovery decision/action persistence."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Payment, RecoveryAction, RecoveryDecision
from app.models.enums import RecoveryActionStatus


class RecoveryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- reads ---------------------------------------------------------------

    def _verify_payment_ownership(self, payment_ids: list[uuid.UUID], merchant_id: uuid.UUID) -> list[uuid.UUID]:
        """Return the subset of payment_ids that belong to the given merchant.

        Raises ValueError if merchant_id is None — callers must always provide
        a merchant scope to prevent accidental cross-tenant access.
        """
        if not payment_ids:
            return []
        if merchant_id is None:
            raise ValueError("merchant_id is required for payment ownership verification")
        stmt = select(Payment.id).where(
            Payment.id.in_(payment_ids),
            Payment.merchant_id == merchant_id,
        )
        return list(self._session.scalars(stmt))

    def latest_decisions(
        self,
        payment_ids: list[uuid.UUID],
        merchant_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, RecoveryDecision]:
        """Current (highest version_number) decision per payment."""
        if not payment_ids:
            return {}
        # Defense-in-depth: verify payment ownership when merchant_id is provided.
        if merchant_id is not None:
            payment_ids = self._verify_payment_ownership(payment_ids, merchant_id)
            if not payment_ids:
                return {}
        stmt = (
            select(RecoveryDecision)
            .where(RecoveryDecision.payment_id.in_(payment_ids))
            .order_by(
                RecoveryDecision.payment_id,
                RecoveryDecision.version_number.desc(),
                RecoveryDecision.created_at.desc(),
            )
        )
        latest: dict[uuid.UUID, RecoveryDecision] = {}
        for d in self._session.scalars(stmt):
            latest.setdefault(d.payment_id, d)
        return latest

    def next_version_number(self, payment_id: uuid.UUID) -> int:
        """max(version_number) + 1 for a payment; 1 for its first decision."""
        from sqlalchemy import func

        current = self._session.scalar(
            select(func.max(RecoveryDecision.version_number))
            .where(RecoveryDecision.payment_id == payment_id)
        )
        return (current or 0) + 1

    def actions_for_payments(
        self,
        payment_ids: list[uuid.UUID],
        merchant_id: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, list[RecoveryAction]]:
        if not payment_ids:
            return {}
        # Defense-in-depth: verify payment ownership when merchant_id is provided.
        if merchant_id is not None:
            payment_ids = self._verify_payment_ownership(payment_ids, merchant_id)
            if not payment_ids:
                return {}
        stmt = (
            select(RecoveryAction)
            .where(RecoveryAction.payment_id.in_(payment_ids))
            .order_by(RecoveryAction.scheduled_at.desc().nullslast(), RecoveryAction.created_at.desc())
        )
        grouped: dict[uuid.UUID, list[RecoveryAction]] = {}
        for a in self._session.scalars(stmt):
            grouped.setdefault(a.payment_id, []).append(a)
        return grouped

    # -- writes ---------------------------------------------------------------

    def add_decision(self, decision: RecoveryDecision) -> RecoveryDecision:
        self._session.add(decision)
        return decision

    def add_action(self, action: RecoveryAction) -> RecoveryAction:
        self._session.add(action)
        return action

    def due_scheduled_actions(self, merchant_id: uuid.UUID, now: datetime | None = None) -> list[RecoveryAction]:
        """Retrieve SCHEDULED actions that are due (scheduled_at <= now) for the merchant's payments.
        Preserves merchant isolation and avoids premature execution.
        External scheduler must call this; this repository does NOT execute.
        """
        from datetime import timezone
        now = now or datetime.now(timezone.utc)
        stmt_ids = select(Payment.id).where(Payment.merchant_id == merchant_id)
        owned_ids = list(self._session.scalars(stmt_ids))
        if not owned_ids:
            return []
        stmt = select(RecoveryAction).where(
            RecoveryAction.payment_id.in_(owned_ids),
            RecoveryAction.status == RecoveryActionStatus.SCHEDULED,
            RecoveryAction.scheduled_at <= now,
        ).order_by(RecoveryAction.scheduled_at.asc())
        return list(self._session.scalars(stmt))
