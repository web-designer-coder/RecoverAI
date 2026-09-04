"""Application configuration — everything comes from environment variables.

Secrets (database credentials today, Razorpay keys in Phase 3) are never
hardcoded. See `.env.example` for the documented variables.
"""

import secrets as _secrets
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"

    database_url: str = (
        "postgresql+psycopg://postgres:recoverai_dev@localhost:5432/recoverai"
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Explicit, configurable origins — never "*" for a payments API.
    cors_origins: str = "http://localhost:8080,http://localhost:3000"

    log_level: str = "INFO"

    # Auth token signing key (Phase 9.1). Must be unique per deployment.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    # Empty default — production MUST set this via AUTH_SECRET_KEY env var.
    auth_secret_key: str = ""

    # Encryption key for merchant credentials (Fernet base64 key OR raw
    # passphrase). Production MUST set MERCHANT_CREDENTIALS_ENCRYPTION_KEY.
    merchant_credentials_encryption_key: str = ""

    # Razorpay TEST MODE credentials (Phase 3). All optional so the backend
    # starts — and the unrelated test suites run — without them. Never live
    # credentials; never hardcoded; loaded from environment only.
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    # Rate limiting for authentication endpoints (Phase 26.5).
    # Default: 5 failed attempts per 60-second window, then 429.
    auth_rate_limit: str = "5/minute"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def razorpay_webhook_configured(self) -> bool:
        return bool(self.razorpay_webhook_secret)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Production guard: required secrets MUST be explicitly set.
    if s.app_env == "production":
        missing = []
        if not s.auth_secret_key:
            missing.append("AUTH_SECRET_KEY")
        if not s.merchant_credentials_encryption_key:
            missing.append("MERCHANT_CREDENTIALS_ENCRYPTION_KEY")
        if missing:
            # Never include the value; never include partial values.
            raise RuntimeError(
                "Required production secrets are not set: " + ", ".join(missing) + ". "
                "Generate AUTH_SECRET_KEY with: python -c \"import secrets; print(secrets.token_hex(32))\". "
                "Generate MERCHANT_CREDENTIALS_ENCRYPTION_KEY with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"."
            )
    # Dev/test: generate a random key if none was provided, so tokens are
    # unique per process (acceptable — dev tokens don't need to survive restarts).
    if not s.auth_secret_key:
        import logging
        logging.getLogger("recoverai.config").warning(
            "AUTH_SECRET_KEY not set — using random per-process key (tokens won't survive restart)"
        )
        s.auth_secret_key = _secrets.token_hex(32)
    return s
