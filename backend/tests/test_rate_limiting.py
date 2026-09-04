"""Phase 26.5 — Rate limiting tests for authentication endpoints.

Verifies:
- Normal valid login succeeds without rate limit interference
- Invalid login returns 401
- Repeated failed logins eventually trigger 429
- Successful login resets the failure counter
- 429 includes Retry-After header
- No account enumeration via rate limit
- Signup endpoint also rate-limited
- Health endpoint NOT rate-limited
"""

import pytest

from app.limiter import limiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_limiter():
    """Clear rate limit state before and after each test."""
    limiter.clear()
    yield
    limiter.clear()


def _create_merchant(client, email="ratelimit@example.com", password="securepass123"):
    """Create a merchant via the API and return the response JSON."""
    resp = client.post("/api/merchants", json={
        "businessName": "Rate Limit Test",
        "email": email,
        "password": password,
    })
    assert resp.status_code == 201, f"Signup failed: {resp.json()}"
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Normal login succeeds
# ---------------------------------------------------------------------------

class TestRateLimitBaseline:
    def test_valid_login_succeeds(self, client):
        """Normal login with correct credentials returns 200 with token."""
        _create_merchant(client, email="baseline@example.com")
        resp = client.post("/api/merchants/signin", json={
            "email": "baseline@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert body["email"] == "baseline@example.com"

    def test_invalid_login_returns_401(self, client):
        """Wrong password returns 401 with generic error message."""
        _create_merchant(client, email="wrong@example.com")
        resp = client.post("/api/merchants/signin", json={
            "email": "wrong@example.com",
            "password": "definitelywrong",
        })
        assert resp.status_code == 401
        body = resp.json()
        assert "Invalid email or password" in body["error"]["message"]


# ---------------------------------------------------------------------------
# 2. Rate limiting triggers after repeated failures
# ---------------------------------------------------------------------------

class TestSigninRateLimit:
    def test_repeated_failures_trigger_429(self, client):
        """5/minute allows 5 attempts; the 6th triggers 429."""
        _create_merchant(client, email="fail5@example.com")

        for i in range(5):
            resp = client.post("/api/merchants/signin", json={
                "email": "fail5@example.com",
                "password": "wrongpassword",
            })
            assert resp.status_code == 401, f"Attempt {i + 1} should be 401"

        # 6th attempt should be rate-limited
        resp = client.post("/api/merchants/signin", json={
            "email": "fail5@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMITED"
        assert "Too many" in body["error"]["message"]

    def test_429_includes_retry_after_header(self, client):
        """429 response includes Retry-After header."""
        _create_merchant(client, email="retry@example.com")
        for _ in range(5):
            client.post("/api/merchants/signin", json={
                "email": "retry@example.com",
                "password": "wrong",
            })
        resp = client.post("/api/merchants/signin", json={
            "email": "retry@example.com",
            "password": "wrong",
        })
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


# ---------------------------------------------------------------------------
# 3. Successful login resets the failure counter
# ---------------------------------------------------------------------------

class TestRateLimitReset:
    def test_successful_login_resets_counter(self, client):
        """3 failures + 1 success = 200, then more failures should still work."""
        _create_merchant(client, email="reset@example.com", password="securepass123")

        # 3 failures
        for _ in range(3):
            client.post("/api/merchants/signin", json={
                "email": "reset@example.com",
                "password": "wrongpassword",
            })

        # Successful login — resets counter
        resp = client.post("/api/merchants/signin", json={
            "email": "reset@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 200

        # Should be able to fail again without 429
        resp = client.post("/api/merchants/signin", json={
            "email": "reset@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401  # not 429


# ---------------------------------------------------------------------------
# 4. No account enumeration
# ---------------------------------------------------------------------------

class TestNoEnumeration:
    def test_no_account_enumeration(self, client):
        """Rate limiting fires the same way for nonexistent emails."""
        for i in range(5):
            resp = client.post("/api/merchants/signin", json={
                "email": "ghost_nonexistent@example.com",
                "password": "anypassword",
            })
            assert resp.status_code == 401, f"Attempt {i + 1} should be 401, not {resp.status_code}"

        # 6th attempt should be rate-limited regardless of email existence
        resp = client.post("/api/merchants/signin", json={
            "email": "ghost_nonexistent@example.com",
            "password": "anypassword",
        })
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 5. Signup rate limiting
# ---------------------------------------------------------------------------

class TestSignupRateLimit:
    def test_signup_rate_limiting(self, client):
        """Repeated signup attempts trigger 429 after the limit."""
        for i in range(5):
            resp = client.post("/api/merchants", json={
                "businessName": f"Rate Test {i}",
                "email": f"signup{i}@ratelimit.com",
                "password": "securepass123",
            })
            assert resp.status_code == 201, f"Signup {i + 1} should succeed"

        # 6th signup should be rate-limited
        resp = client.post("/api/merchants", json={
            "businessName": "Rate Test 5",
            "email": "signup5@ratelimit.com",
            "password": "securepass123",
        })
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMITED"


# ---------------------------------------------------------------------------
# 6. Health endpoint not affected
# ---------------------------------------------------------------------------

class TestHealthUnaffected:
    def test_health_not_rate_limited(self, client):
        """Health endpoint is unaffected by auth rate limiting."""
        # Trigger rate limit on signin (6 attempts: 5 allowed, 6th blocked)
        for _ in range(5):
            client.post("/api/merchants/signin", json={
                "email": "anyone@example.com",
                "password": "wrong",
            })
        # Confirm rate limit is active
        resp = client.post("/api/merchants/signin", json={
            "email": "anyone@example.com",
            "password": "wrong",
        })
        assert resp.status_code == 429

        # Health should still work
        resp = client.get("/api/health")
        assert resp.status_code == 200
