"""Simulation endpoints — Phase 6 simulation engine."""

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional

from app.config import get_settings
from app.dependencies import DbSession, MerchantId
from app.limiter import limiter
from app.schemas.simulation_schemas import (
    SimulationCreateRequest,
    SimulationResponse,
)
from app.services.simulation_service import SimulationService

router = APIRouter(tags=["simulations"])


@router.get(
    "/simulations",
    response_model=list[SimulationResponse],
    summary="List simulations",
    description="Stored simulation records, newest first.",
)
def list_simulations(
    session: DbSession,
    merchant_id: MerchantId,
) -> list[SimulationResponse]:
    return SimulationService(session).list_simulations(merchant_id)


@router.post(
    "/simulations",
    response_model=SimulationResponse,
    summary="Run what-if simulation",
    description=(
        "Run a simulation based on historical data and given parameters to model "
        "different recovery scenarios. Returns projected recovery rates and revenue."
    ),
)
def run_simulation(
    request: SimulationCreateRequest,
    session: DbSession,
    merchant_id: MerchantId,
) -> SimulationResponse:
    """Run a what-if simulation for recovery scenario modeling."""
    # Rate limit: 10 simulations per minute per merchant (Phase 31).
    settings = get_settings()
    rate_key = f"simulations:{merchant_id}"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
            headers={"Retry-After": "60"},
        )
    return SimulationService(session).run_simulation(request, merchant_id)


@router.post(
    "/simulations/compare",
    response_model=List[Dict],
    summary="Run comparative simulations",
    description=(
        "Run multiple simulations with varying parameters to compare different "
        "recovery strategy scenarios. Useful for what-if analysis and optimization."
    ),
)
def run_comparative_simulations(
    request: SimulationCreateRequest,
    session: DbSession,
    merchant_id: MerchantId,
    parameter_variations: Optional[Dict[str, List]] = None,
) -> List[Dict]:
    """Run comparative simulations with parameter variations."""
    if parameter_variations is None:
        # Default variations: test different recovery windows and failure rates
        parameter_variations = {
            "recovery_window_days": [7, 15, 30, 45],
            "failure_rate": [0.05, 0.1, 0.15, 0.2]
        }

    return SimulationService(session).run_comparative_simulation(
        request, parameter_variations, merchant_id
    )
