"""Dashboard aggregation service.

All metrics are computed from database records. The two static-retry benchmark
constants below are business-defined product baselines (documented in
docs/api-mapping.md) — the counterfactual "what would static retries recover"
is not observable in this dataset, so the benchmark is applied explicitly.

Phase 32: Aggregation moved from Python (load-all + filter) to SQL (targeted
queries per metric group). Reduces memory usage and query overhead on large
payment sets.
"""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Payment
from app.models.enums import PaymentStatus
from app.repositories import AnalyticsRepository
from app.schemas.dashboard_schemas import (
    AiVsStaticRow,
    DashboardResponse,
    FailureBreakdownItem,
    FunnelStep,
    Kpis,
    RecoveredSeriesPoint,
)
from app.utils.errors import CATEGORY_LABELS

# Business-defined static-retry benchmarks (not frontend KPI copies).
STATIC_RECOVERY_RATE = 0.53
STATIC_RETRIES_PER_RECOVERY = 2.4

# Status groups reused across multiple SQL aggregations.
_AT_RISK_STATUSES = (
    PaymentStatus.FAILED,
    PaymentStatus.QUEUED,
    PaymentStatus.SCHEDULED,
    PaymentStatus.PROCESSING,
    PaymentStatus.NEEDS_ACTION,
)


