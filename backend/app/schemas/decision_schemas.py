"""AI recovery-decision API schemas (Phase 4).

Probability/confidence convention: floats in 0..1 (0.74 = 74%). Conversion to
percent is a presentation-layer concern only — never mixed in the API.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SignalInfo(BaseModel):
    """One explainable evidence item — no chain-of-thought."""

    name: str
    value: str
    impact: str = Field(description="positive | negative | neutral")
    category: str


class AnalyzeResponse(BaseModel):
    decision_id: str
    payment_id: str = Field(description="External payment id (PAY_…)")
    version_number: int = Field(description="Monotonic per-payment decision version; current = highest")
    diagnosis: str
    probability: float = Field(description="Recovery probability, 0..1", ge=0.0, le=1.0)
    confidence: float = Field(description="AI confidence in its own estimate, 0..1", ge=0.0, le=1.0)
    recommended_action: str
    action_rationale: str
    optimal_window: str = Field(description="NOW | +12H | +1D | +2D")
    optimal_recovery_at: datetime
    expected_recovery_value: float = Field(description="amount × probability at the optimal window, ₹")
    data_sufficiency: str = Field(description="HIGH | MEDIUM | LOW historical evidence")
    signals: list[SignalInfo]
    explanation: str
    model_version: str
    is_current: bool = True
