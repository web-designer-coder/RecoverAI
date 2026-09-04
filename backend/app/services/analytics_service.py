"""Analytics foundation service — DB-computed groupings, honest baselines, time-range support.

Static-retry benchmarks (rate, avg hours) are business-defined product
baselines applied explicitly where no counterfactual data exists in the
database; everything else is computed from records.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models import Payment
from app.models.enums import PaymentStatus
from app.repositories import AnalyticsRepository
from app.schemas.analytics_schemas import (
    AnalyticsResponse,
    AttemptRecovery,
    AvgTimeToRecovery,
    CategoryRecovery,
    MethodRecovery,
    PerformancePoint,
)
from app.services.dashboard_service import STATIC_RECOVERY_RATE
from app.utils.errors import CATEGORY_LABELS

# Business-defined static benchmark for mean time to recovery (hours).
STATIC_AVG_RECOVERY_HOURS = 61.0


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.analytics = AnalyticsRepository(session)

    def build(
        self,
        merchant_id: uuid.UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> AnalyticsResponse:
        """Build analytics response with optional time filtering."""
        performance = [
            PerformancePoint(
                month=month,
                ai_rate=round((recovered_count / pipeline * 100.0) if pipeline else 0.0, 1),
                static_rate=round(STATIC_RECOVERY_RATE * 100.0, 1),
            )
            for month, pipeline, recovered_count in self._monthly_pipeline(
                merchant_id, start_date, end_date
            )
        ]

        by_category = sorted(
            (
                CategoryRecovery(
                    label=CATEGORY_LABELS.get(cat.value, cat.value),
                    recovered=round(recovered_amount, 2),
                    rate=round((rec / total * 100.0) if total else 0.0, 1),
                )
                for cat, total, _amount, rec, recovered_amount in self.analytics.category_stats(
                    merchant_id, start_date, end_date
                )
            ),
            key=lambda c: c.recovered,
            reverse=True,
        )

        method_rows = self.analytics.method_stats(merchant_id, start_date, end_date)
        pipeline_amount = sum(amount for _m, _t, amount, _r, _ra in method_rows)
        label_map = {"UPI": "UPI", "CARD": "Cards", "NET_BANKING": "Net Banking"}
        by_method = sorted(
            (
                MethodRecovery(
                    label=label_map.get(method.value, method.value),
                    recovered=round(recovered_amount, 2),
                    rate=round((rec / total * 100.0) if total else 0.0, 1),
                    share=round((amount / pipeline_amount * 100.0) if pipeline_amount else 0.0, 0),
                )
                for method, total, amount, rec, recovered_amount in method_rows
            ),
            key=lambda m: m.recovered,
            reverse=True,
        )

        by_attempt = [
            AttemptRecovery(
                attempt=f"Attempt {attempt}" + ("+" if attempt >= 4 else ""),
                rate=round((recovered / cohort * 100.0) if cohort else 0.0, 1),
                recovered=round(recovered_amount, 2),
            )
            for attempt, recovered, cohort, recovered_amount in self._attempt_cohorts(
                merchant_id, start_date, end_date
            )
        ]

        avg_hours = self.analytics.avg_recovery_hours(merchant_id, start_date, end_date)

        return AnalyticsResponse(
            performance=performance,
            by_category=by_category,
            by_method=by_method,
            by_attempt=by_attempt,
            avg_time_to_recovery_hours=AvgTimeToRecovery(
                static_hours=STATIC_AVG_RECOVERY_HOURS,
                ai_hours=round(avg_hours, 1) if avg_hours is not None else 0.0,
            ),
        )

    def _monthly_pipeline(
        self,
        merchant_id: uuid.UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> list[tuple[str, float, float]]:
        """(month, pipeline_count, recovered_count) per creation month."""
        rows = self.analytics.pipeline_by_month(merchant_id, start_date, end_date)
        recovered = {m: count for m, count, _amt in self.analytics.recovered_by_month(merchant_id, start_date, end_date)}
        return [(month, float(count), float(recovered.get(month, 0))) for month, count, _amount in rows]

    def _attempt_cohorts(
        self,
        merchant_id: uuid.UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> list[tuple[int, int, int, float]]:
        """Per attempt number: recovered count, cohort size, recovered amount."""
        recovered = case((Payment.status == PaymentStatus.RECOVERED, 1), else_=0)
        recovered_amount = case(
            (Payment.status == PaymentStatus.RECOVERED, Payment.amount), else_=0.0
        )
        stmt = (
            select(
                Payment.attempt_number,
                func.sum(recovered),
                func.count(),
                func.sum(recovered_amount),
            )
            .where(Payment.merchant_id == merchant_id)
        )
        if start_date is not None:
            stmt = stmt.where(Payment.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(Payment.created_at <= end_date)
        stmt = stmt.group_by(Payment.attempt_number).order_by(Payment.attempt_number)
        return [
            (int(a), int(r), int(c), float(ra or 0))
            for a, r, c, ra in self._session.execute(stmt).all()
        ]
