"""Settings router: defaults, persistence, unknown rejection."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_returns_defaults(client: TestClient) -> None:
    r = client.get("/settings")
    assert r.status_code == 200
    data = r.json()
    assert "settings" in data
    assert "llm_provider" in data["settings"]


def test_put_persists(client: TestClient) -> None:
    r = client.put("/settings", json={"llm_provider": "anthropic"})
    assert r.status_code == 200
    r2 = client.get("/settings")
    assert r2.json()["settings"]["llm_provider"] == "anthropic"


def test_put_unknown_key_rejected(client: TestClient) -> None:
    r = client.put("/settings", json={"banana": "x"})
    assert r.status_code == 400
