"""Payment / recovery read schemas.

Field names intentionally mirror the frontend `RecoveryPayment` domain
(see src/lib/types.ts) so the Phase 7 integration is a thin fetch swap:

- `payment_id` / `customer_id` carry EXTERNAL identifiers (PAY_…, CUST_…).
- `retry_count` mirrors payments.attempt_number.
- The frontend action token NOTIFY ↔ backend CUSTOMER_NOTIFICATION is converted
  by app.utils.mapping.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class FailureInfo(BaseModel):
    failure_code: str
    failure_reason: str
    failure_category: str
    attempt_number: int
    occurred_at: datetime


class CustomerInfo(BaseModel):
    external_customer_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class DecisionInfo(BaseModel):
    diagnosis: str | None = None
    confidence: float | None = None
    recovery_probability: float | None = None
    recommended_action: str | None = None
    expected_recovery: float | None = None
    optimal_recovery_at: datetime | None = None
    model_version: str | None = None
    signals: list[dict] | None = None
    explanation: str | None = None
    data_sufficiency: str | None = None
    optimal_window: str | None = None


class ActionInfo(BaseModel):
    id: str
    action_type: str
    status: str
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    external_reference: str | None = None


class RecoveryPaymentResponse(BaseModel):
    payment_id: str
    customer_id: str
    amount: float
    currency: str
    payment_method: str
    status: str
    priority: str
    retry_count: int

    failure_reason: str
    failure_category: str

    recovery_probability: float
    confidence: float
    recommended_action: str
    recommended_at: datetime | None
    expected_recovery: float

    created_at: datetime
    failed_at: datetime
    next_action_at: datetime | None


class RecoveryPaymentDetailResponse(RecoveryPaymentResponse):
    decision: DecisionInfo | None = None
    actions: list[ActionInfo] = []
    customer: CustomerInfo | None = None
    provider_order_id: str | None = None
    provider_status: str | None = None


class PaymentCreate(BaseModel):
    """Minimal ingest contract (used by tests / future webhook ingestion)."""

    external_payment_id: str
    external_customer_id: str
    amount: Decimal
    currency: str = "INR"
    payment_method: str
