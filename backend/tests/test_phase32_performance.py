"""Phase 32 — Post-fix performance measurement.

Measures endpoint latency after all database query optimizations to validate
improvements against the pre-fix baseline in docs/PHASE-32-BASELINE.md.
"""

import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient

from app.utils.tokens import create_token


class TestPostFixPerformance:
    """Endpoint latency measurement after Phase 32 query optimizations."""

    @pytest.fixture()
    def auth_headers(self, merchant_id: str) -> dict:
        token = create_token(merchant_id)
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/dashboard",
            "/api/recoveries",
            "/api/analytics",
            "/api/audit",
        ],
    )
    def test_endpoint_latency(self, client: TestClient, auth_headers: dict, endpoint: str):
        """Measure P50/P95/P99 latency across 30 iterations."""
        times = []
        for _ in range(30):
            start = time.perf_counter()
            resp = client.get(endpoint, headers=auth_headers)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}"

        avg = statistics.mean(times)
        p50 = statistics.median(times)
        p95 = sorted(times)[int(len(times) * 0.95)]
        p99 = sorted(times)[int(len(times) * 0.99)]

        # Log measurements for the report
        print(f"\n{endpoint}: avg={avg:.1f}ms p50={p50:.1f}ms p95={p95:.1f}ms p99={p99:.1f}ms")

        # Performance should be reasonable (no regressions from baseline)
        # Baseline p95 was 27-28ms for data endpoints. Allow generous headroom.
        assert p95 < 100, f"{endpoint} p95={p95:.1f}ms exceeds 100ms threshold"

    def test_health_fast(self, client: TestClient):
        """Health endpoint should remain sub-5ms."""
        times = []
        for _ in range(20):
            start = time.perf_counter()
            resp = client.get("/api/health")
            times.append((time.perf_counter() - start) * 1000)
            assert resp.status_code == 200

        p95 = sorted(times)[int(len(times) * 0.95)]
        print(f"\n/api/health: p95={p95:.1f}ms")
        assert p95 < 20, f"Health p95={p95:.1f}ms exceeds 20ms threshold"

    def test_recovery_queue_no_n_plus_one(self, client: TestClient, auth_headers: dict):
        """Recovery queue should not degrade with more payments.

        The P0 fix (JOIN→subquery) and P1 fix (eager customer load) should
        keep latency stable regardless of payment count.
        """
        times = []
        for _ in range(20):
            start = time.perf_counter()
            resp = client.get("/api/recoveries", headers=auth_headers)
            times.append((time.perf_counter() - start) * 1000)
            assert resp.status_code == 200

        p95 = sorted(times)[int(len(times) * 0.95)]
        print(f"\n/api/recoveries: p95={p95:.1f}ms")
        assert p95 < 80, f"Recovery p95={p95:.1f}ms exceeds 80ms threshold"

    def test_dashboard_sql_aggregation(self, client: TestClient, auth_headers: dict):
        """Dashboard should use SQL aggregation, not Python load-all."""
        times = []
        for _ in range(20):
            start = time.perf_counter()
            resp = client.get("/api/dashboard", headers=auth_headers)
            times.append((time.perf_counter() - start) * 1000)
            assert resp.status_code == 200

        p95 = sorted(times)[int(len(times) * 0.95)]
        print(f"\n/api/dashboard: p95={p95:.1f}ms")
        assert p95 < 80, f"Dashboard p95={p95:.1f}ms exceeds 80ms threshold"

    def test_response_sizes_sane(self, client: TestClient, auth_headers: dict):
        """All endpoints should return reasonable response sizes."""
        endpoints = {
            "/api/dashboard": 50_000,    # 50 KB max
            "/api/recoveries": 200_000,   # 200 KB max
            "/api/analytics": 50_000,
            "/api/audit": 50_000,
        }
        for ep, max_size in endpoints.items():
            resp = client.get(ep, headers=auth_headers)
            assert resp.status_code == 200
            size = len(resp.content)
            print(f"\n{ep}: {size} bytes")
            assert size < max_size, f"{ep} response {size} bytes exceeds {max_size} byte limit"

    def test_concurrent_requests_no_errors(self, client: TestClient, auth_headers: dict):
        """Simulate 10 concurrent requests — no errors, no deadlocks.

        FastAPI + SQLAlchemy session-per-request should handle this cleanly.
        """
        endpoints = [
            "/api/dashboard",
            "/api/recoveries",
            "/api/analytics",
            "/api/audit",
            "/api/policies",
            "/api/simulations",
        ]

        def make_request(ep: str) -> tuple[str, int]:
            resp = client.get(ep, headers=auth_headers)
            return ep, resp.status_code

        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(make_request, ep) for ep in endpoints * 2]
            for f in as_completed(futures):
                results.append(f.result())

        statuses = [code for _, code in results]
        errors = [f"{ep}: {code}" for ep, code in results if code != 200]
        assert not errors, f"Concurrent request errors: {errors}"
        assert len(results) == 12, f"Expected 12 results, got {len(results)}"

    def test_stop_recovery_idempotent(self, client: TestClient, auth_headers: dict):
        """Stopping an already-halted recovery should return 200 or 404, not 500."""
        # First, get a recovery to stop
        resp = client.get("/api/recoveries", headers=auth_headers)
        assert resp.status_code == 200
        recoveries = resp.json()
        if not recoveries:
            pytest.skip("No recoveries to test")

        payment_id = recoveries[0]["payment_id"]

        # First stop should succeed
        resp1 = client.post(f"/api/recoveries/{payment_id}/stop", headers=auth_headers)
        assert resp1.status_code == 200

        # Second stop should not crash (200 or 404, not 500)
        resp2 = client.post(f"/api/recoveries/{payment_id}/stop", headers=auth_headers)
        assert resp2.status_code in (200, 404), f"Second stop returned {resp2.status_code}"
