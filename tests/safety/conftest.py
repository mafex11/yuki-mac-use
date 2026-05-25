"""Safety tests: temp vault env."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_safety_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    monkeypatch.setenv("YUKI_ALLOW_RULES_DIR", str(tmp_path / "allow-rules"))
    (vault / "60-Episodes").mkdir(parents=True)
    return vault
