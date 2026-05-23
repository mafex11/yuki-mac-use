"""CostTracker — per-session token totals persisted to JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yuki.agent.cost import CostTracker


@pytest.fixture
def tmp_cost_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("YUKI_COST_DIR", str(tmp_path))
    return tmp_path


def test_records_usage_per_call(tmp_cost_dir: Path) -> None:
    c = CostTracker(session_id="abc")
    c.record(
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=80,
        cache_creation_tokens=20,
        model="claude-sonnet-4-6",
    )
    c.record(
        input_tokens=20,
        output_tokens=10,
        cache_read_tokens=15,
        cache_creation_tokens=0,
        model="claude-sonnet-4-6",
    )
    totals = c.totals()
    assert totals["input_tokens"] == 120
    assert totals["output_tokens"] == 60
    assert totals["cache_read_tokens"] == 95


def test_persists_to_disk(tmp_cost_dir: Path) -> None:
    c = CostTracker(session_id="xyz")
    c.record(
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        model="claude-sonnet-4-6",
    )
    path = tmp_cost_dir / "xyz.cost.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["totals"]["input_tokens"] == 10


def test_resume_existing_session(tmp_cost_dir: Path) -> None:
    c1 = CostTracker(session_id="r")
    c1.record(
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        model="claude-sonnet-4-6",
    )
    c2 = CostTracker(session_id="r")
    assert c2.totals()["input_tokens"] == 10
