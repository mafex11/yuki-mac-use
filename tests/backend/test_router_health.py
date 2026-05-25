"""Health: no auth required."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_no_auth_required(unauth_client: TestClient) -> None:
    r = unauth_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
