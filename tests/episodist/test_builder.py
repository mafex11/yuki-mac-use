"""Builder: writes episode markdown to vault."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from yuki.episodist.builder import build_for_date


@pytest.fixture
def vault_and_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seeded_events_db: Path,
) -> Path:
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    return vault


def test_build_writes_episode(vault_and_events: Path) -> None:
    out = build_for_date(date(2026, 5, 21))
    assert out.exists()
    text = out.read_text()
    assert "2026-05-21" in text
    assert "type: episode" in text


def test_build_no_events_creates_empty_episode(vault_and_events: Path) -> None:
    out = build_for_date(date(2026, 5, 1))
    assert out.exists()
    assert "2026-05-01" in out.read_text()


def test_idempotent_overwrites(vault_and_events: Path) -> None:
    a = build_for_date(date(2026, 5, 21))
    b = build_for_date(date(2026, 5, 21))
    assert a == b
