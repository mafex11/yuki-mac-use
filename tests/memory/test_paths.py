"""Paths module — vault dir + index db path with env overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.memory import paths


def test_default_vault_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YUKI_VAULT_DIR", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    assert paths.vault_dir() == Path("/tmp/fakehome/YukiVault")


def test_default_index_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YUKI_INDEX_DB", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    expected = Path("/tmp/fakehome/Library/Application Support/Yuki/index.db")
    assert paths.index_db_path() == expected


def test_env_override_vault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "vault"))
    assert paths.vault_dir() == tmp_path / "vault"


def test_env_override_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    assert paths.index_db_path() == tmp_path / "index.db"


def test_section_dirs() -> None:
    sections = paths.SECTIONS
    assert "00-Identity" in sections
    assert "10-People" in sections
    assert "30-Routines" in sections
    assert "60-Episodes" in sections
    assert "90-Inbox" in sections
    assert len(sections) == 9


def test_app_support_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YUKI_APP_SUPPORT", raising=False)
    monkeypatch.setenv("HOME", "/Users/test")
    assert paths.app_support_dir() == Path(
        "/Users/test/Library/Application Support/Yuki"
    )


def test_app_support_dir_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_APP_SUPPORT", "/tmp/yuki")
    assert paths.app_support_dir() == Path("/tmp/yuki")


def test_socket_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_APP_SUPPORT", "/tmp/yuki")
    assert paths.socket_path() == Path("/tmp/yuki/yuki.sock")


def test_chat_history_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_APP_SUPPORT", "/tmp/yuki")
    assert paths.chat_history_path() == Path("/tmp/yuki/chat_history.jsonl")
