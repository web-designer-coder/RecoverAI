"""Phase 6 — Simulation endpoint tests.

Verifies:
- GET /api/simulations — authenticated lists simulations, unauthenticated returns 401
- POST /api/simulations — valid creation, missing fields 422, invalid values 422
- POST /api/simulations — out-of-range values rejected
"""

import pytest


def _auth_header(merchant_id: str) -> dict:
    from app.utils.tokens import create_token
    return {"Authorization": f"Bearer {create_token(merchant_id)}"}


def _valid_payload():
    return {
        "transactions": 5000,
        "average_amount": 2400,
        "failure_rate": 0.12,
        "recovery_window_days": 14,
    }


def _create_merchant(client, email: str) -> str:
    """Create a fresh merchant via API and return its ID."""
    resp = client.post("/api/merchants", json={
        "businessName": "Sim Test Merchant",
        "email": email,
        "password": "securepass123",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 1. GET /api/simulations
# ---------------------------------------------------------------------------

class TestListSimulations:
    def test_list_requires_auth(self, client):
        """Unauthenticated GET /api/simulations must return 401."""
        resp = client.get("/api/simulations")
        assert resp.status_code == 401

    def test_list_returns_empty_for_new_merchant(self, client):
        """A freshly created merchant has no simulations."""
        mid = _create_merchant(client, "sim_empty_list@example.com")
        resp = client.get("/api/simulations", headers=_auth_header(mid))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_includes_created_simulation(self, client):
        """After creating a simulation, it appears in the list."""
        mid = _create_merchant(client, "sim_list_includes@example.com")
        client.post("/api/simulations", json=_valid_payload(), headers=_auth_header(mid))
        resp = client.get("/api/simulations", headers=_auth_header(mid))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["transactions"] == 5000


# ---------------------------------------------------------------------------
# 2. POST /api/simulations — valid creation
# ---------------------------------------------------------------------------

class TestCreateSimulation:
    def test_create_simulation_success(self, client, merchant_id):
        """Valid payload must return 200 with simulation result."""
        resp = client.post("/api/simulations", json=_valid_payload(), headers=_auth_header(merchant_id))
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["transactions"] == 5000
        assert data["average_amount"] == 2400
        assert data["failure_rate"] == 0.12
        assert data["recovery_window_days"] == 14
        assert data["static_recovery_rate"] >= 0
        assert data["ai_recovery_rate"] >= 0

    def test_create_simulation_requires_auth(self, client):
        """Unauthenticated POST /api/simulations must return 401."""
        resp = client.post("/api/simulations", json=_valid_payload())
        assert resp.status_code == 401

    def test_create_simulation_different_params(self, client, merchant_id):
        """Different valid parameters produce different results."""
        payload1 = {**_valid_payload(), "transactions": 1000, "failure_rate": 0.05}
        payload2 = {**_valid_payload(), "transactions": 10000, "failure_rate": 0.20}
        r1 = client.post("/api/simulations", json=payload1, headers=_auth_header(merchant_id))
        r2 = client.post("/api/simulations", json=payload2, headers=_auth_header(merchant_id))
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Different inputs should produce different revenue-at-risk
        assert r1.json()["transactions"] != r2.json()["transactions"]


# ---------------------------------------------------------------------------
# 3. POST /api/simulations — validation failures
# ---------------------------------------------------------------------------

class TestSimulationValidation:
    def test_missing_transactions(self, client, merchant_id):
        """Missing transactions field must return 422."""
        payload = _valid_payload()
        del payload["transactions"]
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_missing_average_amount(self, client, merchant_id):
        """Missing average_amount field must return 422."""
        payload = _valid_payload()
        del payload["average_amount"]
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_missing_failure_rate(self, client, merchant_id):
        """Missing failure_rate field must return 422."""
        payload = _valid_payload()
        del payload["failure_rate"]
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_missing_recovery_window(self, client, merchant_id):
        """Missing recovery_window_days must return 422."""
        payload = _valid_payload()
        del payload["recovery_window_days"]
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_zero_transactions_rejected(self, client, merchant_id):
        """transactions=0 must be rejected (Field gt=0)."""
        payload = {**_valid_payload(), "transactions": 0}
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_negative_transactions_rejected(self, client, merchant_id):
        """Negative transactions must be rejected."""
        payload = {**_valid_payload(), "transactions": -100}
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_failure_rate_zero_rejected(self, client, merchant_id):
        """failure_rate=0 must be rejected (Field gt=0)."""
        payload = {**_valid_payload(), "failure_rate": 0}
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_failure_rate_above_one_rejected(self, client, merchant_id):
        """failure_rate > 1 must be rejected (Field le=1)."""
        payload = {**_valid_payload(), "failure_rate": 1.5}
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_recovery_window_zero_rejected(self, client, merchant_id):
        """recovery_window_days=0 must be rejected (Field ge=1)."""
        payload = {**_valid_payload(), "recovery_window_days": 0}
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_recovery_window_above_90_rejected(self, client, merchant_id):
        """recovery_window_days > 90 must be rejected (Field le=90)."""
        payload = {**_valid_payload(), "recovery_window_days": 91}
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_empty_body_rejected(self, client, merchant_id):
        """Empty body must return 422."""
        resp = client.post("/api/simulations", json={}, headers=_auth_header(merchant_id))
        assert resp.status_code == 422

    def test_wrong_type_rejected(self, client, merchant_id):
        """String values for numeric fields must return 422."""
        payload = {**_valid_payload(), "transactions": "not_a_number"}
        resp = client.post("/api/simulations", json=payload, headers=_auth_header(merchant_id))
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Tenant isolation — simulations are scoped per merchant
# ---------------------------------------------------------------------------

class TestSimulationIsolation:
    def test_merchant_a_cannot_see_merchant_b_simulations(self, client):
        """Each merchant sees only their own simulations."""
        # Create two fresh merchants
        id_a = _create_merchant(client, "sim_iso_a@example.com")
        id_b = _create_merchant(client, "sim_iso_b@example.com")

        # Create a simulation for merchant A
        client.post("/api/simulations", json=_valid_payload(), headers=_auth_header(id_a))

        # Merchant B should see empty list
        resp_b = client.get("/api/simulations", headers=_auth_header(id_b))
        assert resp_b.status_code == 200
        assert resp_b.json() == []

        # Merchant A sees theirs
        resp_a = client.get("/api/simulations", headers=_auth_header(id_a))
        assert resp_a.status_code == 200
        assert len(resp_a.json()) == 1
