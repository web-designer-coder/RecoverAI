"""Encryption utilities for securing sensitive merchant credentials."""

import base64
import os
from typing import Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class DecryptionError(Exception):
    """Raised when credential decryption fails (wrong key, corrupted data)."""


def get_encryption_key() -> bytes:
    """
    Get or derive the encryption key from environment variable.

    Expected format: base64-encoded 32-byte key
    Falls back to deriving a key from MERCHANT_CREDENTIALS_ENCRYPTION_KEY
    if not already in correct format.
    """
    import logging
    _log = logging.getLogger("recoverai.crypto")

    key_env = os.getenv("MERCHANT_CREDENTIALS_ENCRYPTION_KEY")
    if not key_env:
        from app.config import get_settings
        settings = get_settings()
        if settings.app_env == "production":
            raise RuntimeError(
                "MERCHANT_CREDENTIALS_ENCRYPTION_KEY must be set in production. "
                "Generate with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        _log.warning(
            "Using demo encryption key — set MERCHANT_CREDENTIALS_ENCRYPTION_KEY for production"
        )
        # For demo/testing purposes, generate a consistent key from a fixed string
        key_material = b"recoverai-demo-encryption-key-change-in-production"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"recoverai-stable-salt",
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(key_material))
        return key

    # Try to use as-is if it's already a valid Fernet key
    try:
        return base64.urlsafe_b64decode(key_env)
    except Exception:
        # If not valid base64, derive key from the string
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"recoverai-stable-salt",
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(key_env.encode()))
        return key


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string using Fernet symmetric encryption.

    Args:
        plaintext: The string to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    if not plaintext:
        return ""

    f = Fernet(get_encryption_key())
    encrypted_bytes = f.encrypt(plaintext.encode('utf-8'))
    return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')


def decrypt_value(encrypted: str) -> str:
    """
    Decrypt an encrypted string using Fernet symmetric encryption.

    Args:
        encrypted: Base64-encoded encrypted string

    Returns:
        Decrypted plaintext string

    Raises:
        Exception: If decryption fails (invalid key, corrupted data, etc.)
    """
    if not encrypted:
        return ""

    try:
        f = Fernet(get_encryption_key())
        decoded_bytes = base64.urlsafe_b64decode(encrypted.encode('utf-8'))
        decrypted_bytes = f.decrypt(decoded_bytes)
        return decrypted_bytes.decode('utf-8')
    except Exception:
        # Log details server-side only; never leak crypto internals to clients.
        import logging
        logging.getLogger("recoverai.crypto").debug("Decryption failed", exc_info=True)
        raise DecryptionError("Decryption failed")