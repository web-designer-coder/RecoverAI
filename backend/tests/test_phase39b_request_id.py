"""39B-2 — X-Request-ID correlation middleware tests."""
import re
import uuid


def test_missing_request_id_is_generated(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    # Default: generated UUID4 string.
    uuid.UUID(rid)


def test_supplied_request_id_is_preserved(client):
    supplied = "client-abc-123"
    resp = client.get("/api/health", headers={"X-Request-ID": supplied})
    assert resp.headers.get("X-Request-ID") == supplied


def test_oversized_request_id_is_truncated(client):
    long = "a" * 500
    resp = client.get("/api/health", headers={"X-Request-ID": long})
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) <= 128


def test_two_requests_without_id_get_distinct_ids(client):
    a = client.get("/api/health").headers["X-Request-ID"]
    b = client.get("/api/health").headers["X-Request-ID"]
    assert a != b


def test_malformed_request_id_is_still_echoed_safely(client):
    # Middleware must not 500 on weird input — accept it, return as-is (capped).
    weird = "!@#$%^&*()"
    resp = client.get("/api/health", headers={"X-Request-ID": weird})
    assert resp.status_code == 200
    # Length-capped: 10 chars here, under 128, so echoed verbatim.
    assert resp.headers["X-Request-ID"] == weird
