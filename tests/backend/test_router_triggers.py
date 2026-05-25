"""Triggers router: create, list, delete, audit."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _trigger_payload(slug: str = "standup") -> dict[str, Any]:
    now = "2026-05-22T09:00:00+00:00"
    return {
        "id": f"trigger-{slug}",
        "type": "trigger",
        "created_at": now,
        "updated_at": now,
        "confidence": 0.9,
        "source": ["user"],
        "enabled": True,
        "condition": {"kind": "time", "cron": "0 10 * * 1-5"},
        "debounce": "1h",
        "action": {"kind": "suggestion", "text": "standup"},
        "fire_count": 0,
        "acceptance_rate": 0.0,
    }


def test_create_then_list(client: TestClient) -> None:
    r = client.post("/triggers", json={"note": _trigger_payload(), "body": ""})
    assert r.status_code == 200
    r2 = client.get("/triggers")
    assert r2.status_code == 200
    ids = {t["id"] for t in r2.json()["triggers"]}
    assert "trigger-standup" in ids


def test_delete(client: TestClient) -> None:
    client.post("/triggers", json={"note": _trigger_payload(), "body": ""})
    r = client.delete("/triggers/trigger-standup")
    assert r.status_code == 200
    r2 = client.get("/triggers")
    assert all(t["id"] != "trigger-standup" for t in r2.json()["triggers"])


def test_audit_returns_lines(client: TestClient) -> None:
    r = client.get("/triggers/audit", params={"date": "2026-05-22"})
    assert r.status_code == 200
    assert "lines" in r.json()
