"""Recovery queue + detail + action boundary endpoints."""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.dependencies import DbSession, MerchantId
from app.limiter import limiter
from app.policy.service import PolicyService as PolicyEngineService
from app.schemas.audit_schemas import AuditEventResponse
from app.schemas.decision_schemas import AnalyzeResponse
from app.schemas.execution_schemas import (
    ExecutionResponse,
    PolicyCheckResponse,
    PolicyValidationResponse,
)
from app.schemas.payment_schemas import (
    RecoveryPaymentDetailResponse,
    RecoveryPaymentResponse,
)
from app.models.enums import FailureCategory, PaymentStatus
from app.services.audit_service import AuditService
from app.services.merchant_service import MerchantService
from app.services.providers.payment_provider import RazorpayPaymentProvider
from app.services.recovery_execution_service import RecoveryExecutionService
from app.services.recovery_intelligence_service import RecoveryIntelligenceService
from app.services.recovery_service import RecoveryService
from app.utils.errors import AppError

router = APIRouter(prefix="/recoveries", tags=["recoveries"])


def _service(session: DbSession) -> RecoveryService:
    return RecoveryService(session)


@router.get(
    "",
    response_model=list[RecoveryPaymentResponse],
    summary="List recoveries",
    description=(
        "Prioritised recovery queue with optional status/category filters and a "
        "search term matching payment id, customer id or failure reason."
    ),
)
def list_recoveries(
    session: DbSession,
    merchant_id: MerchantId,
    status: str | None = Query(default=None, description="Payment status filter (ALL for everything)"),
    category: str | None = Query(default=None, description="Failure category filter"),
    search: str | None = Query(default=None, min_length=1, description="Search payment/customer/failure reason"),
) -> list[RecoveryPaymentResponse]:
    try:
        status_value = PaymentStatus(status) if status and status != "ALL" else None
        category_value = FailureCategory(category) if category else None
    except ValueError as exc:
        raise AppError(code="INVALID_FILTER", message=str(exc), status_code=422) from exc
    return _service(session).list_recoveries(
        merchant_id,
        status=status,
        category=category,
        search=search,
    )


@router.get(
    "/{payment_id}",
    response_model=RecoveryPaymentDetailResponse,
    summary="Recovery detail",
    description=(
        "Full recovery view for one external payment id (PAY_…): overview, "
        "latest AI decision, recovery actions and audit trail."
    ),
    responses={404: {"description": "Payment not found"}},
)
def get_recovery(
    session: DbSession,
    merchant_id: MerchantId,
    payment_id: str,
) -> RecoveryPaymentDetailResponse:
    return _service(session).get_recovery_detail(merchant_id, payment_id)


@router.get(
    "/{payment_id}/audit",
    response_model=list[AuditEventResponse],
    summary="Audit trail for one payment",
    responses={404: {"description": "Payment not found"}},
)
def recovery_audit(
    session: DbSession,
    merchant_id: MerchantId,
    payment_id: str,
) -> list[AuditEventResponse]:
    service = _service(session)
    payment = service.require_payment(merchant_id, payment_id)
    events = AuditService(session).list_by_payment(merchant_id, payment.id)
    for e in events:
        e.payment_id = payment.external_payment_id
    return events


@router.post(
    "/{payment_id}/analyze",
    response_model=AnalyzeResponse,
    summary="AI recovery analysis",
    description=(
        "Runs the deterministic recoverai-v1 intelligence engine over the "
        "payment's failure and its leakage-safe history, persists a NEW "
        "versioned RecoveryDecision and returns the explainable result. "
        "The AI only recommends — nothing is executed."
    ),
    responses={
        404: {"description": "Payment not found"},
        409: {"description": "ALREADY_RECOVERED / NO_FAILURE_DATA / UNSUPPORTED_STATE"},
    },
)
def analyze(session: DbSession, merchant_id: MerchantId, payment_id: str) -> AnalyzeResponse:
    # Rate limit: 10 analyses per minute per merchant (Phase 31).
    settings = get_settings()
    rate_key = f"recovery:{merchant_id}"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
            headers={"Retry-After": "60"},
        )
    return RecoveryIntelligenceService(session).analyze(merchant_id, payment_id)


@router.post(
    "/{payment_id}/validate-policy",
    response_model=PolicyValidationResponse,
    summary="Validate policy for the current AI decision",
    description=(
        "Runs the full deterministic policy check suite against the payment's "
        "current recovery decision and persists an immutable evaluation. "
        "Never triggers analysis; never executes anything."
    ),
    responses={
        404: {"description": "Payment not found"},
        409: {"description": "NO_RECOVERY_DECISION"},
    },
)
def validate_policy(
    session: DbSession, merchant_id: MerchantId, payment_id: str
) -> PolicyValidationResponse:
    decision, evaluation = PolicyEngineService(session).evaluate_for_payment(
        merchant_id, payment_id
    )
    return PolicyValidationResponse(
        payment_id=payment_id,
        decision=decision.decision,
        allowed=decision.allowed,
        reason=decision.reason,
        policy_version=decision.policy_version,
        checks=[PolicyCheckResponse(**c.to_dict()) for c in decision.checks],
        evaluated_at=decision.evaluated_at,
        policy_evaluation_id=str(evaluation.id),
    )


@router.post(
    "/{payment_id}/execute",
    response_model=ExecutionResponse,
    summary="Safe policy-checked execution",
    description=(
        "Evaluates policy fresh (never cached), then either blocks, escalates "
        "or executes only provider operations Razorpay genuinely supports. A "
        "retry creates a Payment Link — money moves only after the customer "
        "pays and the webhook confirms. Nothing is ever marked RECOVERED "
        "without provider confirmation."
    ),
    responses={
        404: {"description": "Payment not found"},
        409: {"description": "NO_RECOVERY_DECISION / EXECUTION_CONFLICT"},
    },
)
def execute(
    session: DbSession,
    merchant_id: MerchantId,
    payment_id: str,
    idempotency_key: str | None = Query(default=None, max_length=128),
) -> ExecutionResponse:
    # Rate limit: 5 executions per minute per merchant (Phase 31).
    settings = get_settings()
    rate_key = f"execute:{merchant_id}"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
            headers={"Retry-After": "60"},
        )
    # Build a provider factory that loads THIS merchant's stored Razorpay
    # credentials from the database — never falls back to global env vars.
    merchant_svc = MerchantService(session)

    def _merchant_provider():
        client = merchant_svc.get_razorpay_client(merchant_id)
        return RazorpayPaymentProvider(client)

    return RecoveryExecutionService(session, provider=_merchant_provider).execute(
        merchant_id, payment_id, idempotency_key=idempotency_key
    )


@router.post(
    "/{payment_id}/stop",
    response_model=RecoveryPaymentResponse,
    summary="Stop recovery",
    description=(
        "Operator halt: marks the payment HALTED, cancels open scheduled actions "
        "and appends an audit event. No gateway call is made in Phase 2."
    ),
    responses={404: {"description": "Payment not found"}},
)
def stop(session: DbSession, merchant_id: MerchantId, payment_id: str) -> RecoveryPaymentResponse:
    # Rate limit: 10 stops per minute per merchant (Phase 31).
    settings = get_settings()
    rate_key = f"stop:{merchant_id}"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
            headers={"Retry-After": "60"},
        )
    return _service(session).stop_recovery(merchant_id, payment_id)
