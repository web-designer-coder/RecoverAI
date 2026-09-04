"""Phase 39A-2 — Production configuration hardening tests.

Requires production to fail fast when required secrets are missing,
and never to fall back silently. Development/test must continue.
"""
import os
from unittest.mock import patch

import pytest


def test_production_missing_auth_secret_fails_fast():
    """APP_ENV=production with no AUTH_SECRET_KEY must raise at startup."""
    env = {
        **os.environ,
        "APP_ENV": "production",
        "AUTH_SECRET_KEY": "",
        "MERCHANT_CREDENTIALS_ENCRYPTION_KEY": "test-key-32-bytes-long!!!",
    }
    with patch.dict(os.environ, env, clear=False):
        # Clear cached settings
        from app.config import get_settings, Settings
        get_settings.cache_clear()
        with pytest.raises(RuntimeError) as exc:
            get_settings()
        msg = str(exc.value)
        assert "AUTH_SECRET_KEY" in msg
        assert "production" in msg.lower() or "must be set" in msg.lower()
        # Secret value must NOT appear in the message
        assert "test-key-32-bytes-long!!!" not in msg


def test_production_missing_encryption_key_fails_fast():
    """APP_ENV=production with auth set but encryption missing must raise."""
    env = {
        **os.environ,
        "APP_ENV": "production",
        "AUTH_SECRET_KEY": "a" * 32,
        "MERCHANT_CREDENTIALS_ENCRYPTION_KEY": "",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import get_settings
        get_settings.cache_clear()
        with pytest.raises(RuntimeError) as exc:
            get_settings()
        msg = str(exc.value)
        assert "MERCHANT_CREDENTIALS_ENCRYPTION_KEY" in msg
        assert "a" * 32 not in msg


def test_production_with_both_secrets_succeeds():
    """APP_ENV=production with both secrets set must return settings."""
    env = {
        **os.environ,
        "APP_ENV": "production",
        "AUTH_SECRET_KEY": "a" * 32,
        "MERCHANT_CREDENTIALS_ENCRYPTION_KEY": "test-key-32-bytes-long!!!",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert s.app_env == "production"
        assert s.auth_secret_key == "a" * 32


def test_development_continues_without_secrets():
    """Development/test must work without explicit production secrets."""
    env = {
        **os.environ,
        "APP_ENV": "development",
        "AUTH_SECRET_KEY": "",
        "MERCHANT_CREDENTIALS_ENCRYPTION_KEY": "",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert s.app_env == "development"
        # Random per-process key generated; not empty
        assert s.auth_secret_key != ""
        # No RuntimeError raised
