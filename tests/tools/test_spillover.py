"""Spillover: short pass-through, oversized spill to disk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yuki.tools.spillover import maybe_spill


@pytest.fixture
def tmp_blobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("YUKI_BLOB_DIR", str(tmp_path))
    return tmp_path


def test_short_result_passes_through(tmp_blobs: Path) -> None:
    out = maybe_spill("hello", max_chars=100, tool_name="x")
    assert out == "hello"


def test_long_string_spills(tmp_blobs: Path) -> None:
    big = "x" * 5000
    out = maybe_spill(big, max_chars=200, tool_name="screenshot")
    assert isinstance(out, dict)
    assert out["spilled"] is True
    assert out["bytes"] >= 5000
    assert "preview" in out
    assert len(out["preview"]) <= 220
    assert Path(out["path"]).exists()
    assert Path(out["path"]).read_text() == big


def test_long_dict_spills_as_json(tmp_blobs: Path) -> None:
    big = {"data": list(range(10_000))}
    out = maybe_spill(big, max_chars=200, tool_name="ax_dump")
    assert isinstance(out, dict)
    assert out["spilled"] is True
    on_disk = json.loads(Path(out["path"]).read_text())
    assert on_disk == big


def test_short_dict_passes_through(tmp_blobs: Path) -> None:
    out = maybe_spill({"x": 1}, max_chars=100, tool_name="x")
    assert out == {"x": 1}
