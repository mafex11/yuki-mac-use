"""Trigger tests: tmp vault + tmp index_db env, sections pre-created."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_trigger_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    (vault / "30-Routines" / "triggers").mkdir(parents=True)
    (vault / "60-Episodes").mkdir(parents=True)
    (vault / "90-Inbox").mkdir(parents=True)
    return vault
