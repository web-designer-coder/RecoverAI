"""Payment persistence queries."""

import uuid
from datetime import datetime
from typing import List

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Customer, Merchant, Payment, PaymentFailure
from app.models.enums import FailureCategory, PaymentStatus


class PaymentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- lookups ------------------------------------------------------------

    def get(self, payment_id: uuid.UUID, merchant_id: uuid.UUID) -> Payment | None:
        """Fetch a payment by ID, scoped to a specific merchant (tenant isolation)."""
        stmt = select(Payment).where(
            Payment.id == payment_id,
            Payment.merchant_id == merchant_id,
        )
        return self._session.scalars(stmt).first()

    def get_by_external_id(self, merchant_id: uuid.UUID, external_payment_id: str) -> Payment | None:
        stmt = select(Payment).where(
            Payment.merchant_id == merchant_id,
            Payment.external_payment_id == external_payment_id,
        )
        return self._session.scalars(stmt).first()

    def external_id_exists(self, merchant_id: uuid.UUID, external_payment_id: str) -> bool:
        """Duplicate-protection probe backed by uq_payments_merchant_external."""
        stmt = (
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.merchant_id == merchant_id,
                Payment.external_payment_id == external_payment_id,
            )
        )
        count = self._session.scalar(stmt)
        return count is not None and count > 0

    # -- listing ------------------------------------------------------------

    def list_payments(
        self,
        merchant_id: uuid.UUID,
        status: PaymentStatus | None = None,
        category: FailureCategory | None = None,
        search: str | None = None,
        *,
        load_customer: bool = False,
    ) -> list[Payment]:
        # Use a subquery with IN instead of JOIN to avoid row multiplication
        # when a payment has multiple failure records (Phase 32 P0 fix).
        stmt: Select[tuple[Payment]] = (
            select(Payment)
            .where(Payment.merchant_id == merchant_id)
        )
        if load_customer:
            stmt = stmt.options(joinedload(Payment.customer))
        if status is not None:
            stmt = stmt.where(Payment.status == status)
        if category is not None:
            stmt = stmt.where(
                Payment.id.in_(
                    select(PaymentFailure.payment_id).where(
                        PaymentFailure.failure_category == category
                    )
                )
            )
        if search:
            # Escape SQL LIKE wildcards to prevent pattern injection (Phase 31 P2-5).
            sanitized = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{sanitized}%"
            stmt = stmt.where(
                Payment.id.in_(
                    select(PaymentFailure.payment_id).where(
                        func.lower(PaymentFailure.failure_reason).like(pattern, escape="\\")
                    )
                )
                | func.lower(Payment.external_payment_id).like(pattern, escape="\\")
                | Payment.id.in_(
                    select(Customer.id).where(func.lower(Customer.external_customer_id).like(pattern, escape="\\"))
                )
            )
        stmt = stmt.order_by(Payment.created_at.desc())
        return list(self._session.scalars(stmt))

    def list_latest_failures(self, payment_ids: list[uuid.UUID]) -> dict[uuid.UUID, PaymentFailure]:
        """Latest failure row per payment (by occurred_at)."""
        if not payment_ids:
            return {}
        max_occ = (
            select(
                PaymentFailure.payment_id.label("pid"),
                func.max(PaymentFailure.occurred_at).label("occ"),
            )
            .where(PaymentFailure.payment_id.in_(payment_ids))
            .group_by(PaymentFailure.payment_id)
            .subquery()
        )
        stmt = select(PaymentFailure).join(
            max_occ,
            (PaymentFailure.payment_id == max_occ.c.pid)
            & (PaymentFailure.occurred_at == max_occ.c.occ),
        )
        rows = self._session.scalars(stmt).all()
        return {f.payment_id: f for f in rows}

    # -- writes ---------------------------------------------------------------

    def add(self, payment: Payment) -> Payment:
        self._session.add(payment)
        return payment

    def get_or_create_customer(
        self,
        merchant_id: uuid.UUID,
        external_customer_id: str,
        name: str | None = None,
        email: str | None = None,
    ) -> Customer:
        stmt = select(Customer).where(
            Customer.merchant_id == merchant_id,
            Customer.external_customer_id == external_customer_id,
        )
        customer = self._session.scalars(stmt).first()
        if customer is None:
            customer = Customer(
                merchant_id=merchant_id,
                external_customer_id=external_customer_id,
                name=name,
                email=email,
            )
            self._session.add(customer)
            self._session.flush()
        return customer


class MerchantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_default_merchant(self) -> Merchant | None:
        """Phase 2 runs single-tenant against one seeded demo merchant."""
        return self._session.scalars(select(Merchant).order_by(Merchant.created_at)).first()

    def get_merchants_with_webhook_secret(self) -> List[Merchant]:
        """Return all merchants that have a Razorpay webhook secret configured (encrypted)."""
        return self._session.scalars(
            select(Merchant).where(Merchant.razorpay_webhook_secret_encrypted.isnot(None))
        ).all()

    def get(self, merchant_id: uuid.UUID) -> Merchant | None:
        """Get a merchant by ID."""
        return self._session.get(Merchant, merchant_id)

    def add(self, merchant: Merchant) -> Merchant:
        self._session.add(merchant)
        return merchant

    def count(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(Merchant)) or 0)