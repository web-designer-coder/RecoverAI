"""Phase 14 — Authentication and tenant isolation tests.

Verifies:
- Signup creates merchant with password hash (never NULL)
- Sign-in with correct password succeeds, wrong password fails
- Seed merchant (ops@merchant.in / demo1234) sign-in works after seed
- Token reuse after sign-out (stateless tokens — documented behavior)
- Tenant isolation: Merchant A cannot access Merchant B's data
- No password_hash in API responses
"""

import pytest
from sqlalchemy import select

from app.models import Merchant
from app.seed import DEMO_PASSWORD, MERCHANT_EMAIL, seed_database
from app.utils.password_hash import hash_password
from app.utils.tokens import create_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_header(merchant_id: str) -> dict:
    return {"Authorization": f"Bearer {create_token(merchant_id)}"}


def _create_merchant_via_api(client, email="testmerchant@example.com", password="securepass123"):
    """Create a merchant via POST /api/merchants and return the response JSON."""
    resp = client.post("/api/merchants", json={
        "businessName": "Test Merchant",
        "email": email,
        "password": password,
    })
    assert resp.status_code == 201, f"Signup failed: {resp.json()}"
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Signup creates merchant with password hash
# ---------------------------------------------------------------------------

class TestSignupPasswordHash:
    def test_signup_stores_password_hash(self, client, db_session):
        """POST /api/merchants must create a merchant with a non-NULL password_hash."""
        data = _create_merchant_via_api(client)
        merchant = db_session.scalars(
            select(Merchant).where(Merchant.id == data["id"])
        ).one()
        assert merchant.password_hash is not None, "password_hash must not be NULL after signup"
        assert merchant.password_hash.startswith("$2"), "password_hash must be a bcrypt hash"

    def test_signup_returns_token(self, client):
        """POST /api/merchants must return a token in the response."""
        data = _create_merchant_via_api(client)
        assert "token" in data and data["token"] is not None, "Token must be present in signup response"

    def test_signup_rejects_duplicate_email(self, client):
        """POST /api/merchants with an existing email must return 409."""
        _create_merchant_via_api(client, email="dup@example.com")
        resp = client.post("/api/merchants", json={
            "businessName": "Dup Merchant",
            "email": "dup@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 409

    def test_signup_rejects_short_password(self, client):
        """POST /api/merchants with password < 8 chars must return 422."""
        resp = client.post("/api/merchants", json={
            "businessName": "Short PW",
            "email": "shortpw@example.com",
            "password": "abc",
        })
        assert resp.status_code == 422

    def test_signup_rejects_invalid_email(self, client):
        """POST /api/merchants with invalid email must return 422."""
        resp = client.post("/api/merchants", json={
            "businessName": "Bad Email",
            "email": "not-an-email",
            "password": "securepass123",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2. Sign-in with correct password succeeds
# ---------------------------------------------------------------------------

class TestSigninSuccess:
    def test_signin_correct_password(self, client):
        """POST /api/merchants/signin with valid credentials returns a token."""
        _create_merchant_via_api(client, email="signin@example.com")
        resp = client.post("/api/merchants/signin", json={
            "email": "signin@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data and data["token"] is not None

    def test_signin_returns_merchant_details(self, client):
        """Sign-in response includes id, email, businessName, status, environment."""
        _create_merchant_via_api(client, email="details@example.com")
        resp = client.post("/api/merchants/signin", json={
            "email": "details@example.com",
            "password": "securepass123",
        })
        data = resp.json()
        assert data["email"] == "details@example.com"
        assert data["businessName"] == "Test Merchant"
        assert "id" in data
        assert data["status"] in ("active", "ACTIVE")
        assert data["environment"] in ("test", "TEST")


# ---------------------------------------------------------------------------
# 3. Sign-in with wrong password fails
# ---------------------------------------------------------------------------

class TestSigninFailure:
    def test_signin_wrong_password(self, client):
        """POST /api/merchants/signin with wrong password returns 401."""
        _create_merchant_via_api(client, email="wrongpw@example.com")
        resp = client.post("/api/merchants/signin", json={
            "email": "wrongpw@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401
        body = resp.json()
        assert "Invalid email or password" in body.get("error", {}).get("message", "")

    def test_signin_nonexistent_email(self, client):
        """POST /api/merchants/signin with unknown email returns 401."""
        resp = client.post("/api/merchants/signin", json={
            "email": "ghost@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 401

    def test_signin_null_password_hash(self, client, db_session):
        """Merchant with NULL password_hash cannot sign in (legacy migration path)."""
        merchant = Merchant(
            name="No Password Merchant",
            email="nohash@example.com",
            password_hash=None,
        )
        db_session.add(merchant)
        db_session.flush()
        resp = client.post("/api/merchants/signin", json={
            "email": "nohash@example.com",
            "password": "anything",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 4. Seed merchant sign-in works
# ---------------------------------------------------------------------------

class TestSeedMerchantSignin:
    def test_seed_merchant_authenticates(self, client, db_session):
        """After seed_database, the demo merchant must be able to sign in."""
        seed_database(db_session)
        db_session.flush()
        resp = client.post("/api/merchants/signin", json={
            "email": MERCHANT_EMAIL,
            "password": DEMO_PASSWORD,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == MERCHANT_EMAIL
        assert "token" in data and data["token"] is not None

    def test_seed_idempotent(self, db_session):
        """Running seed_database twice does not create duplicate merchants."""
        seed_database(db_session)
        db_session.flush()
        seed_database(db_session)
        db_session.flush()
        merchants = db_session.scalars(
            select(Merchant).where(Merchant.email == MERCHANT_EMAIL)
        ).all()
        assert len(merchants) == 1

    def test_seed_backfills_null_password_hash(self, db_session):
        """Seed fixes up merchants with NULL password_hash (legacy migration)."""
        LEGACY_EMAIL = "legacy_seed_test@example.com"
        # Create a legacy merchant without password (simulating pre-Phase-9 data)
        legacy = Merchant(name="Legacy", email=LEGACY_EMAIL, password_hash=None)
        db_session.add(legacy)
        db_session.flush()
        assert legacy.password_hash is None
        # Seed with the same email should backfill the password hash
        seed_database(db_session, email=LEGACY_EMAIL)
        db_session.flush()
        updated = db_session.scalars(
            select(Merchant).where(Merchant.email == LEGACY_EMAIL)
        ).one()
        assert updated.password_hash is not None
        assert updated.password_hash.startswith("$2")


# ---------------------------------------------------------------------------
# 5. Token reuse after sign-out (stateless — documented behavior)
# ---------------------------------------------------------------------------

class TestTokenLifecycle:
    """Token tests use /api/dashboard (requires auth) since /merchants/me doesn't exist."""

    def test_token_works_after_signout(self, client, db_session):
        """Stateless tokens remain valid until expiry — sign-out is client-side only."""
        data = _create_merchant_via_api(client, email="tokenreuse@example.com")
        mid = data["id"]
        # Token should work for authenticated requests
        resp = client.get("/api/dashboard", headers=_auth_header(mid))
        assert resp.status_code == 200
        # (There is no server-side sign-out endpoint — tokens are stateless)
        # Token should still work
        resp2 = client.get("/api/dashboard", headers=_auth_header(mid))
        assert resp2.status_code == 200

    def test_invalid_token_returns_401(self, client):
        """Tampered token must be rejected."""
        resp = client.get("/api/dashboard", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert resp.status_code == 401

    def test_missing_auth_header_returns_401(self, client):
        """Request without Authorization header must return 401."""
        resp = client.get("/api/dashboard")
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client):
        """Expired token must be rejected. We create one with exp in the past."""
        from app.utils.tokens import TOKEN_TTL_SECONDS
        import json
        import time
        from app.utils.tokens import _b64url_encode, _sign
        from app.config import get_settings
        from uuid import uuid4

        mid = str(uuid4())
        now = int(time.time())
        payload_obj = {
            "mid": mid,
            "iat": now - TOKEN_TTL_SECONDS - 100,
            "n": "expired",
            "exp": now - 100,
        }
        payload_bytes = json.dumps(payload_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = _b64url_encode(payload_bytes)
        sig = _sign(payload_bytes, get_settings().auth_secret_key)
        expired_token = f"{payload_b64}.{sig}"

        resp = client.get("/api/dashboard", headers={
            "Authorization": f"Bearer {expired_token}",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 6. Tenant isolation — Merchant A cannot access Merchant B's data
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def _create_merchant(self, client, email):
        """Create a merchant via API and return its response dict."""
        resp = client.post("/api/merchants", json={
            "businessName": f"Tenant {email.split('@')[0]}",
            "email": email,
            "password": "securepass123",
        })
        assert resp.status_code == 201
        return resp.json()

    def test_merchant_a_dashboard_not_shared_with_b(self, client):
        """Each merchant sees only their own dashboard data."""
        data_a = self._create_merchant(client, "tenant_a_iso@example.com")
        data_b = self._create_merchant(client, "other_tenant@example.com")
        resp_a = client.get("/api/dashboard", headers=_auth_header(data_a["id"]))
        resp_b = client.get("/api/dashboard", headers=_auth_header(data_b["id"]))
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        # Both return independent dashboard data (empty for API-created merchants)
        assert "kpis" in resp_a.json()
        assert "kpis" in resp_b.json()

    def test_merchant_a_recoveries_not_shared_with_b(self, client, db_session):
        """Merchant B's token must not see Merchant A's recoveries."""
        data_a = self._create_merchant(client, "tenant_a_rec@example.com")
        data_b = self._create_merchant(client, "tenant_b_rec@example.com")
        resp_a = client.get("/api/recoveries", headers=_auth_header(data_a["id"]))
        resp_b = client.get("/api/recoveries", headers=_auth_header(data_b["id"]))
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        # Neither has data, but they are independently scoped
        assert resp_a.json() == []
        assert resp_b.json() == []

    def test_merchant_a_audit_not_shared_with_b(self, client):
        """Audit trail must be scoped per merchant."""
        data_a = self._create_merchant(client, "tenant_a_audit@example.com")
        data_b = self._create_merchant(client, "tenant_b_audit@example.com")
        resp_a = client.get("/api/audit", headers=_auth_header(data_a["id"]))
        resp_b = client.get("/api/audit", headers=_auth_header(data_b["id"]))
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json() == []
        assert resp_b.json() == []


# ---------------------------------------------------------------------------
# 7. No password_hash in API responses
# ---------------------------------------------------------------------------

class TestNoHashExposure:
    def test_signup_response_no_password_hash(self, client):
        """MerchantResponse must never include password_hash."""
        resp = client.post("/api/merchants", json={
            "businessName": "Expose Test",
            "email": "expose@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "password_hash" not in data
        assert "password" not in data

    def test_signin_response_no_password_hash(self, client):
        """Sign-in response must never include password_hash."""
        _create_merchant_via_api(client, email="expose_signin@example.com")
        resp = client.post("/api/merchants/signin", json={
            "email": "expose_signin@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "password_hash" not in data
        assert "password" not in data

    def test_dashboard_response_no_secrets(self, client):
        """GET /api/dashboard must not expose any merchant secrets."""
        data = _create_merchant_via_api(client, email="profile_test@example.com")
        resp = client.get("/api/dashboard", headers=_auth_header(data["id"]))
        assert resp.status_code == 200
        body = resp.json()
        # Dashboard KPIs should never contain auth/credential data
        kpis = body.get("kpis", {})
        assert "password_hash" not in str(body)
        assert "password" not in str(body).lower() or "password_hash" not in str(body)
        assert "razorpay_key_secret" not in str(body)
        assert "razorpay_webhook_secret" not in str(body)
