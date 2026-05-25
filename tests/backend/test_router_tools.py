"""Tools router: lists native tools, requires auth."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_tools_endpoint_lists_native(client: TestClient) -> None:
    r = client.get("/tools")
    assert r.status_code == 200
    data = r.json()
    assert "tools" in data
    names = {t["name"] for t in data["tools"]}
    assert "calendar" in names


def test_tools_endpoint_requires_auth(unauth_client: TestClient) -> None:
    r = unauth_client.get("/tools")
    assert r.status_code == 401
