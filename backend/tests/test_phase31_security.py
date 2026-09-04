"""Phase 31 — Advanced Security Hardening tests.

Verifies each fix from the Phase 31 security audit:
- P1-1: .env in .gitignore
- P1-2: Content-Security-Policy header on all responses
- P1-3: Rate limiting on mutation endpoints
- P2-3: DecryptionError specific exception type
- P2-4: Request body size limit (413)
- P2-5: Search input sanitization (LIKE wildcards escaped)
"""

import os

import pytest

from app.limiter import limiter
from app.utils.tokens import create_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_header(merchant_id: str) -> dict:
    return {"Authorization": f"Bearer {create_token(merchant_id)}"}


# ---------------------------------------------------------------------------
# P1-1: .env in .gitignore
# ---------------------------------------------------------------------------

class TestEnvGitignore:
    def test_env_in_gitignore(self):
        """The .env file must be listed in .gitignore to prevent credential leaks."""
        gitignore_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", ".gitignore"
        )
        with open(gitignore_path) as f:
            content = f.read()
        # Check for .env or .env.* patterns
        assert ".env" in content, ".gitignore must include .env"

    def test_env_example_not_ignored(self):
        """`.env.example` must NOT be ignored (it's a documentation file)."""
        gitignore_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", ".gitignore"
        )
        with open(gitignore_path) as f:
            lines = [l.strip() for l in f.readlines()]
        # .env.example should be explicitly un-ignored
        assert "!.env.example" in lines, ".gitignore must include !.env.example"


# ---------------------------------------------------------------------------
# P1-2: Content-Security-Policy header
# ---------------------------------------------------------------------------

