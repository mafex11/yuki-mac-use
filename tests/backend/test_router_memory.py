"""Memory router: write, read, search, validation."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _person_payload(id_: str = "person-x", confidence: float = 0.9) -> dict[str, Any]:
    return {
        "id": id_,
        "type": "person",
        "name": "X",
        "confidence": confidence,
        "source": ["scan"],
        "created_at": "2026-05-22T09:00:00+00:00",
        "updated_at": "2026-05-22T09:00:00+00:00",
    }


def test_write_then_read(client: TestClient) -> None:
    r = client.post(
        "/memory/write", json={"note": _person_payload(), "body": "hello"}
    )
    assert r.status_code == 200

    r2 = client.get("/memory/read", params={"id_or_path": "person-x"})
    assert r2.status_code == 200
    note = r2.json()
    # memory_read returns a note dict; id should be present somewhere.
    assert "person-x" in str(note)


def test_search_returns_hits(client: TestClient) -> None:
    client.post(
        "/memory/write",
        json={"note": _person_payload(), "body": "manager and team lead"},
    )
    r = client.get("/memory/search", params={"query": "manager", "k": 5})
    assert r.status_code == 200
    data = r.json()
    assert "hits" in data


def test_write_invalid_returns_400(client: TestClient) -> None:
    r = client.post("/memory/write", json={"note": {"type": "person"}, "body": ""})
    assert r.status_code == 400
