"""Project-root pytest fixtures shared across all test packages."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_keychain_prompts() -> None:
    """Never let a test trigger the macOS Keychain GUI password prompt.

    `make_llm`/`appstate.api_key_for` falls back to the `security` CLI when an
    api key isn't in the env. Tests that scrub env keys would otherwise make
    that CLI pop a blocking "allow access?" dialog (3x), which can't be answered
    in an unattended run. Setting this for the whole session keeps `pytest`
    fully non-interactive.
    """
    os.environ["YUKI_NO_KEYCHAIN"] = "1"
    # Never start the real observer daemon (AX/AppleScript polling) in tests.
    os.environ["YUKI_OBSERVER"] = "0"


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
