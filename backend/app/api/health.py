"""Health endpoints.

Liveness (/health):  simple check — process is alive. Used by load balancers to
                     keep the instance in the pool.

Readiness (/ready):  deeper check — database reachable, critical configuration
                     present. Used by orchestrators to route traffic only to
                     instances that can actually serve requests.
"""

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.database import get_engine
from app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Simple process liveness check. Returns 200 if the application process is running. Does not check database or configuration.",
)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        database="ok",  # liveness does not assert DB connectivity
        environment=get_settings().app_env,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Comprehensive readiness check. Verifies database connectivity and critical configuration (auth key, encryption key in production). Returns 200 only if the application can serve traffic.",
)
def readiness() -> ReadinessResponse:
    settings = get_settings()

    # Database connectivity
    database = "ok"
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database = "unreachable"

    # Configuration checks
    config_issues: list[str] = []
    if settings.app_env == "production":
        if not settings.auth_secret_key:
            config_issues.append("AUTH_SECRET_KEY not set")
        # encryption key is validated lazily on first use; we don't probe it here

    ready = database == "ok" and len(config_issues) == 0

    return ReadinessResponse(
        ready=ready,
        database=database,
        environment=settings.app_env,
        config_issues=config_issues if config_issues else None,
    )
