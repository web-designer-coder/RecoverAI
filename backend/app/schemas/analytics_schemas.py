"""Analytics foundation schemas — Phase 6 will expand on these."""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class PerformancePoint(BaseModel):
    month: str
    ai_rate: float
    static_rate: float


class CategoryRecovery(BaseModel):
    label: str
    recovered: float
    rate: float


class MethodRecovery(BaseModel):
    label: str
    recovered: float
    rate: float
    share: float


class AttemptRecovery(BaseModel):
    attempt: str
    rate: float
    recovered: float


class AvgTimeToRecovery(BaseModel):
    static_hours: float
    ai_hours: float


class SimulationScenario(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any]
    created_at: datetime


class SimulationResult(BaseModel):
    scenario_name: str
    baseline_metrics: Dict[str, float]
    simulated_metrics: Dict[str, float]
    improvement: Dict[str, float]
    confidence_interval: Optional[Dict[str, float]] = None


class AnalyticsResponse(BaseModel):
    performance: list[PerformancePoint]
    by_category: list[CategoryRecovery]
    by_method: list[MethodRecovery]
    by_attempt: list[AttemptRecovery]
    avg_time_to_recovery_hours: AvgTimeToRecovery
    simulations: Optional[List[SimulationResult]] = None
