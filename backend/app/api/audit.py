"""Audit trail endpoint — strictly read-only."""

from fastapi import APIRouter, Query

from app.dependencies import DbSession, MerchantId
from app.schemas.audit_schemas import AuditEventResponse
from app.services.audit_service import AuditService

router = APIRouter(tags=["audit"])


@router.get(
    "/audit",
    response_model=list[AuditEventResponse],
    summary="Audit trail",
    description=(
        "Append-oriented governance log, newest first. Optional category filter "
        "(AI_DECISION | POLICY | EXECUTION | RESULT). Historical records are "
        "immutable by database trigger."
    ),
)
def audit(
    session: DbSession,
    merchant_id: MerchantId,
    category: str | None = Query(default=None, description="Category filter"),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[AuditEventResponse]:
    return AuditService(session).list_events(merchant_id, category=category, limit=limit)
