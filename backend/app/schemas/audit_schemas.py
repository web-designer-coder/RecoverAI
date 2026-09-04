"""Audit trail response schemas."""

from datetime import datetime

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: str
    timestamp: datetime
    event_type: str
    category: str
    actor_type: str
    payment_id: str | None = None
    summary: str
    amount: float | None = None
    metadata: dict = {}
