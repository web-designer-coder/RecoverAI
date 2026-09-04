"""Dashboard aggregation schemas.

Metric formulas are documented in docs/api-mapping.md; every number here is
computed from database records, never copied from frontend constants.
"""

from pydantic import BaseModel


class Kpis(BaseModel):
    revenue_at_risk: float
    recovered_revenue: float
    recovery_rate: float  # percentage 0–100
    incremental_revenue: float
    active_recoveries: int
    payments_at_risk: int


class FunnelStep(BaseModel):
    label: str
    value: float
    is_currency: bool = False


class AiVsStaticRow(BaseModel):
    metric: str
    static: str
    ai: str
    delta: str


class FailureBreakdownItem(BaseModel):
    category: str
    label: str
    count: int
    amount: float


class RecoveredSeriesPoint(BaseModel):
    month: str
    recovered: float
    baseline: float


class DashboardResponse(BaseModel):
    kpis: Kpis
    funnel: list[FunnelStep]
    ai_vs_static: list[AiVsStaticRow]
    failure_breakdown: list[FailureBreakdownItem]
    recovered_series: list[RecoveredSeriesPoint]
