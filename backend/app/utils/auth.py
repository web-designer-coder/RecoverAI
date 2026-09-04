"""Authentication utilities for merchant session management."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Merchant
from app.repositories import MerchantRepository
from app.utils.tokens import parse_token


def get_merchant_id_from_header(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_db),
) -> UUID:
    """
    Extract and verify merchant identity from Authorization header.

    Format: Authorization: Bearer <signed_token>

    Returns 401 if:
    - No Authorization header
    - Invalid format (not Bearer scheme)
    - Token cannot be parsed
    - Token is expired
    - Merchant does not exist
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required: missing Authorization header"
        )

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authentication scheme")
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication header format"
        )

    # Parse and verify the signed token
    merchant_id = parse_token(token)
    if merchant_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token"
        )

    # Verify the merchant still exists and is active
    merchant_repo = MerchantRepository(session)
    merchant = merchant_repo.get(merchant_id)
    if merchant is None:
        raise HTTPException(
            status_code=401,
            detail="Merchant account not found"
        )

    return merchant_id


# Dependency for merchant-scoped operations
from typing import Annotated
from fastapi import Depends

MerchantId = Annotated[UUID, Depends(get_merchant_id_from_header)]
