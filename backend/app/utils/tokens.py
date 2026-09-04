"""Signed token utilities for merchant session authentication.

Tokens are HMAC-SHA256 signed, with a payload of: {merchant_id, issued_at, nonce, expires_at}.
The token is base64url(payload) + "." + base64url(hmac_sha256(payload)).
"""

import base64
import hmac
import hashlib
import json
import secrets
import time
from typing import Optional
from uuid import UUID

from app.config import get_settings


# Token TTL: 7 days
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data = data + "=" * padding
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _sign(payload: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_token(merchant_id: UUID) -> str:
    """Create a signed session token for the given merchant."""
    now = int(time.time())
    payload_obj = {
        "mid": str(merchant_id),
        "iat": now,
        "n": secrets.token_hex(8),
        "exp": now + TOKEN_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    secret = get_settings().auth_secret_key
    sig = _sign(payload_bytes, secret)
    return f"{payload_b64}.{sig}"


def parse_token(token: str) -> Optional[UUID]:
    """Parse and verify a token. Returns the merchant_id on success, None on failure."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
        payload_bytes = _b64url_decode(payload_b64)
    except (ValueError, Exception):
        return None

    secret = get_settings().auth_secret_key
    expected_sig = _sign(payload_bytes, secret)

    # Constant-time compare to prevent timing attacks
    if not hmac.compare_digest(expected_sig, sig):
        return None

    try:
        obj = json.loads(payload_bytes)
        merchant_id_str = obj.get("mid")
        exp = obj.get("exp")
        if not merchant_id_str or exp is None:
            return None
        if int(exp) < int(time.time()):
            return None  # expired
        return UUID(merchant_id_str)
    except (ValueError, KeyError, TypeError):
        return None
