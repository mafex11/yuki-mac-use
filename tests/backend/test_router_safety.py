"""Safety router: burst engage / disengage / status."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_burst_engage(client: TestClient) -> None:
    r = client.post("/safety/burst", json={"duration": 30})
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_burst_disengage(client: TestClient) -> None:
    client.post("/safety/burst", json={"duration": 30})
    r = client.delete("/safety/burst")
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_burst_status(client: TestClient) -> None:
    r = client.get("/safety/burst")
    assert r.status_code == 200
    assert "active" in r.json()
