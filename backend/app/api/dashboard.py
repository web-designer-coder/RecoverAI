"""Dashboard aggregation endpoint."""

from fastapi import APIRouter

from app.dependencies import DbSession, MerchantId
from app.schemas.dashboard_schemas import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Recovery dashboard",
    description=(
        "KPIs (revenue at risk, recovered revenue, recovery rate, incremental "
        "revenue, active recoveries, payments at risk), recovery funnel, "
        "AI-vs-static rows, failure breakdown and monthly recovered series — all "
        "computed from PostgreSQL records."
    ),
)
def dashboard(session: DbSession, merchant_id: MerchantId) -> DashboardResponse:
    return DashboardService(session).build(merchant_id)
