"""Analytics aggregations — SQL-side grouping, Python-side shaping."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models import Payment, PaymentFailure, RecoveryAction, RecoveryDecision, PolicyEvaluation
from app.models.enums import FailureCategory, PaymentMethod, PaymentStatus, RecoveryActionStatus, PolicyOutcome


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _apply_time_filter(
        self, stmt, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ):
        """Apply time range filtering to a statement based on payment.created_at.

        Note: merchant_id is NOT added here — all callers already include it
        in their WHERE clause (Phase 32 cleanup).
        """
        conditions = []

        if start_date is not None:
            conditions.append(Payment.created_at >= start_date)
        if end_date is not None:
            conditions.append(Payment.created_at <= end_date)

        if conditions:
            return stmt.where(and_(*conditions))
        return stmt

    def recovered_by_month(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[tuple[str, int, float]]:
        """(month, recovered_count, recovered_amount) from real payment rows."""
        month = func.to_char(func.date_trunc("month", Payment.created_at), "YYYY-MM")
        stmt = (
            select(month, func.count(), func.sum(Payment.amount))
            .where(Payment.merchant_id == merchant_id, Payment.status == PaymentStatus.RECOVERED)
            .group_by(month)
            .order_by(month)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return [
            (m, int(c), float(s or 0)) for m, c, s in self._session.execute(stmt).all()
        ]

    def pipeline_by_month(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[tuple[str, int, float]]:
        """(month, count, amount) for every payment entering the pipeline."""
        month = func.to_char(func.date_trunc("month", Payment.created_at), "YYYY-MM")
        stmt = (
            select(month, func.count(), func.sum(Payment.amount))
            .where(Payment.merchant_id == merchant_id)
            .group_by(month)
            .order_by(month)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return [(m, int(c), float(s or 0)) for m, c, s in self._session.execute(stmt).all()]

    def category_stats(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[tuple[FailureCategory, int, float, int, float]]:
        """Per failure category: total payments, at-risk amount, recovered count,
        recovered amount."""
        recovered = case((Payment.status == PaymentStatus.RECOVERED, 1), else_=0)
        recovered_amount = case(
            (Payment.status == PaymentStatus.RECOVERED, Payment.amount), else_=0.0
        )
        stmt = (
            select(
                PaymentFailure.failure_category,
                func.count(Payment.id),
                func.sum(Payment.amount),
                func.sum(recovered),
                func.sum(recovered_amount),
            )
            .join(PaymentFailure, PaymentFailure.payment_id == Payment.id)
            .where(Payment.merchant_id == merchant_id)
            .group_by(PaymentFailure.failure_category)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return [
            (cat, int(total), float(amount or 0), int(rec), float(rec_amount or 0))
            for cat, total, amount, rec, rec_amount in self._session.execute(stmt).all()
        ]

    def method_stats(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[tuple[PaymentMethod, int, float, int, float]]:
        recovered = case((Payment.status == PaymentStatus.RECOVERED, 1), else_=0)
        recovered_amount = case(
            (Payment.status == PaymentStatus.RECOVERED, Payment.amount), else_=0.0
        )
        stmt = (
            select(
                Payment.method,
                func.count(Payment.id),
                func.sum(Payment.amount),
                func.sum(recovered),
                func.sum(recovered_amount),
            )
            .where(Payment.merchant_id == merchant_id)
            .group_by(Payment.method)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return [
            (method, int(total), float(amount or 0), int(rec), float(rec_amount or 0))
            for method, total, amount, rec, rec_amount in self._session.execute(stmt).all()
        ]

    def attempt_stats(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[tuple[int, int, float]]:
        """Recovered payments grouped by the attempt number that succeeded."""
        stmt = (
            select(
                Payment.attempt_number,
                func.count(),
                func.sum(Payment.amount),
            )
            .where(
                Payment.merchant_id == merchant_id,
                Payment.status == PaymentStatus.RECOVERED,
                Payment.attempt_number > 0,
            )
            .group_by(Payment.attempt_number)
            .order_by(Payment.attempt_number)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return [(int(a), int(c), float(s or 0)) for a, c, s in self._session.execute(stmt).all()]

    def avg_recovery_hours(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> float | None:
        """Mean hours between failure and successful recovery action completion."""
        stmt = (
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        RecoveryAction.completed_at - RecoveryAction.scheduled_at,
                    )
                    / 3600.0
                )
            )
            .join(Payment, Payment.id == RecoveryAction.payment_id)
            .where(
                Payment.merchant_id == merchant_id,
                RecoveryAction.status == "SUCCEEDED",
                RecoveryAction.completed_at.is_not(None),
                RecoveryAction.scheduled_at.is_not(None),
            )
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        value = self._session.scalar(stmt)
        return float(value) if value is not None else None

    # used by dashboard funnel -------------------------------------------------

    def eligible_count(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> int:
        stmt = select(func.count(func.distinct(RecoveryDecision.payment_id))).join(
            Payment, Payment.id == RecoveryDecision.payment_id
        ).where(Payment.merchant_id == merchant_id)
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return int(self._session.scalar(stmt) or 0)

    def attempted_count(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> int:
        stmt = select(func.count(func.distinct(RecoveryAction.payment_id))).join(
            Payment, Payment.id == RecoveryAction.payment_id
        ).where(Payment.merchant_id == merchant_id)
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return int(self._session.scalar(stmt) or 0)

    def action_distribution(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[tuple[str, str, int]]:
        """Count of recovery actions by action_type and status."""
        stmt = (
            select(
                RecoveryAction.action_type,
                RecoveryAction.status,
                func.count(),
            )
            .join(Payment, Payment.id == RecoveryAction.payment_id)
            .where(Payment.merchant_id == merchant_id)
            .group_by(RecoveryAction.action_type, RecoveryAction.status)
            .order_by(RecoveryAction.action_type, RecoveryAction.status)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return [
            (action_type.value, status.value, int(count))
            for action_type, status, count in self._session.execute(stmt).all()
        ]

    # Phase 6: Simulation analytics
    def simulation_summary(
        self, merchant_id: uuid.UUID, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list[tuple]:
        """Get summary statistics for simulations run in the time period."""
        from app.models import Simulation

        stmt = (
            select(
                func.count(Simulation.id).label('count'),
                func.avg(Simulation.static_recovery_rate).label('avg_static_rate'),
                func.avg(Simulation.ai_recovery_rate).label('avg_ai_rate'),
                func.avg(Simulation.incremental_revenue).label('avg_incremental_revenue')
            )
            .where(Simulation.merchant_id == merchant_id)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        result = self._session.execute(stmt).first()
        return [
            ('simulation_count', int(result.count or 0)),
            ('avg_static_recovery_rate', float(result.avg_static_rate or 0)),
            ('avg_ai_recovery_rate', float(result.avg_ai_rate or 0)),
            ('avg_incremental_revenue', float(result.avg_incremental_revenue or 0))
        ]

    def recent_simulations(
        self, merchant_id: uuid.UUID, limit: int = 10, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> list:
        """Get recent simulations with key metrics."""
        from app.models import Simulation

        stmt = (
            select(Simulation)
            .where(Simulation.merchant_id == merchant_id)
            .order_by(Simulation.created_at.desc())
            .limit(limit)
        )
        stmt = self._apply_time_filter(stmt, merchant_id, start_date, end_date)
        return list(self._session.scalars(stmt))


class SimulationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_merchant(self, merchant_id: uuid.UUID, limit: int = 50):
        from app.models import Simulation

        stmt = (
            select(Simulation)
            .where(Simulation.merchant_id == merchant_id)
            .order_by(Simulation.created_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def add(self, simulation):
        self._session.add(simulation)
        return simulation