class TestContentSecurityPolicy:
    def test_csp_header_on_health(self, client):
        """Health endpoint must include Content-Security-Policy header."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'none'" in csp, f"CSP should block all resources, got: {csp}"

    def test_csp_header_on_authenticated(self, client, merchant_id):
        """Authenticated endpoints must include CSP header."""
        headers = _auth_header(merchant_id)
        resp = client.get("/api/policies", headers=headers)
        assert resp.status_code == 200
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'none'" in csp

    def test_csp_blocks_frame_ancestors(self, client):
        """CSP must include frame-ancestors 'none' to prevent clickjacking."""
        resp = client.get("/api/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in csp

    def test_all_security_headers_present(self, client):
        """All security headers must be present on responses."""
        resp = client.get("/api/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in resp.headers
        assert "Content-Security-Policy" in resp.headers


# ---------------------------------------------------------------------------
# P1-3: Rate limiting on mutation endpoints
# ---------------------------------------------------------------------------

class TestMutationRateLimiting:
    """Rate limiting must apply to all mutation endpoints, not just signin/signup."""

    def test_policy_update_rate_limited(self, client, merchant_id):
        """PUT /policies must be rate-limited per merchant."""
        headers = _auth_header(merchant_id)
        payload = {
            "maximum_retries": 3,
            "recovery_window_days": 14,
            "minimum_ai_confidence": 70,
            "high_value_threshold": 50000,
            "failure_rules": {
                "INSUFFICIENT_FUNDS": "RETRY",
                "NETWORK_FAILURE": "RETRY",
                "EXPIRED_CARD": "CUSTOMER_NOTIFICATION",
                "INVALID_DETAILS": "CUSTOMER_NOTIFICATION",
                "BANK_DECLINE": "STOP",
                "OTHER": "ESCALATE",
            },
        }

        # Exhaust the rate limit (5/minute = 5 requests)
        for i in range(5):
            resp = client.put("/api/policies", json=payload, headers=headers)
            # May succeed or fail based on validation, but should NOT be 429
            assert resp.status_code != 429, f"Request {i+1} should not be rate-limited"

        # 6th request should be rate-limited
        resp = client.put("/api/policies", json=payload, headers=headers)
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMITED"

    def test_razorpay_settings_rate_limited(self, client, merchant_id):
        """POST /merchants/me/razorpay must be rate-limited per merchant."""
        headers = _auth_header(merchant_id)
        for i in range(5):
            resp = client.post("/api/merchants/me/razorpay", json={
                "keyId": f"rzp_test_{i}",
                "keySecret": f"secret_{i}",
            }, headers=headers)
            assert resp.status_code != 429, f"Request {i+1} should not be rate-limited"

        # 6th request should be rate-limited
        resp = client.post("/api/merchants/me/razorpay", json={
            "keyId": "rzp_test_5",
            "keySecret": "secret_5",
        }, headers=headers)
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMITED"

    def test_simulation_rate_limited(self, client, merchant_id):
        """POST /simulations must be rate-limited per merchant."""
        headers = _auth_header(merchant_id)
        payload = {
            "transactions": 1000,
            "average_amount": 2000,
            "failure_rate": 0.1,
            "recovery_window_days": 14,
        }
        for i in range(5):
            resp = client.post("/api/simulations", json=payload, headers=headers)
            assert resp.status_code != 429, f"Request {i+1} should not be rate-limited"

        # 6th request should be rate-limited
        resp = client.post("/api/simulations", json=payload, headers=headers)
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMITED"

    def test_health_not_affected_by_mutation_limits(self, client, merchant_id):
        """Health endpoint must not be affected by mutation rate limiting."""
        headers = _auth_header(merchant_id)
        # Exhaust policy rate limit
        payload = {
            "maximum_retries": 3,
            "recovery_window_days": 14,
            "minimum_ai_confidence": 70,
            "high_value_threshold": 50000,
            "failure_rules": {
                "INSUFFICIENT_FUNDS": "RETRY",
                "NETWORK_FAILURE": "RETRY",
                "EXPIRED_CARD": "CUSTOMER_NOTIFICATION",
                "INVALID_DETAILS": "CUSTOMER_NOTIFICATION",
                "BANK_DECLINE": "STOP",
                "OTHER": "ESCALATE",
            },
        }
        for _ in range(5):
            client.put("/api/policies", json=payload, headers=headers)

        # Health should still work
        resp = client.get("/api/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# P2-3: DecryptionError specific exception type
# ---------------------------------------------------------------------------

class TestDecryptionErrorType:
    def test_decryption_error_is_specific_type(self):
        """decrypt_value must raise DecryptionError, not generic Exception."""
        from app.utils.encryption import DecryptionError, decrypt_value

        with pytest.raises(DecryptionError):
            decrypt_value("this_is_not_valid_encrypted_data")

    def test_decryption_error_not_generic_exception(self):
        """DecryptionError must be a subclass of Exception but not bare Exception catch."""
        from app.utils.encryption import DecryptionError
        assert issubclass(DecryptionError, Exception)
        # Verify it's a distinct type from generic Exception
        assert DecryptionError is not Exception

    def test_merchant_service_catches_decryption_error(self):
        """merchant_service must catch DecryptionError specifically."""
        import inspect
        from app.services.merchant_service import MerchantService

        source = inspect.getsource(MerchantService.get_razorpay_client)
        assert "DecryptionError" in source, "get_razorpay_client must catch DecryptionError"
        assert "except Exception" not in source, "get_razorpay_client must not catch bare Exception"


# ---------------------------------------------------------------------------
# P2-4: Request body size limit
# ---------------------------------------------------------------------------

class TestBodySizeLimit:
    def test_oversized_request_returns_413(self, client):
        """Requests with Content-Length > 1MB must return 413."""
        # Create a payload that claims to be over 1MB
        oversized = "x" * (1024 * 1024 + 1)
        resp = client.post(
            "/api/merchants/signin",
            content=oversized,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(oversized)),
            },
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

    def test_normal_request_not_affected(self, client):
        """Normal-sized requests must not be affected by body size limit."""
        resp = client.post("/api/merchants/signin", json={
            "email": "test@example.com",
            "password": "testpassword",
        })
        # Should get 401 (invalid credentials) or 422 (validation), NOT 413
        assert resp.status_code != 413

    def test_health_not_affected(self, client):
        """GET requests (no body) must not be affected."""
        resp = client.get("/api/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# P2-5: Search input sanitization (LIKE wildcards escaped)
# ---------------------------------------------------------------------------

class TestSearchSanitization:
    def test_search_with_percent_literal(self, client, merchant_id):
        """Search containing % must be treated as literal, not wildcard."""
        headers = _auth_header(merchant_id)
        resp = client.get("/api/recoveries?search=100%25", headers=headers)
        # Should return results without SQL error
        assert resp.status_code == 200

    def test_search_with_underscore_literal(self, client, merchant_id):
        """Search containing _ must be treated as literal, not wildcard."""
        headers = _auth_header(merchant_id)
        resp = client.get("/api/recoveries?search=PAY_82931", headers=headers)
        # Should return results (PAY_82931 is a real seed payment)
        assert resp.status_code == 200
        data = resp.json()
        # Should find the payment — _ is escaped, but PAY_82931 matches literally
        assert len(data) >= 1

    def test_search_with_combined_wildcards(self, client, merchant_id):
        """Search with multiple LIKE wildcards must not cause SQL errors."""
        headers = _auth_header(merchant_id)
        resp = client.get("/api/recoveries?search=%25_%25", headers=headers)
        # Should return 200 without SQL injection or errors
        assert resp.status_code == 200

    def test_search_normal_input_works(self, client, merchant_id):
        """Normal search input (no wildcards) must still work correctly."""
        headers = _auth_header(merchant_id)
        resp = client.get("/api/recoveries?search=insufficient", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should find payments with "Insufficient balance" failure reason
        assert len(data) >= 1
