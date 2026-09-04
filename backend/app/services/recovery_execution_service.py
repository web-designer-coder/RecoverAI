"""Safe recovery execution service.

Flow (mandatory, in this order):

    load payment → load current AI decision → evaluate policy
      BLOCKED   → stop, return structured blocked response
      ESCALATED → stop, return structured escalation response
      APPROVED  → create action → provider operation → persist result → audit

There is deliberately NO lower-level method that executes without a fresh
policy evaluation — authorization and execution cannot be decoupled by any
caller. Idempotency is enforced at the database (UNIQUE idempotency_key +
partial UNIQUE active-action-per-payment), not by in-memory locks.

Payment state follows provider confirmation only: PROCESSING while awaiting a
webhook; RECOVERED exclusively via the Phase 3 webhook ingestion path.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import RecoveryAction
from app.models.enums import (
    ActorType,
    AuditCategory,
    AuditEventType,
    PaymentStatus,
    RecommendedAction,
    RecoveryActionStatus,
)
from app.policy.service import PolicyService
from app.repositories import PaymentRepository, PolicyRepository, RecoveryRepository
from app.schemas.execution_schemas import (
    ExecutionResponse,
    PolicyCheckResponse,
)
from app.services.providers.payment_provider import ExecutionStatus
from app.services.action_state_machine import apply_transition
from app.utils.errors import AppError, payment_not_found

logger = logging.getLogger("recoverai.execution")

# Provider-facing actions the execution service can attempt after approval.
_PROVIDER_ACTIONS = {RecommendedAction.RETRY}
_CUSTOMER_ACTIONS = {
    RecommendedAction.PAYMENT_UPDATE,
    RecommendedAction.CUSTOMER_NOTIFICATION,
}


class RecoveryExecutionService:
    def __init__(self, session: Session, provider=None) -> None:
        self._session = session
        self.payments = PaymentRepository(session)
        self.recovery = RecoveryRepository(session)
        self._policy_service = PolicyService(session)
        self._provider_factory = provider

    def execute(
        self,
        merchant_id: uuid.UUID,
        external_payment_id: str,
        *,
        idempotency_key: str | None = None,
        now: datetime | None = None,
    ) -> ExecutionResponse:
        now = now or datetime.now(timezone.utc)

        payment = self.payments.get_by_external_id(merchant_id, external_payment_id)
        if payment is None:
            raise payment_not_found(external_payment_id)

        # 1. Fresh policy evaluation — never cached, never bypassed.
        decision, evaluation = self._policy_service.evaluate_for_payment(
            merchant_id, external_payment_id, now=now
        )
        checks = [PolicyCheckResponse(**c.to_dict()) for c in decision.checks]

        # Idempotent replay BEFORE any block handling: returning the recorded
        # state of an already-created action is a read, never an execution —
        # no new action, no provider call, so policy cannot be bypassed.
        if idempotency_key:
            replay = self._find_by_idempotency_key(idempotency_key)
            if replay is not None and replay.payment_id == payment.id:
                logger.info("execution replayed payment=%s action=%s",
                            external_payment_id, replay.status.value)
                return self._response_for_action(external_payment_id, replay,
                                                 decision, checks)

        if decision.decision == "BLOCKED":
            return ExecutionResponse(
                payment_id=external_payment_id,
                decision="BLOCKED",
                status="BLOCKED",
                reason=decision.reason,
                checks=checks,
                policy_version=decision.policy_version,
            )
        if decision.decision == "ESCALATED":
            return ExecutionResponse(
                payment_id=external_payment_id,
                decision="ESCALATED",
                status="ESCALATED",
                reason=decision.reason,
                checks=checks,
                policy_version=decision.policy_version,
            )

        # 2. Approved: build the idempotent execution key.
        ai_decision = self.recovery.latest_decisions([payment.id], merchant_id)[payment.id]
        key = (
            idempotency_key
            or f"{external_payment_id}:{ai_decision.id}:{ai_decision.recommended_action.value}"
        )
        existing = self._find_by_idempotency_key(key)
        if existing is not None:
            logger.info("execution replayed payment=%s action=%s", external_payment_id, existing.status.value)
            return self._response_for_action(external_payment_id, existing, decision, checks)

        # 3. Create + persist the action under database duplicate protection.
        action = RecoveryAction(
            payment_id=payment.id,
            decision_id=ai_decision.id,
            policy_evaluation_id=evaluation.id,
            action_type=ai_decision.recommended_action,
            status=RecoveryActionStatus.PENDING,
            idempotency_key=key,
        )
        self.recovery.add_action(action)
        try:
            self._session.flush()
        except IntegrityError:
            # Concurrent request created the active action first.
            self._session.rollback()
            race = self._find_by_idempotency_key(key) or self._find_active_action(payment.id)
            if race is None:
                raise AppError(
                    code="EXECUTION_CONFLICT",
                    message="Another execution for this payment is already in progress.",
                    status_code=409,
                ) from None
            logger.info("execution lost insert race payment=%s — replaying", external_payment_id)
            return self._response_for_action(external_payment_id, race, decision, checks)

        try:
            # Policy authorized this action — record the approval transition
            # so every later move goes through the validated state machine.
            apply_transition(action, RecoveryActionStatus.APPROVED)
            # Point 8 — isolate provider + audit from rollback of bookkeeping errors.
            # The action is already flushed (line 135); use a savepoint so a
            # failure in _run_approved doesn't wipe the persisted action state.
            with self._session.begin_nested():
                response = self._run_approved(payment, action, ai_decision, decision, checks, now)
        except Exception:
            # Provider errors handled inside; anything escaping is bookkeeping.
            # Roll back only the savepoint, preserving the flushed action.
            self._session.rollback()
            raise
        self._session.commit()
        return response

    # -- internals -----------------------------------------------------------

    def _run_approved(self, payment, action, ai_decision, decision, checks, now) -> ExecutionResponse:
        action_type = ai_decision.recommended_action
        base = dict(payment_id=payment.external_payment_id, decision="APPROVED",
                    action=action_type.value, action_id=str(action.id),
                    policy_version=decision.policy_version, checks=checks)

        # Customer-facing actions never call the provider.
        if action_type in _CUSTOMER_ACTIONS:
            apply_transition(action, RecoveryActionStatus.CUSTOMER_ACTION_REQUIRED)
            payment.status = PaymentStatus.NEEDS_ACTION
            payment.next_action_at = None
            self._audit(payment, action, AuditEventType.CUSTOMER_NOTIFIED
                        if action_type is RecommendedAction.CUSTOMER_NOTIFICATION
                        else AuditEventType.ACTION_SELECTED,
                        f"{action_type.value} requires customer action — "
                        f"{payment.external_payment_id}",
                        {"action_id": str(action.id)})
            return ExecutionResponse(**base, status="CUSTOMER_ACTION_REQUIRED",
                                     message="Customer must complete this step; nothing was executed.")

        if action_type not in _PROVIDER_ACTIONS:
            # ESCALATE / STOP recommendations terminate before execution.
            target = (RecoveryActionStatus.ESCALATED
                      if action_type is RecommendedAction.ESCALATE
                      else RecoveryActionStatus.BLOCKED)
            apply_transition(action, target)
            self._audit(payment, action, AuditEventType.RECOVERY_HALTED
                        if action_type is RecommendedAction.STOP else AuditEventType.POLICY_ESCALATED,
                        f"{action_type.value} recommendation applied — {payment.external_payment_id}",
                        {"action_id": str(action.id)})
            return ExecutionResponse(**base, status=target.value,
                                     message=f"{action_type.value} handled without provider execution.")

        # Scheduled path: the AI's optimal window is still in the future.
        optimal_at = ai_decision.optimal_recovery_at
        if optimal_at is not None and optimal_at > now:
            apply_transition(action, RecoveryActionStatus.SCHEDULED)
            action.scheduled_at = optimal_at
            payment.next_action_at = optimal_at
            self._audit(payment, action, AuditEventType.RECOVERY_SCHEDULED,
                        f"Recovery scheduled for {optimal_at.isoformat()} — {payment.external_payment_id}",
                        {"action_id": str(action.id), "scheduled_at": optimal_at.isoformat()})
            return ExecutionResponse(**base, status="SCHEDULED",
                                     message=f"Recovery scheduled for {optimal_at.isoformat()}.")

        # Live execution: PROCESSING first — RECOVERED only ever arrives via
        # the Phase 3 webhook once the provider confirms money movement.
        apply_transition(action, RecoveryActionStatus.PROCESSING)
        payment.status = PaymentStatus.PROCESSING
        self._audit(payment, action, AuditEventType.RECOVERY_PROCESSING,
                    f"Provider operation started — {payment.external_payment_id}",
                    {"action_id": str(action.id)})

        try:
            provider = self._provider_factory() if self._provider_factory else _default_provider()
        except Exception as exc:
            return self._fail_provider(payment, action, "PROVIDER_UNAVAILABLE",
                                       f"Provider unavailable: {exc.__class__.__name__}", base)

        try:
            result = provider.execute_recovery(
                action_type=action_type,
                amount=payment.amount,
                currency=payment.currency,
                reference_id=payment.external_payment_id,
            )
        except Exception as exc:  # structured RazorpayClientErrors land here too
            code = getattr(exc, "code", "PROVIDER_ERROR")
            return self._fail_provider(payment, action, code,
                                       getattr(exc, "message", str(exc)), base)

        if result is None or not isinstance(getattr(result, "status", None), ExecutionStatus):
            # A provider contract violation must fail safely, never crash.
            return self._fail_provider(payment, action, "PROVIDER_INVALID_RESPONSE",
                                       "Provider returned no structured result.", base)

        if result.status is ExecutionStatus.PROCESSING:
            action.external_reference = result.external_reference
            self._audit(payment, action, AuditEventType.RECOVERY_EXECUTED,
                        f"Provider accepted recovery op — {payment.external_payment_id}",
                        {"action_id": str(action.id),
                         "reference": result.external_reference})
            return ExecutionResponse(**base, status="PROCESSING",
                                     message=result.message,
                                     external_reference=result.external_reference)

        if result.status is ExecutionStatus.SUCCEEDED:
            # Only a provider-confirmed final success moves money state.
            apply_transition(action, RecoveryActionStatus.SUCCEEDED)
            payment.status = PaymentStatus.RECOVERED
            payment.next_action_at = None
            self._audit(payment, action, AuditEventType.PAYMENT_RECOVERED,
                        f"Provider confirmed recovery — {payment.external_payment_id}",
                        {"action_id": str(action.id), "reference": result.external_reference})
            return ExecutionResponse(**base, status="SUCCEEDED",
                                     message=result.message,
                                     external_reference=result.external_reference)

        if result.status is ExecutionStatus.CUSTOMER_ACTION_REQUIRED:
            apply_transition(action, RecoveryActionStatus.CUSTOMER_ACTION_REQUIRED)
            payment.status = PaymentStatus.NEEDS_ACTION
            self._audit(payment, action, AuditEventType.CUSTOMER_NOTIFIED,
                        f"Customer action required — {payment.external_payment_id}",
                        {"action_id": str(action.id)})
            return ExecutionResponse(**base, status="CUSTOMER_ACTION_REQUIRED",
                                     message=result.message)

        return self._fail_provider(payment, action, "PROVIDER_FAILED",
                                   result.message, base)

    def _fail_provider(self, payment, action, code: str, message: str, base: dict) -> ExecutionResponse:
        apply_transition(action, RecoveryActionStatus.FAILED)
        action.failure_reason = f"{code}: {message}"[:500]
        # Payment stays FAILED-family — no manufactured success.
        if payment.status is PaymentStatus.PROCESSING:
            payment.status = PaymentStatus.FAILED
        self._audit(payment, action, AuditEventType.RECOVERY_FAILED,
                    f"Provider execution failed ({code}) — {payment.external_payment_id}",
                    {"action_id": str(action.id), "provider_code": code})
        return ExecutionResponse(**base, status="FAILED", reason=message,
                                 message=f"Execution failed safely: {message}")

    def _audit(self, payment, action, event_type: AuditEventType, summary: str,
               metadata: dict) -> None:
        from app.repositories import AuditRepository

        if action.policy_evaluation_id is not None:
            metadata = {**metadata, "policy_evaluation_id": str(action.policy_evaluation_id)}
        AuditRepository(self._session).append(
            merchant_id=payment.merchant_id,
            payment_id=payment.id,
            event_type=event_type,
            category=AuditCategory.EXECUTION,
            actor_type=ActorType.SYSTEM,
            summary=summary,
            metadata=metadata,
        )

    def _find_by_idempotency_key(self, key: str) -> RecoveryAction | None:
        from sqlalchemy import select

        return self._session.scalars(
            select(RecoveryAction).where(RecoveryAction.idempotency_key == key)
        ).first()

    def _find_active_action(self, payment_id: uuid.UUID) -> RecoveryAction | None:
        from sqlalchemy import select

        return self._session.scalars(
            select(RecoveryAction).where(
                RecoveryAction.payment_id == payment_id,
                RecoveryAction.status.in_([
                    RecoveryActionStatus.PENDING,
                    RecoveryActionStatus.VERIFYING_POLICY,
                    RecoveryActionStatus.APPROVED,
                    RecoveryActionStatus.SCHEDULED,
                    RecoveryActionStatus.PROCESSING,
                ]),
            )
        ).first()

    def _response_for_action(self, external_payment_id, action, decision, checks) -> ExecutionResponse:
        return ExecutionResponse(
            payment_id=external_payment_id,
            decision="APPROVED",
            status=action.status.value,
            action=action.action_type.value,
            action_id=str(action.id),
            policy_version=decision.policy_version,
            checks=checks,
            external_reference=action.external_reference,
            message="Existing execution returned (idempotent replay); no new provider action.",
        )


def _default_provider():
    from app.services.providers.payment_provider import build_payment_provider

    return build_payment_provider()
