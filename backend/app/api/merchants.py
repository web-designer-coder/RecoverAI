"""Merchant management endpoints."""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from app.config import get_settings
from app.dependencies import DbSession, MerchantId
from app.limiter import limiter
from app.models import Merchant
from app.schemas.common import MessageResponse
from app.services.merchant_service import MerchantService
from app.services.providers.razorpay_client import (
    RazorpayAuthError,
    RazorpayNotFound,
    RazorpayNotConfigured,
    RazorpayTimeout,
    RazorpayUnavailable,
)
from app.utils.errors import AppError
from app.utils.tokens import create_token


def _client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

router = APIRouter(prefix="/merchants", tags=["merchants"])


class MerchantCreateRequest(BaseModel):
    businessName: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class MerchantSigninRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class MerchantResponse(BaseModel):
    id: str
    businessName: str
    email: str
    status: str
    environment: str
    token: Optional[str] = None


class RazorpayCredentialsRequest(BaseModel):
    keyId: str = Field(..., min_length=1, max_length=500)
    keySecret: str = Field(..., min_length=1, max_length=500)


class ConnectionTestResponse(BaseModel):
    status: str
    message: str


class WebhookSecretRequest(BaseModel):
    webhookSecret: str = Field(..., min_length=1, max_length=500)


class RazorpayIntegrationResponse(BaseModel):
    configured: bool
    keyId: Optional[str] = None
    keySecretSet: bool = False


class WebhookStatusResponse(BaseModel):
    configured: bool
    lastVerified: Optional[str] = None


def _merchant_service(session: DbSession) -> MerchantService:
    return MerchantService(session)


@router.post(
    "",
    response_model=MerchantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new merchant",
    description="Create a new merchant account. In production, this would require email verification.",
)
def create_merchant(
    request: Request,
    session: DbSession,
    merchant_input: MerchantCreateRequest = Body(...),
) -> MerchantResponse:
    service = _merchant_service(session)

    # Rate limit: check BEFORE account creation (Phase 26.5).
    settings = get_settings()
    rate_key = f"{_client_ip(request)}/signup"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please try again shortly.",
                }
            },
            headers={"Retry-After": "60"},
        )

    merchant = service.create_merchant(
        business_name=merchant_input.businessName,
        email=merchant_input.email,
        password=merchant_input.password,
    )
    # Note: NO limiter.reset() here. Signup rate limit is a hard cap per IP
    # to prevent bulk account creation spam. Signin resets on success instead.
    token = create_token(merchant.id)
    return MerchantResponse(
        id=str(merchant.id),
        businessName=merchant.name,
        email=merchant.email,
        status=merchant.status.value,
        environment=merchant.environment.value,
        token=token,
    )


@router.post(
    "/signin",
    response_model=MerchantResponse,
    summary="Sign in to existing merchant account",
    description="Sign in with email to get merchant session. Returns merchant details for session creation.",
)
def signin_merchant(
    request: Request,
    session: DbSession,
    signin_input: MerchantSigninRequest = Body(...),
) -> MerchantResponse:
    """Sign in an existing merchant by email and password."""
    service = _merchant_service(session)

    # Rate limit: check BEFORE authentication (Phase 26.5).
    # Returns 429 WITHOUT calling authenticate_merchant — prevents account enumeration.
    settings = get_settings()
    rate_key = f"{_client_ip(request)}/signin"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many sign-in attempts. Please try again shortly.",
                }
            },
            headers={"Retry-After": "60"},
        )

    merchant = service.authenticate_merchant(
        email=signin_input.email,
        password=signin_input.password
    )
    if merchant is None:
        # On FAILED attempt: counter stays incremented (already incremented by hit()).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # On SUCCESSFUL attempt: reset the counter.
    limiter.reset(rate_key)
    token = create_token(merchant.id)
    return MerchantResponse(
        id=str(merchant.id),
        businessName=merchant.name,
        email=merchant.email,
        status=merchant.status.value,
        environment=merchant.environment.value,
        token=token,
    )


@router.get(
    "/me",
    response_model=MerchantResponse,
    summary="Get authenticated merchant profile",
    description="Returns the profile of the currently authenticated merchant. "
                "Token is never included in the response.",
)
def get_merchant_profile(
    session: DbSession,
    merchant_id: MerchantId,
) -> MerchantResponse:
    service = _merchant_service(session)
    merchant = service.get_merchant(merchant_id)
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found"
        )
    return MerchantResponse(
        id=str(merchant.id),
        businessName=merchant.name,
        email=merchant.email,
        status=merchant.status.value,
        environment=merchant.environment.value,
    )


