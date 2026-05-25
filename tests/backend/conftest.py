"""Backend tests: TestClient with a valid token; reset runtime each test."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yuki.backend.auth import generate_token, set_active_token
from yuki.backend.runtime import reset_runtime
from yuki.backend.server import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path / "trajectories"))
    monkeypatch.setenv("YUKI_ALLOW_RULES_DIR", str(tmp_path / "allow-rules"))
    reset_runtime()
    token = generate_token()
    set_active_token(token)
    app = create_app()
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c
    reset_runtime()


@pytest.fixture
def unauth_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    reset_runtime()
    set_active_token(generate_token())
    app = create_app()
    with TestClient(app) as c:
        yield c
    reset_runtime()
