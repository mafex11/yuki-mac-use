"""Project-root pytest fixtures shared across all test packages."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Empty vault rooted at a temp dir, with all sections pre-created.

    Sets YUKI_VAULT_GIT=0 by default — tests that want to verify git-tracking
    behavior should monkeypatch it back to "1" inside the test.
    """
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    from yuki.memory.paths import SECTIONS

    for section in SECTIONS:
        (vault / section).mkdir(parents=True, exist_ok=True)
    return vault
