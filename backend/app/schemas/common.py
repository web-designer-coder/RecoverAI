"""Shared response schemas."""

from typing import Optional
from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Generic success envelope carrying a human-readable message."""

    message: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Consistent error envelope used for every non-2xx response."""

    error: ErrorBody


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str
    database: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    ready: bool
    database: str
    environment: str
    config_issues: Optional[list[str]] = None
