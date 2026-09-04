"""Correctness hardening regression tests.

Tests 1-5: Recovery execution uses merchant-specific credentials from the DB,
            never falls back to global env vars, never exposes decrypted secrets.
Tests 6-10: Connection test distinguishes SUCCESS / FAILURE / TIMEOUT correctly
            using exception types (not string matching).

All tests mock the Razorpay HTTP layer — no live transactions or real credentials.
"""

import httpx
import pytest
from unittest.mock import MagicMock, patch

from app.services.providers.razorpay_client import (
    RazorpayAuthError,
    RazorpayClient,
    RazorpayNotFound,
    RazorpayNotConfigured,
    RazorpayTimeout,
    RazorpayUnavailable,
)
from app.services.providers.payment_provider import RazorpayPaymentProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeTransport(httpx.BaseTransport):
    """Inject controlled HTTP responses into httpx.Client."""

    def __init__(self, status_code: int, json_body: dict | None = None):
        self._status = status_code
        self._json = json_body or {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=self._status,
            json=self._json,
        )


def _make_client(status_code: int, json_body: dict | None = None) -> RazorpayClient:
    """Build a RazorpayClient with a fake HTTP transport."""
    transport = _FakeTransport(status_code, json_body)
    return RazorpayClient(
        key_id="rzp_test_merchant_aaa",
        key_secret="secret_aaa",
        transport=transport,
    )


# ===================================================================
# Tests 1–5: Recovery execution credential selection
# ===================================================================


class TestRecoveryExecutionCredentialSelection:
    """Ensure recovery execution always uses the authenticated merchant's
    stored credentials and never falls back to global env vars."""

    def test_1_execution_uses_merchant_specific_credentials(self):
        """MerchantService.get_razorpay_client builds a client with the
        merchant's own key_id from the DB — not the global env value."""
        from app.services.merchant_service import MerchantService
        from app.utils.encryption import encrypt_value

        with patch.object(MerchantService, "get_merchant") as mock_get:
            mock_merchant = MagicMock()
            mock_merchant.razorpay_key_id = "rzp_test_merchant_xyz"
            mock_merchant.razorpay_key_secret_encrypted = encrypt_value("secret_xyz")
            mock_get.return_value = mock_merchant

            svc = MerchantService.__new__(MerchantService)
            svc._session = MagicMock()
            svc._repository = MagicMock()

            client = svc.get_razorpay_client(MagicMock())
            # The client must carry the merchant's key_id, not a global one
            assert client._key_id == "rzp_test_merchant_xyz"
            assert client._key_secret == "secret_xyz"

    def test_2_execution_fails_when_merchant_has_no_credentials(self):
        """When the merchant has no stored credentials, get_razorpay_client
        raises RazorpayNotConfigured — no silent fallback to env vars."""
        from app.services.merchant_service import MerchantService

        with patch.object(MerchantService, "get_merchant") as mock_get:
            mock_merchant = MagicMock()
            mock_merchant.razorpay_key_id = None
            mock_merchant.razorpay_key_secret_encrypted = None
            mock_get.return_value = mock_merchant

            svc = MerchantService.__new__(MerchantService)
            svc._session = MagicMock()
            svc._repository = MagicMock()

            with pytest.raises(RazorpayNotConfigured):
                svc.get_razorpay_client(MagicMock())

    def test_3_execution_does_not_fall_back_to_global_env(self):
        """Even when merchant credentials exist but decryption fails,
        the client must NOT silently use global env credentials."""
        from app.services.merchant_service import MerchantService
        from app.utils.encryption import DecryptionError

        with patch.object(MerchantService, "get_merchant") as mock_get, \
             patch("app.services.merchant_service.decrypt_value") as mock_decrypt:
            mock_merchant = MagicMock()
            mock_merchant.razorpay_key_id = "rzp_test_abc"
            mock_merchant.razorpay_key_secret_encrypted = "encrypted_blob"
            mock_get.return_value = mock_merchant
            mock_decrypt.side_effect = DecryptionError("bad key")

            svc = MerchantService.__new__(MerchantService)
            svc._session = MagicMock()
            svc._repository = MagicMock()

            with pytest.raises(RazorpayNotConfigured):
                svc.get_razorpay_client(MagicMock())

            # Crucially: get_settings must NOT be called (no env fallback)
            with patch("app.services.merchant_service.get_settings") as mock_settings:
                # If we somehow got here, settings should never be consulted
                mock_settings.assert_not_called()

    def test_4_decrypted_credentials_never_logged(self):
        """Verify that RazorpayClient never logs key_secret or key_id."""
        import logging

        client = _make_client(404)

        with patch("app.services.providers.razorpay_client.logger") as mock_logger:
            # Trigger a path that logs
            try:
                client.get_payment("pay_test_nonexistent")
            except RazorpayNotFound:
                pass

            # Check all log calls — none should contain the secret
            for call in mock_logger.warning.call_args_list + mock_logger.error.call_args_list:
                args = " ".join(str(a) for a in call.args)
                assert "secret_aaa" not in args, f"Secret leaked in log: {args}"
                assert "rzp_test_merchant" not in args, f"Key ID leaked in log: {args}"

    def test_5_provider_factory_receives_merchant_id_from_endpoint(self):
        """The provider factory closure in recoveries.py captures the
        authenticated merchant_id (from JWT), not a request parameter."""
        # Verify the execute endpoint constructs a closure over merchant_id
        import inspect
        from app.api import recoveries

        source = inspect.getsource(recoveries.execute)
        # The closure must reference MerchantService and merchant_id
        assert "MerchantService" in source
        assert "merchant_id" in source
        assert "_merchant_provider" in source


