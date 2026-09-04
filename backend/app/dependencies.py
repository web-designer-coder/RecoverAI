"""Shared FastAPI dependencies."""

from typing import Annotated, Optional
import uuid

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils.auth import get_merchant_id_from_header
from app.utils.errors import merchant_not_found


DbSession = Annotated[Session, Depends(get_db)]

# For backward compatibility, we'll keep the old dependency name but update its implementation
# New code should use get_merchant_id_from_header directly or create a new dependency
def get_merchant_id(authorization: Optional[str] = Header(None), session: Session = Depends(get_db)) -> uuid.UUID:
    """Resolve merchant identity from authenticated Authorization header.
    Requires Authorization: Bearer <merchant-id>. No anonymous fallback."""
    from app.utils.auth import get_merchant_id_from_header
    return get_merchant_id_from_header(authorization=authorization, session=session)


# New dependency for proper merchant authentication
MerchantId = Annotated[uuid.UUID, Depends(get_merchant_id_from_header)]