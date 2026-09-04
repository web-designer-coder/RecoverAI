"""RecoverAI backend entrypoint.

Run locally:  uvicorn app.main:app --reload
OpenAPI docs: http://127.0.0.1:8000/docs
"""

import logging
import time

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import api_router
from app.config import get_settings
from app.utils.errors import AppError

# Maximum request body size: 1 MB (Phase 31 P2-4).
_MAX_BODY_BYTES = 1 * 1024 * 1024


def _error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )

logger = logging.getLogger("recoverai")


def _configure_logging() -> None:
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()

    is_prod = settings.app_env == "production"
    app = FastAPI(
        title="RecoverAI Backend",
        version="0.2.0",
        description=(
            "Backend foundation for RecoverAI payment-recovery operations. "
            "Phase 2 scope: PostgreSQL-backed domain model and read APIs with "
            "clear boundaries for AI (Phase 4), policy execution (Phase 5) and "
            "simulation (Phase 6). No Razorpay integration yet."
        ),
        docs_url=None if is_prod else "/docs",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # Explicit configurable origins — never a wildcard for a payments API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Request body size limit — prevent memory exhaustion (Phase 31 P2-4).
    class _BodySizeLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > _MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request body exceeds 1 MB limit"}},
                )
            return await call_next(request)

    app.add_middleware(_BodySizeLimitMiddleware)

    @app.middleware("http")
    async def request_correlation(request: Request, call_next):
        # 39B-2 minimal request correlation — never log secrets or payload.
        req_id = request.headers.get("X-Request-ID")
        if req_id and len(req_id) > 128:
            req_id = req_id[:128]  # cap oversized IDs safely
        if not req_id:
            req_id = str(uuid.uuid4())
        # Attach to state for potential request-scoped logging; do not expose in logs.
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        # Do NOT include request_id in log messages (no correlation with secrets/payload).
        return response

    @app.middleware("http")
    async def security_headers_and_logging(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        # Security headers — defense-in-depth for all API responses.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Content-Security-Policy: API-only backend — block all resource loading.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        # HSTS: production HTTPS only (Phase 26.5).
        if settings.app_env == "production" and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        # Rate-limit advisory for 429 responses (Phase 26.5).
        if response.status_code == 429:
            response.headers["Retry-After"] = "60"
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Surface only field-level messages; never raw internals.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        return _error_response(
            "VALIDATION_ERROR",
            f"Invalid request{' at ' + loc if loc else ''}: {first.get('msg', 'validation failed')}",
            422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return _error_response(code, detail, exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error on %s", exc.__class__.__name__, exc_info=exc)
        return _error_response(
            "INTERNAL_ERROR",
            "An unexpected error occurred. The details are logged server-side.",
            500,
        )

    app.include_router(api_router)

    return app


app = create_app()
