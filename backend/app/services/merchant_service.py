"""Merchant service for handling merchant-specific operations."""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Merchant
from app.models.enums import Environment
from app.utils.password_hash import hash_password, verify_password
from app.utils.tokens import create_token
from app.repositories import MerchantRepository
from app.services.providers.razorpay_client import RazorpayClient, RazorpayNotConfigured
from app.utils.encryption import DecryptionError, decrypt_value, encrypt_value
from app.config import get_settings


class MerchantService:
    def __init__(self, session: Session):
        self._session = session
        self._repository = MerchantRepository(session)

    def create_merchant(self, business_name: str, email: str, password: Optional[str] = None) -> Merchant:
        """Create a new merchant."""
        existing = self._session.query(Merchant).filter(Merchant.email == email).first()
        if existing:
            from app.utils.errors import AppError
            raise AppError(
                code="MERCHANT_EXISTS",
                message="A merchant with this email already exists",
                status_code=409
            )

        merchant = Merchant(
            name=business_name,
            email=email,
            environment=Environment.TEST,
            password_hash=hash_password(password) if password else None,
        )
        self._session.add(merchant)
        self._session.flush()
        return merchant

    def authenticate_merchant(self, email: str, password: str) -> Optional[Merchant]:
        """Authenticate merchant by email and password. Returns merchant or None."""
        merchant = self._session.query(Merchant).filter(Merchant.email == email).first()
        if merchant is None or merchant.password_hash is None:
            return None
        if verify_password(password, merchant.password_hash):
            return merchant
        return None

    def get_merchant(self, merchant_id: uuid.UUID) -> Optional[Merchant]:
        """Get a merchant by ID."""
        return self._repository.get(merchant_id)

    def update_razorpay_credentials(
        self,
        merchant_id: uuid.UUID,
        key_id: str,
        key_secret: str
    ) -> None:
        """
        Update Razorpay Test Mode credentials for a merchant.
        Encrypts the key_secret before storage.
        """
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            from app.utils.errors import AppError
            raise AppError(
                code="MERCHANT_NOT_FOUND",
                message="Merchant not found",
                status_code=404
            )

        # Encrypt the secret before storage
        merchant.razorpay_key_id = key_id
        merchant.razorpay_key_secret_encrypted = encrypt_value(key_secret)
        # razorpay_webhook_configured remains False until webhook is verified
        self._session.flush()

    def update_razorpay_webhook_secret(
        self,
        merchant_id: uuid.UUID,
        webhook_secret: str
    ) -> None:
        """
        Update Razorpay Webhook secret for a merchant.
        Encrypts the webhook_secret before storage.
        """
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            from app.utils.errors import AppError
            raise AppError(
                code="MERCHANT_NOT_FOUND",
                message="Merchant not found",
                status_code=404
            )

        # Encrypt the webhook secret before storage
        merchant.razorpay_webhook_secret_encrypted = encrypt_value(webhook_secret)
        # When webhook secret is set, we consider webhook configured (though we might want to verify it separately)
        merchant.razorpay_webhook_configured = True
        self._session.flush()

    def get_razorpay_client(self, merchant_id: uuid.UUID) -> RazorpayClient:
        """
        Get a Razorpay client configured with merchant-specific credentials.

        Only uses the credentials stored in the merchant's database record.
        Never falls back to global environment variables — that would
        silently execute recovery actions with another party's credentials.
        """
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            from app.utils.errors import AppError
            raise AppError(
                code="MERCHANT_NOT_FOUND",
                message="Merchant not found",
                status_code=404
            )

        if not merchant.razorpay_key_id or not merchant.razorpay_key_secret_encrypted:
            raise RazorpayNotConfigured()

        try:
            key_secret = decrypt_value(merchant.razorpay_key_secret_encrypted)
        except DecryptionError:
            raise RazorpayNotConfigured()

        return RazorpayClient(key_id=merchant.razorpay_key_id, key_secret=key_secret)

    def get_razorpay_webhook_secret(self, merchant_id: uuid.UUID) -> Optional[str]:
        """
        Get the decrypted Razorpay webhook secret for a merchant.
        Returns None if not configured or decryption fails.
        Falls back to environment variable for backward compatibility.
        """
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            return None

        # Use merchant-specific webhook secret if available
        if merchant.razorpay_webhook_secret_encrypted:
            try:
                return decrypt_value(merchant.razorpay_webhook_secret_encrypted)
            except DecryptionError:
                # If decryption fails, fall back to environment variable
                pass

        # Fall back to environment variables (maintains backward compatibility)
        return get_settings().razorpay_webhook_secret

    def is_razorpay_configured(self, merchant_id: uuid.UUID) -> bool:
        """Check if merchant has Razorpay API credentials configured."""
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            return False

        # Check if merchant has encrypted credentials
        if merchant.razorpay_key_id and merchant.razorpay_key_secret_encrypted:
            try:
                # Try to decrypt to verify it's valid
                decrypt_value(merchant.razorpay_key_secret_encrypted)
                return True
            except DecryptionError:
                return False

        # Fall back to environment variables for backward compatibility
        settings = get_settings()
        return bool(settings.razorpay_key_id and settings.razorpay_key_secret)

    def is_webhook_configured(self, merchant_id: uuid.UUID) -> bool:
        """Check if merchant has Razorpay web secret configured."""
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            return False

        # Check if merchant has encrypted webhook secret
        if merchant.razorpay_webhook_secret_encrypted:
            try:
                # Try to decrypt to verify it's valid
                decrypt_value(merchant.razorpay_webhook_secret_encrypted)
                return True
            except DecryptionError:
                return False

        # Fall back to environment variables for backward compatibility
        settings = get_settings()
        return bool(settings.razorpay_webhook_secret)

    def set_webhook_configured(self, merchant_id: uuid.UUID, configured: bool = True) -> None:
        """Set the webhook configured status for a merchant."""
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            from app.utils.errors import AppError
            raise AppError(
                code="MERCHANT_NOT_FOUND",
                message="Merchant not found",
                status_code=404
            )

        merchant.razorpay_webhook_configured = configured
        self._session.flush()

    def get_webhook_status(self, merchant_id: uuid.UUID) -> dict:
        """Get webhook status for a merchant."""
        merchant = self.get_merchant(merchant_id)
        if merchant is None:
            from app.utils.errors import AppError
            raise AppError(
                code="MERCHANT_NOT_FOUND",
                message="Merchant not found",
                status_code=404
            )

        return {
            "configured": merchant.razorpay_webhook_configured,
            "lastVerified": None  # TODO: Add timestamp tracking
        }