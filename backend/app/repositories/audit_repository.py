"""Audit persistence with tracing capabilities.

The repository deliberately exposes append + reads only. Updates and deletes are
impossible through this layer, and blocked at the database level by a trigger
created in the initial migration (SQLSTATE 55006).

Phase 6 enhancement: Added tracing methods to link audit events with decisions,
policy evaluations, and recovery actions for complete auditability.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, RecoveryDecision, PolicyEvaluation, RecoveryAction
from app.models.enums import ActorType, AuditCategory, AuditEventType


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        *,
        merchant_id: uuid.UUID,
        event_type: AuditEventType,
        category: AuditCategory,
        summary: str,
        payment_id: uuid.UUID | None = None,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: str | None = None,
        amount: Decimal | float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            merchant_id=merchant_id,
            payment_id=payment_id,
            event_type=event_type,
            category=category,
            actor_type=actor_type,
            actor_id=actor_id,
            summary=summary,
            amount=amount,
            meta=metadata,
        )
        self._session.add(event)
        return event

    def list_events(
        self,
        merchant_id: uuid.UUID,
        category: str | None = None,
        limit: int = 200,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.merchant_id == merchant_id)
        if category and category != "ALL":
            stmt = stmt.where(AuditEvent.category == category)
        stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit)
        return list(self._session.scalars(stmt))

    def list_by_payment(self, merchant_id: uuid.UUID, payment_id: uuid.UUID) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.merchant_id == merchant_id, AuditEvent.payment_id == payment_id)
            .order_by(AuditEvent.created_at.desc())
        )
        return list(self._session.scalars(stmt))

    def list_by_decision(self, merchant_id: uuid.UUID, decision_id: uuid.UUID) -> list[AuditEvent]:
        """List audit events associated with a specific recovery decision."""
        stmt = (
            select(AuditEvent)
            .join(RecoveryDecision, AuditEvent.payment_id == RecoveryDecision.payment_id)
            .where(
                AuditEvent.merchant_id == merchant_id,
                RecoveryDecision.id == decision_id
            )
            .order_by(AuditEvent.created_at.desc())
        )
        return list(self._session.scalars(stmt))

    def list_by_policy_evaluation(self, merchant_id: uuid.UUID, evaluation_id: uuid.UUID) -> list[AuditEvent]:
        """List audit events associated with a specific policy evaluation."""
        stmt = (
            select(AuditEvent)
            .join(PolicyEvaluation, AuditEvent.payment_id == PolicyEvaluation.payment_id)
            .where(
                AuditEvent.merchant_id == merchant_id,
                PolicyEvaluation.id == evaluation_id
            )
            .order_by(AuditEvent.created_at.desc())
        )
        return list(self._session.scalars(stmt))

    def list_by_recovery_action(self, merchant_id: uuid.UUID, action_id: uuid.UUID) -> list[AuditEvent]:
        """List audit events associated with a specific recovery action."""
        stmt = (
            select(AuditEvent)
            .join(RecoveryAction, AuditEvent.payment_id == RecoveryAction.payment_id)
            .where(
                AuditEvent.merchant_id == merchant_id,
                RecoveryAction.id == action_id
            )
            .order_by(AuditEvent.created_at.desc())
        )
        return list(self._session.scalars(stmt))

    def get_decision_audit_trail(self, merchant_id: uuid.UUID, payment_id: uuid.UUID) -> dict:
        """Get complete audit trail for a payment including decision, policy evaluation, and actions."""
        # Get payment decision
        decision_stmt = (
            select(RecoveryDecision)
            .where(RecoveryDecision.payment_id == payment_id)
            .order_by(RecoveryDecision.version_number.desc())
            .limit(1)
        )
        decision = self._session.scalars(decision_stmt).first()

        # Get policy evaluation if decision exists
        policy_evaluation = None
        if decision:
            pe_stmt = (
                select(PolicyEvaluation)
                .where(PolicyEvaluation.recovery_decision_id == decision.id)
                .order_by(PolicyEvaluation.evaluated_at.desc())
                .limit(1)
            )
            policy_evaluation = self._session.scalars(pe_stmt).first()

        # Get recovery actions
        actions_stmt = (
            select(RecoveryAction)
            .where(RecoveryAction.payment_id == payment_id)
            .order_by(RecoveryAction.created_at.desc())
        )
        actions = list(self._session.scalars(actions_stmt))

        # Get audit events for each
        decision_audit = []
        if decision:
            decision_audit = self.list_by_decision(merchant_id, decision.id)

        policy_evaluation_audit = []
        if policy_evaluation:
            policy_evaluation_audit = self.list_by_policy_evaluation(merchant_id, policy_evaluation.id)

        # Batch-load audit events for ALL actions in one query (Phase 32 P2 fix).
        actions_audit = []
        if actions:
            stmt = (
                select(AuditEvent)
                .join(RecoveryAction, AuditEvent.payment_id == RecoveryAction.payment_id)
                .where(
                    AuditEvent.merchant_id == merchant_id,
                    RecoveryAction.id.in_([a.id for a in actions]),
                )
                .order_by(AuditEvent.created_at.desc())
            )
            actions_audit = list(self._session.scalars(stmt))

        # Get payment-level audit events
        payment_audit = self.list_by_payment(merchant_id, payment_id)

        return {
            "payment_id": str(payment_id),
            "decision": {
                "id": str(decision.id) if decision else None,
                "version_number": decision.version_number if decision else None,
                "created_at": decision.created_at.isoformat() if decision else None
            },
            "policy_evaluation": {
                "id": str(policy_evaluation.id) if policy_evaluation else None,
                "policy_version": policy_evaluation.policy_version if policy_evaluation else None,
                "decision": policy_evaluation.decision if policy_evaluation else None,
                "evaluated_at": policy_evaluation.evaluated_at.isoformat() if policy_evaluation else None
            } if policy_evaluation else None,
            "actions": [
                {
                    "id": str(action.id),
                    "action_type": action.action_type.value,
                    "status": action.status.value,
                    "created_at": action.created_at.isoformat(),
                    "policy_evaluation_id": str(action.policy_evaluation_id) if action.policy_evaluation_id else None
                }
                for action in actions
            ],
            "audit_events": {
                "payment_level": [self._audit_event_to_dict(e) for e in payment_audit],
                "decision_level": [self._audit_event_to_dict(e) for e in decision_audit],
                "policy_evaluation_level": [self._audit_event_to_dict(e) for e in policy_evaluation_audit],
                "action_level": [self._audit_event_to_dict(e) for e in actions_audit]
            }
        }

    def _audit_event_to_dict(self, event: AuditEvent) -> dict:
        """Convert AuditEvent to dictionary for API response."""
        return {
            "id": str(event.id),
            "timestamp": event.created_at.isoformat(),
            "event_type": event.event_type.value,
            "category": event.category.value,
            "actor_type": event.actor_type.value,
            "summary": event.summary,
            "amount": float(event.amount) if event.amount is not None else None,
            "metadata": dict(event.meta or {})
        }

    def count(self, merchant_id: uuid.UUID | None = None) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(AuditEvent)
        if merchant_id is not None:
            stmt = stmt.where(AuditEvent.merchant_id == merchant_id)
        return int(self._session.scalar(stmt) or 0)
