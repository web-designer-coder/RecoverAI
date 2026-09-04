"""Recovery service — assembles the frontend-facing recovery views.

Reads flow through repositories; the only writes in Phase 2 are the honest
operator "stop" transition (HALTED + audit event). Analyze/execute are Phase 4/5
boundaries and raise `not_implemented` rather than pretending to run.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Payment
from app.models.enums import (
    ActorType,
    AuditCategory,
    AuditEventType,
    FailureCategory,
    PaymentStatus,
    RecoveryActionStatus,
)
from app.repositories import AuditRepository, PaymentRepository, RecoveryRepository
from app.schemas.payment_schemas import (
    ActionInfo,
    DecisionInfo,
    RecoveryPaymentDetailResponse,
    RecoveryPaymentResponse,
)
from app.utils.errors import not_implemented, payment_not_found
from app.utils.mapping import canonical_to_frontend_action
from app.services.action_state_machine import apply_transition


class RecoveryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.payments = PaymentRepository(session)
        self.recovery = RecoveryRepository(session)
        self.audit = AuditRepository(session)

    # -- reads ---------------------------------------------------------------

    def list_recoveries(
        self,
        merchant_id: uuid.UUID,
        status: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[RecoveryPaymentResponse]:
        rows = self.payments.list_payments(
            merchant_id,
            status=PaymentStatus(status) if status and status != "ALL" else None,
            category=FailureCategory(category) if category else None,
            search=search or None,
            load_customer=True,  # Phase 32 P1: eager-load customer to avoid N+1
        )
        if not rows:
            return []
        failures = self.payments.list_latest_failures([p.id for p in rows])
        decisions = self.recovery.latest_decisions([p.id for p in rows], merchant_id)
        return [self._to_response(p, failures.get(p.id), decisions.get(p.id)) for p in rows]

    def get_recovery_detail(
        self, merchant_id: uuid.UUID, external_payment_id: str
    ) -> RecoveryPaymentDetailResponse:
        payment = self._require(merchant_id, external_payment_id)
        failure = self.payments.list_latest_failures([payment.id]).get(payment.id)
        decision = self.recovery.latest_decisions([payment.id], merchant_id).get(payment.id)
        actions = self.recovery.actions_for_payments([payment.id], merchant_id).get(payment.id, [])

        base = self._to_response(payment, failure, decision)

        # Resolve customer profile for the payment (already loaded via eager load or session map)
        customer = payment.customer
        customer_info = None
        if customer:
            customer_info = {
                "external_customer_id": customer.external_customer_id,
                "name": customer.name,
                "email": customer.email,
                "phone": customer.phone,
            }

        return RecoveryPaymentDetailResponse(
            **base.model_dump(),
            decision=(
                DecisionInfo(
                    diagnosis=decision.diagnosis,
                    confidence=float(decision.ai_confidence) if decision.ai_confidence is not None else None,
                    recovery_probability=float(decision.recovery_probability)
                    if decision.recovery_probability is not None
                    else None,
                    recommended_action=canonical_to_frontend_action(decision.recommended_action),
                    expected_recovery=float(decision.expected_recovery_amount)
                    if decision.expected_recovery_amount is not None
                    else None,
                    optimal_recovery_at=decision.optimal_recovery_at,
                    model_version=decision.model_version,
                    signals=decision.signals or [],
                    explanation=decision.explanation,
                    data_sufficiency=decision.data_sufficiency,
                    optimal_window=decision.optimal_window,
                )
                if decision
                else None
            ),
            actions=[
                ActionInfo(
                    id=str(a.id),
                    action_type=canonical_to_frontend_action(a.action_type),
                    status=a.status.value,
                    scheduled_at=a.scheduled_at,
                    started_at=a.started_at,
                    completed_at=a.completed_at,
                    external_reference=a.external_reference,
                )
                for a in actions
            ],
            customer=customer_info,
            provider_order_id=payment.provider_order_id,
            provider_status=payment.provider_status,
        )

    # -- writes ---------------------------------------------------------------

    def stop_recovery(self, merchant_id: uuid.UUID, external_payment_id: str) -> RecoveryPaymentResponse:
        """Operator halt — a plain state transition, no AI/policy involved."""
        payment = self._require(merchant_id, external_payment_id)
        payment.status = PaymentStatus.HALTED
        payment.next_action_at = None

        open_actions = self.recovery.actions_for_payments([payment.id], merchant_id).get(payment.id, [])
        for action in open_actions:
            if action.status in (
                RecoveryActionStatus.PENDING,
                RecoveryActionStatus.SCHEDULED,
            ):
                # Shared state machine stamps completed_at on the terminal move.
                apply_transition(action, RecoveryActionStatus.CANCELLED)

        self.audit.append(
            merchant_id=merchant_id,
            payment_id=payment.id,
            event_type=AuditEventType.RECOVERY_HALTED,
            category=AuditCategory.RESULT,
            actor_type=ActorType.OPERATOR,
            summary=f"Recovery halted by operator — {external_payment_id}",
            metadata={"Reason": "Manual stop"},
        )
        # Request-scoped sessions from get_db() do not auto-commit; without
        # this the halt (and cancelled actions) would roll back on close.
        self._session.commit()
        failure = self.payments.list_latest_failures([payment.id]).get(payment.id)
        decision = self.recovery.latest_decisions([payment.id], merchant_id).get(payment.id)
        return self._to_response(payment, failure, decision)

    def execute(self, external_payment_id: str):
        """Phase 5 boundary — policy validation + safe execution will own this."""
        raise not_implemented("Policy-checked execution", "Phase 5")

    # -- helpers ---------------------------------------------------------------

    def require_payment(self, merchant_id: uuid.UUID, external_payment_id: str) -> Payment:
        """Resolve an external id to a Payment or raise PAYMENT_NOT_FOUND."""
        payment = self.payments.get_by_external_id(merchant_id, external_payment_id)
        if payment is None:
            raise payment_not_found(external_payment_id)
        return payment

    def _require(self, merchant_id: uuid.UUID, external_payment_id: str) -> Payment:
        return self.require_payment(merchant_id, external_payment_id)

    def _to_response(
        self,
        payment: Payment,
        failure,
        decision,
    ) -> RecoveryPaymentResponse:
        probability = float(decision.recovery_probability) if decision else 0.0
        confidence = float(decision.ai_confidence) if decision else 0.0
        expected = float(decision.expected_recovery_amount) if decision else 0.0
        return RecoveryPaymentResponse(
            payment_id=payment.external_payment_id,
            customer_id=self._customer_external_id(payment),
            amount=float(payment.amount),
            currency=payment.currency,
            payment_method=payment.method.value,
            status=payment.status.value,
            priority=payment.priority.value,
            retry_count=payment.attempt_number,
            failure_reason=failure.failure_reason if failure else "No failure recorded",
            failure_category=failure.failure_category.value if failure else "UNKNOWN",
            recovery_probability=probability,
            confidence=confidence,
            recommended_action=canonical_to_frontend_action(decision.recommended_action)
            if decision
            else "RETRY",
            recommended_at=decision.optimal_recovery_at if decision else None,
            expected_recovery=expected,
            created_at=payment.created_at,
            failed_at=failure.occurred_at if failure else payment.created_at,
            next_action_at=payment.next_action_at,
        )

    def _customer_external_id(self, payment: Payment) -> str:
        # relationship already loaded via session identity map in practice;
        # fall back to a placeholder UUID string if detached.
        customer = payment.customer
        return customer.external_customer_id if customer else str(payment.customer_id)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
