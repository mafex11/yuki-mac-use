"""/facts CRUD endpoints over fact_store."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yuki.backend.auth import generate_token, set_active_token
from yuki.backend.runtime import reset_runtime
from yuki.backend.server import create_app


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


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Like `client`, but also isolates appstate (YUKI_APP_SUPPORT)."""
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path / "appsupport"))
    reset_runtime()
    token = generate_token()
    set_active_token(token)
    c = TestClient(create_app())
    c.headers.update({"Authorization": f"Bearer {token}"})
    with c:
        yield c
    reset_runtime()


def test_get_settings_defaults(app_client: TestClient) -> None:
    r = app_client.get("/facts/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["learner_enabled"] is True
    assert body["ask_before_remember"] is True


def test_post_settings_persists(app_client: TestClient) -> None:
    r = app_client.post("/facts/settings", json={"learner_enabled": False})
    assert r.status_code == 200
    assert r.json()["learner_enabled"] is False
    # round-trips
    assert app_client.get("/facts/settings").json()["learner_enabled"] is False
    # untouched toggle unchanged
    assert app_client.get("/facts/settings").json()["ask_before_remember"] is True