class DashboardService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.analytics = AnalyticsRepository(session)

    def build(self, merchant_id: uuid.UUID) -> DashboardResponse:
        # Phase 32: Single SQL aggregation for all KPI counts/sums
        # instead of loading every payment into Python.
        pipeline_total, recovered_count, recovered_revenue, at_risk_count, active_count = (
            self._aggregate_status_metrics(merchant_id)
        )
        revenue_at_risk = self._aggregate_at_risk_revenue(merchant_id)
        avg_retries = self._avg_recovered_retries(merchant_id)

        eligible_count = self.analytics.eligible_count(merchant_id)
        attempted_count = self.analytics.attempted_count(merchant_id)

        recovery_rate = (recovered_count / pipeline_total * 100.0) if pipeline_total else 0.0
        incremental = recovered_revenue - recovered_revenue * STATIC_RECOVERY_RATE

        kpis = Kpis(
            revenue_at_risk=round(revenue_at_risk, 2),
            recovered_revenue=round(recovered_revenue, 2),
            recovery_rate=round(recovery_rate, 1),
            incremental_revenue=round(incremental, 2),
            active_recoveries=active_count,
            payments_at_risk=at_risk_count,
        )

        funnel = [
            FunnelStep(label="At-Risk Payments", value=float(at_risk_count)),
            FunnelStep(label="AI Eligible", value=float(eligible_count)),
            FunnelStep(label="Recovery Attempted", value=float(attempted_count)),
            FunnelStep(label="Recovered", value=float(recovered_count)),
            FunnelStep(
                label="Recovered Revenue",
                value=round(recovered_revenue, 2),
                is_currency=True,
            ),
        ]

        ai_vs_static = self._ai_vs_static_rows(
            pipeline_total, recovered_count, recovered_revenue, avg_retries,
        )

        failure_breakdown = [
            FailureBreakdownItem(
                category=cat.value,
                label=CATEGORY_LABELS.get(cat.value, cat.value),
                count=total,
                amount=round(amount, 2),
            )
            for cat, total, amount, _rec, _rec_amount in self.analytics.category_stats(merchant_id)
        ]
        failure_breakdown.sort(key=lambda f: f.amount, reverse=True)

        recovered_series = [
            RecoveredSeriesPoint(
                month=month,
                recovered=round(amount, 2),
                baseline=round(amount * STATIC_RECOVERY_RATE, 2),
            )
            for month, _count, amount in self.analytics.recovered_by_month(merchant_id)
        ]

        return DashboardResponse(
            kpis=kpis,
            funnel=funnel,
            ai_vs_static=ai_vs_static,
            failure_breakdown=failure_breakdown,
            recovered_series=recovered_series,
        )

    # -- SQL aggregations (Phase 32) -----------------------------------------

    def _aggregate_status_metrics(
        self, merchant_id: uuid.UUID,
    ) -> tuple[int, int, float, int, int]:
        """Single query: total, recovered_count, recovered_sum, at_risk_count, active_count."""
        recovered = case((Payment.status == PaymentStatus.RECOVERED, 1), else_=0)
        at_risk = case((Payment.status.in_(_AT_RISK_STATUSES), 1), else_=0)
        active = case(
            (Payment.status.in_((PaymentStatus.SCHEDULED, PaymentStatus.PROCESSING)), 1),
            else_=0,
        )
        stmt = select(
            func.count().label("total"),
            func.sum(recovered).label("recovered_count"),
            func.sum(
                case((Payment.status == PaymentStatus.RECOVERED, Payment.amount), else_=0.0)
            ).label("recovered_sum"),
            func.sum(at_risk).label("at_risk_count"),
            func.sum(active).label("active_count"),
        ).where(Payment.merchant_id == merchant_id)
        row = self._session.execute(stmt).one()
        return (
            int(row.total or 0),
            int(row.recovered_count or 0),
            float(row.recovered_sum or 0),
            int(row.at_risk_count or 0),
            int(row.active_count or 0),
        )

    def _aggregate_at_risk_revenue(self, merchant_id: uuid.UUID) -> float:
        stmt = select(func.sum(Payment.amount)).where(
            Payment.merchant_id == merchant_id,
            Payment.status.in_(_AT_RISK_STATUSES),
        )
        return float(self._session.scalar(stmt) or 0)

    def _avg_recovered_retries(self, merchant_id: uuid.UUID) -> float:
        stmt = select(func.avg(Payment.attempt_number)).where(
            Payment.merchant_id == merchant_id,
            Payment.status == PaymentStatus.RECOVERED,
        )
        return float(self._session.scalar(stmt) or 0)

    def _ai_vs_static_rows(
        self,
        total: int,
        recovered_count: int,
        recovered_revenue: float,
        avg_retries: float,
    ) -> list[AiVsStaticRow]:
        actual_rate = (recovered_count / total * 100.0) if total else 0.0
        delta_pts = actual_rate - STATIC_RECOVERY_RATE * 100
        return [
            AiVsStaticRow(
                metric="Recovery Rate",
                static=f"{STATIC_RECOVERY_RATE * 100:.1f}%",
                ai=f"{actual_rate:.1f}%",
                delta=f"{delta_pts:+.1f} pts",
            ),
            AiVsStaticRow(
                metric="Recovered Revenue",
                static=f"₹{recovered_revenue * STATIC_RECOVERY_RATE / 100000:.1f}L",
                ai=f"₹{recovered_revenue / 100000:.1f}L",
                delta=f"+₹{(recovered_revenue - recovered_revenue * STATIC_RECOVERY_RATE) / 100000:.1f}L",
            ),
            AiVsStaticRow(
                metric="Retries per Recovery",
                static=f"{STATIC_RETRIES_PER_RECOVERY:.1f}",
                ai=f"{avg_retries:.1f}",
                delta=f"{avg_retries - STATIC_RETRIES_PER_RECOVERY:+.1f}",
            ),
            AiVsStaticRow(
                metric="Incremental Revenue",
                static="—",
                ai=f"+₹{(recovered_revenue - recovered_revenue * STATIC_RECOVERY_RATE) / 100000:.1f}L",
                delta=f"+₹{(recovered_revenue - recovered_revenue * STATIC_RECOVERY_RATE) / 100000:.1f}L",
            ),
        ]


# Kept as standalone function — used by test_security_hardening.py (HIGH-3).
def payment_count(session: Session, merchant_id: uuid.UUID) -> int:
    return int(session.scalar(
        select(func.count()).select_from(Payment).where(Payment.merchant_id == merchant_id)
    ) or 0)


def payment_count(session: Session, merchant_id: uuid.UUID) -> int:
    return int(session.scalar(
        select(func.count()).select_from(Payment).where(Payment.merchant_id == merchant_id)
    ) or 0)
