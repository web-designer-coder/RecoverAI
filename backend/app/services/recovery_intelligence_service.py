"""Recovery intelligence service — eligibility, analysis, persistence, audits.

The engine (app/intelligence) is pure; this service owns everything that
touches the database:

    eligibility checks → feature context → engine.analyze → persist
    RecoveryDecision (append-only versioning) → AI audit events

The AI ONLY produces a recommendation. Nothing here executes a recovery,
schedules a gateway retry, or notifies anyone — Phase 5 policy decides.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.intelligence.engine import RecoveryIntelligenceEngine
from app.models import Payment, PaymentFailure, RecoveryDecision
from app.models.enums import ActorType, AuditCategory, AuditEventType, PaymentStatus, RecommendedAction
from app.repositories import AuditRepository, IntelligenceRepository, PaymentRepository, RecoveryRepository
from app.schemas.decision_schemas import AnalyzeResponse, SignalInfo
from app.utils.errors import AppError, payment_not_found


class RecoveryIntelligenceService:
    def __init__(self, session: Session, engine: RecoveryIntelligenceEngine | None = None) -> None:
        self._session = session
        self.payments = PaymentRepository(session)
        self.recovery = RecoveryRepository(session)
        self.audit = AuditRepository(session)
        self.intelligence = IntelligenceRepository(session)
        self._engine = engine or RecoveryIntelligenceEngine()

    # -- analysis -------------------------------------------------------------

    def analyze(
        self,
        merchant_id: uuid.UUID,
        external_payment_id: str,
        *,
        now: datetime | None = None,
    ) -> AnalyzeResponse:
        """Run the deterministic engine and persist a NEW versioned decision.

        ``now`` is injectable so analyses are reproducible in tests; production
        callers use wall-clock time.
        """
        now = now or datetime.now(timezone.utc)

        payment = self.payments.get_by_external_id(merchant_id, external_payment_id)
        if payment is None:
            raise payment_not_found(external_payment_id)

        if payment.status is PaymentStatus.RECOVERED:
            raise AppError(
                code="ALREADY_RECOVERED",
                message=f"Payment {external_payment_id} was already recovered; "
                        "no recovery analysis applies.",
                status_code=409,
            )

        failure = self.payments.list_latest_failures([payment.id]).get(payment.id)
        if failure is None:
            raise AppError(
                code="NO_FAILURE_DATA",
                message=f"Payment {external_payment_id} has no recorded failure to analyze.",
                status_code=409,
            )

        if payment.status not in _ANALYZABLE_STATUSES:
            raise AppError(
                code="UNSUPPORTED_STATE",
                message=f"Payment {external_payment_id} is {payment.status.value}; "
                        "recovery analysis only applies to recoverable states.",
                status_code=409,
            )

        context = self.intelligence.feature_context(payment, failure)
        result = self._engine.analyze(context, now=now)

        decision = self._persist_decision(payment, result)
        self._append_audits(payment, decision, result)
        # Request-scoped sessions from get_db() do not auto-commit; the
        # webhook service owns its own commit too. One atomic unit here.
        self._session.commit()

        return AnalyzeResponse(
            decision_id=str(decision.id),
            payment_id=external_payment_id,
            version_number=decision.version_number,
            diagnosis=result.diagnosis.diagnosis,
            probability=result.probability.probability,
            confidence=result.ai_confidence,
            recommended_action=result.recommended_action,
            action_rationale=result.action_rationale,
            optimal_window=result.optimal_window,
            optimal_recovery_at=result.optimal_at,
            expected_recovery_value=float(result.expected_recovery_value),
            data_sufficiency=result.data_sufficiency,
            signals=[SignalInfo(**s) for s in result.signals],
            explanation=result.explanation,
            model_version=result.model_version,
        )

    # -- internal ranking capability -------------------------------------------

    def rank_failed_payments(self, merchant_id: uuid.UUID, limit: int = 50):
        """Rank open failed payments by expected recovery value (descending).

        Internal capability for future queue prioritization — NOT exposed as a
        route in this phase. Uses each payment's latest decision.
        """
        candidates = self.payments.list_payments(merchant_id, status=PaymentStatus.FAILED)
        decisions = self.recovery.latest_decisions([p.id for p in candidates], merchant_id)
        ranked = [
            (p, d) for p in candidates
            if (d := decisions.get(p.id)) is not None and d.expected_recovery_amount is not None
        ]
        ranked.sort(key=lambda pair: pair[1].expected_recovery_amount, reverse=True)
        return ranked[:limit]

    # -- internals ---------------------------------------------------------------

    def _persist_decision(self, payment: Payment, result) -> RecoveryDecision:
        """Append a new decision row — previous versions are never mutated."""
        decision = RecoveryDecision(
            payment_id=payment.id,
            version_number=self.recovery.next_version_number(payment.id),
            diagnosis=result.diagnosis.diagnosis[:200],
            ai_confidence=_q4(result.ai_confidence),
            recovery_probability=_q4(result.probability.probability),
            recommended_action=RecommendedAction(result.recommended_action),
            expected_recovery_amount=result.expected_recovery_value,
            optimal_recovery_at=result.optimal_at,
            model_version=result.model_version,
            signals=list(result.signals),
            explanation=result.explanation,
            optimal_window=result.optimal_window,
            data_sufficiency=result.data_sufficiency,
        )
        self.recovery.add_decision(decision)
        self._session.flush()  # assign decision.id before audit metadata
        return decision

    def _append_audits(self, payment: Payment, decision: RecoveryDecision, result) -> None:
        base = {
            "decision_id": str(decision.id),
            "model_version": result.model_version,
            "data_sufficiency": result.data_sufficiency,
        }
        common = dict(
            merchant_id=payment.merchant_id,
            payment_id=payment.id,
            actor_type=ActorType.AI_ENGINE,
        )
        self.audit.append(
            **common,
            event_type=AuditEventType.AI_DIAGNOSIS,
            category=AuditCategory.AI_DECISION,
            summary=f"AI diagnosis — {payment.external_payment_id}: "
                    f"{result.diagnosis.diagnosis}",
            metadata={**base, "diagnosis_confidence": result.diagnosis.confidence},
        )
        self.audit.append(
            **common,
            event_type=AuditEventType.RECOVERY_PREDICTION,
            category=AuditCategory.AI_DECISION,
            summary=f"Recovery prediction — {payment.external_payment_id}: "
                    f"{result.probability.probability:.0%} probability",
            metadata={
                **base,
                "probability": result.probability.probability,
                "confidence": result.ai_confidence,
            },
        )
        self.audit.append(
            **common,
            event_type=AuditEventType.ACTION_SELECTED,
            category=AuditCategory.AI_DECISION,
            summary=f"Action selected — {payment.external_payment_id}: "
                    f"{result.recommended_action} at {result.optimal_window}",
            metadata={
                **base,
                "action": result.recommended_action,
                "window": result.optimal_window,
                "probability": result.probability.probability,
            },
        )


# States for which producing a recommendation makes sense. RECOVERED and
# AUTHORIZED carry money already; HALTED means an operator stopped recovery;
# PROCESSING means a transition is in flight.
_ANALYZABLE_STATUSES = {
    PaymentStatus.FAILED,
    PaymentStatus.QUEUED,
    PaymentStatus.SCHEDULED,
    PaymentStatus.NEEDS_ACTION,
}


def _q4(value: float) -> Decimal:
    return Decimal(str(round(float(value), 4)))
