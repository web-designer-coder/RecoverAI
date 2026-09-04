"""Policy-validation and execution API schemas (Phase 5)."""

from datetime import datetime

from pydantic import BaseModel, Field


class PolicyCheckResponse(BaseModel):
    check_name: str
    status: str
    message: str
    severity: str
    metadata: dict = {}


class PolicyValidationResponse(BaseModel):
    payment_id: str = Field(description="External payment id (PAY_…)")
    decision: str = Field(description="APPROVED | BLOCKED | ESCALATED")
    allowed: bool
    reason: str
    policy_version: str
    checks: list[PolicyCheckResponse]
    evaluated_at: datetime
    policy_evaluation_id: str


class ExecutionResponse(BaseModel):
    """Structured result for every execution outcome — approved, scheduled,
    blocked or escalated. Nothing here claims success the provider has not
    confirmed."""

    payment_id: str
    decision: str = Field(description="APPROVED | BLOCKED | ESCALATED")
    status: str = Field(
        description="Action status after execution: SCHEDULED | PROCESSING | "
                    "CUSTOMER_ACTION_REQUIRED | FAILED | BLOCKED | ESCALATED"
    )
    action: str | None = None
    action_id: str | None = None
    reason: str | None = None
    message: str | None = None
    policy_version: str | None = None
    checks: list[PolicyCheckResponse] = []
    external_reference: str | None = Field(
        default=None, description="Opaque provider reference (e.g. payment link id)"
    )