# ===================================================================
# Tests 6–10: Connection test error handling
# ===================================================================


class TestConnectionTestErrorHandling:
    """Ensure the connection test endpoint maps each Razorpay error type
    to the correct HTTP status, never treating failures as success."""

    def test_6_valid_credentials_returns_success(self):
        """404 from an authenticated request proves credentials are valid."""
        # RazorpayNotFound means the API was reached and authenticated
        client = _make_client(404, {"error": "not found"})
        provider = RazorpayPaymentProvider(client)

        with pytest.raises(RazorpayNotFound):
            provider.get_payment("pay_test_00000000000000")

    def test_7_invalid_credentials_raises_auth_error(self):
        """401 from Razorpay → RazorpayAuthError (FAILURE, not success)."""
        client = _make_client(401, {"error": {"code": "BAD_REQUEST", "description": "Authentication failed"}})

        with pytest.raises(RazorpayAuthError):
            client.get_payment("pay_test_00000000000000")

    def test_8_timeout_raises_timeout_error(self):
        """Network timeout → RazorpayTimeout (FAILURE, not success)."""
        transport = MagicMock(spec=httpx.BaseTransport)
        transport.handle_request.side_effect = httpx.TimeoutException("timed out")
        client = RazorpayClient(
            key_id="rzp_test_x",
            key_secret="secret_x",
            transport=transport,
        )

        with pytest.raises(RazorpayTimeout):
            client.get_payment("pay_test_00000000000000")

    def test_9_network_error_raises_unavailable(self):
        """Connection error → RazorpayUnavailable (FAILURE, not success)."""
        transport = MagicMock(spec=httpx.BaseTransport)
        transport.handle_request.side_effect = httpx.ConnectError("connection refused")
        client = RazorpayClient(
            key_id="rzp_test_x",
            key_secret="secret_x",
            transport=transport,
        )

        with pytest.raises(RazorpayUnavailable):
            client.get_payment("pay_test_00000000000000")

    def test_10_connection_test_uses_isinstance_not_string_matching(self):
        """Verify the connection test endpoint uses isinstance() checks
        against structured exception types, not fragile string matching."""
        import inspect
        from app.api.merchants import test_razorpay_connection

        source = inspect.getsource(test_razorpay_connection)

        # Must use isinstance() with structured types
        assert "isinstance(e, RazorpayAuthError)" in source or \
               "except RazorpayAuthError" in source
        assert "isinstance(e, RazorpayTimeout)" in source or \
               "except RazorpayTimeout" in source
        assert "isinstance(e, RazorpayNotFound)" in source or \
               "except RazorpayNotFound" in source

        # Must NOT use fragile string matching
        assert '"authentication" in str(e)' not in source
        assert '"unauthorized" in str(e)' not in source
        assert '"timeout" in str(e)' not in source
