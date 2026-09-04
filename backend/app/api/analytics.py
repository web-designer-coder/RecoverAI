"""Analytics foundation endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter

from app.dependencies import DbSession, MerchantId
from app.schemas.analytics_schemas import AnalyticsResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["analytics"])


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Recovery analytics foundation",
    description=(
        "Database-computed recovery performance by month, failure category, "
        "payment method and retry attempt, plus mean time to recovery. "
        "Phase 6 expands these foundations."
    ),
)
def analytics(
    session: DbSession,
    merchant_id: MerchantId,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AnalyticsResponse:
    return AnalyticsService(session).build(merchant_id, start_date, end_date)
