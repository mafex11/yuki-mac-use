"""/facts CRUD endpoints over fact_store."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_add_then_list_fact(client: TestClient) -> None:
    r = client.post("/facts", json={"text": "I use Linear for tickets"})
    assert r.status_code == 200
    created = r.json()
    assert created["section"] == "identity"
    fid = created["id"]

    r2 = client.get("/facts")
    assert r2.status_code == 200
    facts = r2.json()["facts"]
    assert any(f["id"] == fid for f in facts)


def test_add_empty_text_rejected(client: TestClient) -> None:
    r = client.post("/facts", json={"text": "   "})
    assert r.status_code == 400


def test_delete_fact(client: TestClient) -> None:
    fid = client.post("/facts", json={"text": "Delete me"}).json()["id"]
    r = client.delete(f"/facts/{fid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    facts = client.get("/facts").json()["facts"]
    assert all(f["id"] != fid for f in facts)


def test_delete_missing_returns_404(client: TestClient) -> None:
    r = client.delete("/facts/nope-not-here")
    assert r.status_code == 404
