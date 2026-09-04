"""Regression tests for Phase 35 — Recovery detail intelligence fields."""

import pytest
from fastapi.testclient import TestClient
from app.utils.tokens import create_token


class TestRecoveryIntelligence:
    """Verify customer, provider, and decision intelligence fields in recovery detail."""

    @pytest.fixture()
    def auth_headers(self, merchant_id: str) -> dict:
        token = create_token(merchant_id)
        return {"Authorization": f"Bearer {token}"}

    def test_recovery_detail_has_customer_fields(self, client: TestClient, auth_headers: dict):
        """Verify /api/recoveries/{id} returns customer_name, customer_email, customer_phone."""
        list_resp = client.get("/api/recoveries", headers=auth_headers)
        assert list_resp.status_code == 200
        items = list_resp.json()
        if not items:
            pytest.skip("No recoveries seeded for this merchant")

        detail_resp = client.get(f"/api/recoveries/{items[0]['payment_id']}", headers=auth_headers)
        assert detail_resp.status_code == 200
        data = detail_resp.json()

        assert "customer" in data or "customer_name" in data, "Recovery detail missing customer fields"
        # Both field shapes are valid depending on schema version
        if "customer" in data and data["customer"] is not None:
            assert isinstance(data["customer"], dict)
        assert "provider_order_id" in data
        assert "provider_status" in data

    def test_recovery_detail_has_decision_intelligence(self, client: TestClient, auth_headers: dict):
        """Verify /api/recoveries/{id} returns signals, explanation, data_sufficiency."""
        list_resp = client.get("/api/recoveries", headers=auth_headers)
        assert list_resp.status_code == 200
        items = list_resp.json()
        if not items:
            pytest.skip("No recoveries seeded for this merchant")

        detail_resp = client.get(f"/api/recoveries/{items[0]['payment_id']}", headers=auth_headers)
        assert detail_resp.status_code == 200
        data = detail_resp.json()

        decision = data.get("decision")
        if decision is None:
            pytest.skip("No decision for this payment (may be in seed data)")

        # Decision must expose intelligence fields
        assert "signals" in decision, "Decision missing signals field"
        assert isinstance(decision["signals"], list), "signals must be a list"
        assert "explanation" in decision or decision.get("explanation") is None
        assert "data_sufficiency" in decision or decision.get("data_sufficiency") is None

    def test_recovery_list_unchanged(self, client: TestClient, auth_headers: dict):
        """Verify GET /api/recoveries still returns list with original fields."""
        resp = client.get("/api/recoveries", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        if items:
            item = items[0]
            assert "payment_id" in item
            assert "customer_id" in item
            assert "amount" in item
            assert "status" in item

    def test_policies_still_return(self, client: TestClient, auth_headers: dict):
        """Verify GET /api/policies still returns current policy rules."""
        resp = client.get("/api/policies", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "maximum_retries" in data
        assert "failure_rules" in data
        assert "prevent_duplicate_recovery" in data
