"""CLI: auto-loads .env from cwd and project root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from yuki.backend.cli import _load_env_files


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YUKI_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("YUKI_LLM_PROVIDER", raising=False)


def test_loads_env_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "YUKI_AUTH_TOKEN=fromenv\nYUKI_LLM_PROVIDER=ollama\n"
    )
    loaded = _load_env_files()
    assert tmp_path / ".env" in loaded
    assert os.environ["YUKI_AUTH_TOKEN"] == "fromenv"
    assert os.environ["YUKI_LLM_PROVIDER"] == "ollama"


def test_real_env_wins_over_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If YUKI_AUTH_TOKEN is already set in the shell, .env must not overwrite it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YUKI_AUTH_TOKEN", "from-shell")
    (tmp_path / ".env").write_text("YUKI_AUTH_TOKEN=from-dotenv\n")
    _load_env_files()
    assert os.environ["YUKI_AUTH_TOKEN"] == "from-shell"


def test_no_env_files_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # Project root .env may exist (the dev .env); just check cwd path absent.
    loaded = _load_env_files()
    assert tmp_path / ".env" not in loaded
