"""Scanner paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.scan import paths


def test_default_cache_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YUKI_SCAN_CACHE", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    assert paths.cache_dir() == Path("/tmp/fakehome/Library/Caches/Yuki/scan")


def test_cache_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("YUKI_SCAN_CACHE", str(tmp_path))
    assert paths.cache_dir() == tmp_path


def test_raw_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("YUKI_SCAN_CACHE", str(tmp_path))
    assert paths.raw_path("apps") == tmp_path / "raw" / "apps.json"


def test_sentinel_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_VAULT_DIR", "/tmp/v")
    assert paths.sentinel_path() == Path("/tmp/v/.scan_complete")
