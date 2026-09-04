"""Policy endpoints — validated storage; enforcement lives in app/policy."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.dependencies import DbSession, MerchantId
from app.limiter import limiter
from app.schemas.policy_schemas import PolicyResponse, PolicyUpsertRequest
from app.services.policy_service import PolicyService

router = APIRouter(tags=["policies"])


@router.get(
    "/policies",
    response_model=PolicyResponse,
    summary="Merchant recovery policies",
    description="The active rule set every execution must pass (with its version).",
)
def get_policies(session: DbSession, merchant_id: MerchantId) -> PolicyResponse:
    service = PolicyService(session)
    policies = service.get_policies(merchant_id)
    if policies is None:
        from app.utils.errors import AppError

        raise AppError(
            code="POLICIES_NOT_CONFIGURED",
            message="No policy set exists for this merchant yet. Run `python -m app.seed` or PUT /api/policies.",
            status_code=404,
        )
    return policies


@router.put(
    "/policies",
    response_model=PolicyResponse,
    summary="Replace merchant policies",
    description=(
        "Validated update for the merchant rule set. Every change bumps the "
        "policy version: new evaluations use the new version while historical "
        "evaluations and executions keep pointing at the version that applied."
    ),
)
def put_policies(
    session: DbSession,
    merchant_id: MerchantId,
    request: PolicyUpsertRequest,
) -> PolicyResponse:
    # Rate limit: 10 policy updates per minute per merchant (Phase 31).
    settings = get_settings()
    rate_key = f"policies:{merchant_id}"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
            headers={"Retry-After": "60"},
        )
    return PolicyService(session).upsert_policies(merchant_id, request)
