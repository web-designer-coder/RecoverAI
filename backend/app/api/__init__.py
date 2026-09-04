"""API router registry."""

from fastapi import APIRouter

from app.api import (
    analytics,
    audit,
    dashboard,
    health,
    merchants,
    policies,
    recoveries,
    simulations,
    webhooks,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(dashboard.router)
api_router.include_router(recoveries.router)
api_router.include_router(analytics.router)
api_router.include_router(audit.router)
api_router.include_router(policies.router)
api_router.include_router(simulations.router)
api_router.include_router(webhooks.router)
api_router.include_router(merchants.router)