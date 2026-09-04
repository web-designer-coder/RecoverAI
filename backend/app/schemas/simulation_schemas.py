"""Simulation schemas — records exist now, the engine arrives in Phase 6."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SimulationCreateRequest(BaseModel):
    transactions: int = Field(gt=0)
    average_amount: Decimal = Field(gt=0)
    failure_rate: Decimal = Field(gt=0, le=1)
    recovery_window_days: int = Field(ge=1, le=90)


class SimulationResponse(BaseModel):
    id: str
    transactions: int
    average_amount: float
    failure_rate: float
    recovery_window_days: int
    static_recovery_rate: float
    ai_recovery_rate: float
    static_recovered_revenue: float
    ai_recovered_revenue: float
    incremental_revenue: float
    created_at: datetime