@router.post(
    "/me/razorpay",
    response_model=MessageResponse,
    summary="Configure Razorpay Test Mode credentials",
    description="Store Razorpay Test Mode credentials for the current merchant. "
                "Credentials are encrypted at rest and never returned in responses.",
)
def update_razorpay_credentials(
    session: DbSession,
    merchant_id: MerchantId,
    credentials: RazorpayCredentialsRequest = Body(...),
) -> MessageResponse:
    # Rate limit: 5 credential updates per minute per merchant (Phase 31).
    settings = get_settings()
    rate_key = f"settings:{merchant_id}"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
            headers={"Retry-After": "60"},
        )
    service = _merchant_service(session)
    service.update_razorpay_credentials(
        merchant_id=merchant_id,
        key_id=credentials.keyId,
        key_secret=credentials.keySecret
    )
    return MessageResponse(message="Razorpay credentials updated")


@router.get(
    "/me/razorpay",
    response_model=RazorpayIntegrationResponse,
    summary="Get Razorpay integration status",
    description="Returns whether Razorpay credentials are configured. "
                "keyId is returned (not a secret). keySecretSet confirms a secret exists without exposing it.",
)
def get_razorpay_integration(
    session: DbSession,
    merchant_id: MerchantId,
) -> RazorpayIntegrationResponse:
    service = _merchant_service(session)
    configured = service.is_razorpay_configured(merchant_id)
    if not configured:
        return RazorpayIntegrationResponse(configured=False)
    # Return key_id only — never decrypt or return key_secret
    merchant = service.get_merchant(merchant_id)
    assert merchant is not None
    return RazorpayIntegrationResponse(
        configured=True,
        keyId=merchant.razorpay_key_id,
        keySecretSet=bool(merchant.razorpay_key_secret_encrypted),
    )


@router.get(
    "/me/razorpay/test",
    response_model=ConnectionTestResponse,
    summary="Test Razorpay Test Mode connection",
    description="Perform a safe, read-only test of the Razorpay Test Mode connection. "
                "Does not create or modify any payments.",
)
def test_razorpay_connection(
    session: DbSession,
    merchant_id: MerchantId,
) -> ConnectionTestResponse:
    service = _merchant_service(session)
    try:
        # Get merchant-specific Razorpay client (merchant-scoped, no env fallback).
        client = service.get_razorpay_client(merchant_id)
        # Probe with a known-nonexistent payment. A 404 from an authenticated
        # request proves the credentials are valid. Auth / timeout / network
        # failures are distinct and mapped to the correct response.
        client.get_payment("pay_test_00000000000000")
        # If no exception, credentials are valid (unexpected but fine).
        return ConnectionTestResponse(
            status="success",
            message="Razorpay Test Mode connection verified",
        )
    except RazorpayNotFound:
        # 404 from an authenticated request = credentials are valid.
        return ConnectionTestResponse(
            status="success",
            message="Razorpay Test Mode connection verified",
        )
    except RazorpayAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to authenticate with Razorpay",
        )
    except RazorpayTimeout:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Razorpay API timeout",
        )
    except RazorpayUnavailable:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to connect to Razorpay",
        )
    except RazorpayNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Razorpay not configured for this merchant",
        )


@router.post(
    "/me/razorpay/webhook-secret",
    response_model=MessageResponse,
    summary="Store Razorpay webhook secret",
    description="Store the Razorpay webhook secret for the current merchant. Encrypted at rest; never returned.",
)
def update_webhook_secret(
    session: DbSession,
    merchant_id: MerchantId,
    payload: WebhookSecretRequest = Body(...),
) -> MessageResponse:
    # Rate limit: 5 webhook secret updates per minute per merchant (Phase 31).
    settings = get_settings()
    rate_key = f"webhook:{merchant_id}"
    if not limiter.hit(settings.auth_rate_limit, rate_key):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}},
            headers={"Retry-After": "60"},
        )
    service = _merchant_service(session)
    service.update_razorpay_webhook_secret(
        merchant_id=merchant_id,
        webhook_secret=payload.webhookSecret,
    )
    return MessageResponse(message="Webhook secret updated")


@router.get(
    "/me/razorpay/webhook-status",
    response_model=WebhookStatusResponse,
    summary="Get Razorpay webhook status",
    description="Get the webhook configuration status for the current merchant. "
                "Never returns the webhook secret.",
)
def get_webhook_status(
    session: DbSession,
    merchant_id: MerchantId,
) -> WebhookStatusResponse:
    service = _merchant_service(session)
    status = service.get_webhook_status(merchant_id)
    return WebhookStatusResponse(**status)


# Note: Policy endpoints will be merchant-scoped versions of the existing ones
# We'll create those in a separate file or extend the existing policies router