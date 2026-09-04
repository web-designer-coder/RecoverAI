"""39B-4 — RazorpayClient lifecycle regression tests."""
from unittest.mock import MagicMock


def test_razorpay_client_supports_context_manager_protocol():
    """Client must be usable with 'with' statement (39B-4 lifecycle)."""
    from app.services.providers.razorpay_client import RazorpayClient
    assert hasattr(RazorpayClient, "__enter__")
    assert hasattr(RazorpayClient, "__exit__")


def test_razorpay_client_close_is_idempotent():
    """close() must not raise if called multiple times."""
    from app.services.providers.razorpay_client import RazorpayClient

    class _FakeHttpxClient:
        def close(self):
            pass  # no-op

    # Pass credentials directly so get_settings is never called.
    client = RazorpayClient(
        key_id="k", key_secret="s",
        transport=MagicMock(),
    )
    client._client = _FakeHttpxClient()
    # Must not raise on first or second call.
    client.close()
    client.close()
