"""Regression tests for Phase 34 Bug Fixes (Analytics month format & Recovery Queue endpoints)."""

import re
import pytest
from fastapi.testclient import TestClient
from app.utils.tokens import create_token


class TestBugFixes:
    """Test suite ensuring regressions are prevented for UI/API bug fixes."""

    @pytest.fixture()
    def auth_headers(self, merchant_id: str) -> dict:
        token = create_token(merchant_id)
        return {"Authorization": f"Bearer {token}"}

    def test_analytics_month_format(self, client: TestClient, auth_headers: dict):
        """Verify GET /api/analytics returns valid YYYY-MM formatted month strings in performance."""
        resp = client.get("/api/analytics", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "performance" in data
        month_pattern = re.compile(r"^\d{4}-\d{2}$")
        for point in data["performance"]:
            assert "month" in point
            assert month_pattern.match(point["month"]), f"Month '{point['month']}' does not match YYYY-MM format"

    def test_recovery_list_handles_all_statuses(self, client: TestClient, auth_headers: dict):
        """Verify GET /api/recoveries succeeds and returns a list."""
        resp = client.get("/api/recoveries", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_recovery_detail_not_found_returns_404(self, client: TestClient, auth_headers: dict):
        """Verify GET /api/recoveries/{id} for non-existent payment returns 404 cleanly."""
        missing_id = "pay_TWoq5T0dbrzzEM"
        resp = client.get(f"/api/recoveries/{missing_id}", headers=auth_headers)
        assert resp.status_code == 404
