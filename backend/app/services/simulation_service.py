"""Simulation service — implements what-if modeling for recovery scenarios."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("recoverai.simulation")

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.repositories import AnalyticsRepository, SimulationRepository
from app.schemas.simulation_schemas import SimulationCreateRequest, SimulationResponse
from app.services.analytics_service import AnalyticsService

class SimulationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self.simulations = SimulationRepository(session)
        self.analytics = AnalyticsRepository(session)

    def list_simulations(self, merchant_id: uuid.UUID) -> list[SimulationResponse]:
        return [self._to_response(s) for s in self.simulations.list_for_merchant(merchant_id)]

    def run_simulation(self, request: SimulationCreateRequest, merchant_id: uuid.UUID) -> SimulationResponse:
        """Run a what-if simulation based on historical data and given parameters."""
        # Get historical baseline analytics for the merchant (last 90 days by default)
        end_date = datetime.now(timezone.utc)
        start_date = end_date.replace(day=end_date.day - 90) if end_date.day > 90 else end_date.replace(month=end_date.month - 1)

        baseline_analytics = AnalyticsService(self._session).build(merchant_id, start_date, end_date)

        # For now, use the static_rate from performance points as a proxy
        static_rate_baseline = Decimal('0.0')
        if baseline_analytics.performance:
            # Average static rate across all months
            static_rates = [Decimal(str(point.static_rate)) for point in baseline_analytics.performance]
            static_rate_baseline = sum(static_rates) / len(static_rates) if static_rates else Decimal('0.0')

        # Calculate simulated metrics based on input parameters
        # This is a simplified model - in reality this would be more complex
        failure_rate = request.failure_rate
        recovery_window = request.recovery_window_days
        avg_amount = request.average_amount

        # Simulated AI recovery rate improves with better parameters but is bounded
        # Base improvement from AI: typically 20-40% over static recovery
        # Ensure all values are Decimal for precise financial calculations
        ai_improvement_factor = min(
            Decimal('0.4'),
            Decimal('0.2') +
            (Decimal(str(avg_amount)) / Decimal('10000')) * Decimal('0.1')
        )
        simulated_ai_rate = min(
            Decimal('0.95'),
            static_rate_baseline * (Decimal('1') + ai_improvement_factor)
        )

        # Adjust based on failure rate (higher failure rate might mean harder to recover)
        failure_adjustment = max(
            Decimal('0.5'),
            Decimal('1.0') - (Decimal(str(failure_rate)) * Decimal('0.5'))
        )  # Reduce effectiveness as failure rate increases
        simulated_ai_rate *= failure_adjustment

        # Adjust based on recovery window (longer window = better recovery)
        window_factor = min(
            Decimal('1.5'),
            Decimal('1.0') + (Decimal(str(recovery_window - 7)) * Decimal('0.02'))
        )  # Baseline 7 days, +2% per day up to 50% bonus
        simulated_ai_rate = min(Decimal('0.95'), simulated_ai_rate * window_factor)

        # Calculate revenue metrics
        transactions = request.transactions

        # Expected failed transactions
        failed_transactions = Decimal(transactions) * Decimal(str(failure_rate))

        # Static recovery revenue
        static_recovered = failed_transactions * (static_rate_baseline / Decimal('100')) * Decimal(str(avg_amount))

        # AI recovery revenue
        ai_recovered = failed_transactions * (simulated_ai_rate / Decimal('100')) * Decimal(str(avg_amount))

        # Incremental revenue from AI
        incremental_revenue = ai_recovered - static_recovered

        # Create simulation record
        simulation = self._create_simulation_record(
            merchant_id=merchant_id,
            transactions=transactions,
            average_amount=Decimal(str(avg_amount)),
            failure_rate=Decimal(str(failure_rate)),
            recovery_window_days=recovery_window,
            static_recovery_rate=static_rate_baseline,
            ai_recovery_rate=simulated_ai_rate,
            static_recovered_revenue=static_recovered,
            ai_recovered_revenue=ai_recovered,
            incremental_revenue=incremental_revenue
        )

        return self._to_response(simulation)

    def run_comparative_simulation(
        self,
        base_request: SimulationCreateRequest,
        parameter_variations: Dict[str, List],
        merchant_id: uuid.UUID
    ) -> List[Dict]:
        """Run multiple simulations with varying parameters for comparison."""
        results = []

        # Generate all combinations of parameters
        import itertools
        keys = list(parameter_variations.keys())
        values = list(parameter_variations.values())

        for combination in itertools.product(*values):
            # Create request with varied parameters
            var_dict = dict(zip(keys, combination))

            # Update base request with variations
            varied_request = SimulationCreateRequest(
                transactions=getattr(base_request, 'transactions', var_dict.get('transactions', 1000)),
                average_amount=getattr(base_request, 'average_amount', var_dict.get('average_amount', 1000.0)),
                failure_rate=getattr(base_request, 'failure_rate', var_dict.get('failure_rate', 0.1)),
                recovery_window_days=getattr(base_request, 'recovery_window_days', var_dict.get('recovery_window_days', 30))
            )

            # Override with specific variations
            for key, value in var_dict.items():
                if hasattr(varied_request, key):
                    setattr(varied_request, key, value)

            # Run simulation
            try:
                result = self.run_simulation(varied_request, merchant_id)
                results.append({
                    "parameters": var_dict,
                    "result": {
                        "id": str(result.id),
                        "static_recovery_rate": result.static_recovery_rate,
                        "ai_recovery_rate": result.ai_recovery_rate,
                        "incremental_revenue": result.incremental_revenue,
                        "ai_recovered_revenue": result.ai_recovered_revenue
                    }
                })
            except Exception as e:
                # Skip failed simulations but log so failures are not invisible.
                logger.warning("Comparative simulation variant failed: %s", e)
                continue

        return results

    def _create_simulation_record(
        self,
        merchant_id: uuid.UUID,
        transactions: int,
        average_amount: Decimal,
        failure_rate: Decimal,
        recovery_window_days: int,
        static_recovery_rate: Decimal,
        ai_recovery_rate: Decimal,
        static_recovered_revenue: Decimal,
        ai_recovered_revenue: Decimal,
        incremental_revenue: Decimal
    ):
        """Create and store a simulation record."""
        from app.models import Simulation

        simulation = Simulation(
            merchant_id=merchant_id,
            transactions=transactions,
            average_amount=average_amount,
            failure_rate=failure_rate,
            recovery_window_days=recovery_window_days,
            static_recovery_rate=static_recovery_rate,
            ai_recovery_rate=ai_recovery_rate,
            static_recovered_revenue=static_recovered_revenue,
            ai_recovered_revenue=ai_recovered_revenue,
            incremental_revenue=incremental_revenue,
            result_metadata={
                "generated_by": "Phase 6 Simulation Service",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model_version": "recoverai-sim-v1"
            }
        )

        self._session.add(simulation)
        self._session.commit()
        return simulation

    def _calculate_overall_recovery_rate(self, attempt_data: List) -> float:
        """Calculate overall recovery rate from attempt cohort data."""
        if not attempt_data:
            return 0.0

        total_recovered = sum(item.recovered for item in attempt_data)  # recovered count
        total_attempts = sum(int(item.attempt.split()[1].rstrip('+')) for item in attempt_data if item.attempt.startswith('Attempt'))  # cohort size approximation

        # Better approach: get the actual cohort sizes from the analytics repository
        # For now, we'll use a simplified calculation
        if total_attempts == 0:
            # Fallback: assume equal distribution
            total_attempts = len(attempt_data) * 100  # arbitrary baseline

        return (total_recovered / total_attempts * 100) if total_attempts > 0 else 0.0

    def _to_response(self, s) -> SimulationResponse:
        return SimulationResponse(
            id=str(s.id),
            transactions=s.transactions,
            average_amount=float(s.average_amount),
            failure_rate=float(s.failure_rate),
            recovery_window_days=s.recovery_window_days,
            static_recovery_rate=float(s.static_recovery_rate),
            ai_recovery_rate=float(s.ai_recovery_rate),
            static_recovered_revenue=float(s.static_recovered_revenue),
            ai_recovered_revenue=float(s.ai_recovered_revenue),
            incremental_revenue=float(s.incremental_revenue),
            created_at=s.created_at,
        )
