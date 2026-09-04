"""Leakage-safe historical aggregates for the recovery-intelligence layer.

Every query observes only records that existed BEFORE the current failure:

- cutoff is the current failure's ``occurred_at``; past failures qualify only
  with a strict ``occurred_at < cutoff`` (ties are excluded — conservative).
- the current payment is always excluded from its own history.

Missing history yields documented neutral defaults (None / 0 observations) —
never fabricated data. The whole feature context costs ONE aggregate SQL
query plus one lookup, so analyses stay O(1) queries, not O(history).
"""

import uuid
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.intelligence.features import BUCKET_HOURS, FeatureContext, HistoryStats, time_bucket
from app.models import Payment, PaymentFailure
from app.models.enums import PaymentStatus


class IntelligenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def feature_context(self, payment: Payment, failure: PaymentFailure) -> FeatureContext:
        """Build the full FeatureContext for one payment's latest failure."""
        cutoff = failure.occurred_at
        merchant_id = payment.merchant_id

        # Latest prior failure per payment (strictly before this failure),
        # so each historical payment counts exactly once with its final outcome.
        latest = (
            select(
                PaymentFailure.payment_id.label("pid"),
                func.max(PaymentFailure.occurred_at).label("occ"),
            )
            .select_from(PaymentFailure)
            .join(Payment, Payment.id == PaymentFailure.payment_id)
            .where(
                Payment.merchant_id == merchant_id,
                PaymentFailure.payment_id != payment.id,
                PaymentFailure.occurred_at < cutoff,
            )
            .group_by(PaymentFailure.payment_id)
            .subquery()
        )

        recovered = Payment.status == PaymentStatus.RECOVERED
        bucket_hours = BUCKET_HOURS[time_bucket(failure.occurred_at.hour)]
        in_bucket = func.extract("hour", PaymentFailure.occurred_at).in_(bucket_hours)
        same_customer = Payment.customer_id == payment.customer_id

        row = self._session.execute(
            select(
                # Merchant-wide history stats.
                func.count().label("total"),
                func.count().filter(recovered).label("recovered"),
                func.count().filter(and_(recovered, Payment.attempt_number >= 2)).label("retry_successes"),
                func.avg(Payment.amount).label("avg_amount"),
                # This customer's slice of that history.
                func.count().filter(same_customer).label("cust_total"),
                func.count().filter(and_(same_customer, recovered)).label("cust_recovered"),
                # Dimension-specific rates for this payment's category/method/attempt.
                func.count().filter(PaymentFailure.failure_category == failure.failure_category).label("cat_obs"),
                func.count().filter(and_(PaymentFailure.failure_category == failure.failure_category, recovered)).label("cat_rec"),
                func.count().filter(Payment.method == payment.method).label("method_obs"),
                func.count().filter(and_(Payment.method == payment.method, recovered)).label("method_rec"),
                func.count().filter(Payment.attempt_number == payment.attempt_number).label("att_obs"),
                func.count().filter(and_(Payment.attempt_number == payment.attempt_number, recovered)).label("att_rec"),
                # Time-of-day bucket performance.
                func.count().filter(in_bucket).label("bucket_obs"),
                func.count().filter(and_(in_bucket, recovered)).label("bucket_rec"),
                # Most recent earlier attempt on THIS payment, if any.
                select(func.max(PaymentFailure.occurred_at))
                .where(PaymentFailure.payment_id == payment.id, PaymentFailure.occurred_at < cutoff)
                .correlate(None)
                .scalar_subquery()
                .label("last_attempt_at"),
            )
            .select_from(Payment)
            .join(PaymentFailure, PaymentFailure.payment_id == Payment.id)
            .join(
                latest,
                and_(
                    PaymentFailure.payment_id == latest.c.pid,
                    PaymentFailure.occurred_at == latest.c.occ,
                ),
            )
        ).one()

        return FeatureContext(
            external_payment_id=payment.external_payment_id,
            amount=payment.amount,
            currency=payment.currency,
            method=payment.method,
            category=failure.failure_category,
            failure_code=failure.failure_code,
            failure_reason=failure.failure_reason,
            retry_count=payment.attempt_number,
            created_at=payment.created_at,
            occurred_at=failure.occurred_at,
            last_attempt_at=row.last_attempt_at,
            history=HistoryStats(
                total_failures=int(row.total),
                recovered=int(row.recovered),
                customer_failures=int(row.cust_total),
                customer_recovered=int(row.cust_recovered),
                previous_retry_successes=int(row.retry_successes or 0),
                avg_amount=row.avg_amount,
            ),
            category_recovery_rate=_rate(row.cat_rec, row.cat_obs),
            category_observations=int(row.cat_obs),
            method_recovery_rate=_rate(row.method_rec, row.method_obs),
            method_observations=int(row.method_obs),
            attempt_recovery_rate=_rate(row.att_rec, row.att_obs),
            attempt_observations=int(row.att_obs),
            bucket_recovery_rate=_rate(row.bucket_rec, row.bucket_obs),
            bucket_observations=int(row.bucket_obs),
            amount_ratio=_amount_ratio(payment.amount, row.avg_amount),
        )


def _rate(recovered: int | None, observations: int | None) -> float | None:
    obs = int(observations or 0)
    if obs <= 0:
        return None  # unseen dimension → neutral default, never invented
    return float(recovered or 0) / obs


def _amount_ratio(amount, avg_amount) -> float | None:
    if avg_amount is None or not avg_amount:
        return None
    ratio = amount / avg_amount
    return round(float(ratio), 4)
