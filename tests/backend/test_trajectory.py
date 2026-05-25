"""Trajectory: records JSONL, disable env, default id, redaction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yuki.backend.trajectory import TrajectoryRecorder


def test_records_turns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    rec = TrajectoryRecorder(conversation_id="abc")
    rec.record({"type": "user", "text": "hi"})
    rec.record({"type": "thought", "text": "thinking"})
    rec.record({"type": "done", "content": "hello back"})

    out = tmp_path / "abc.jsonl"
    assert out.exists()
    lines = out.read_text().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["type"] == "user"
    assert parsed[2]["content"] == "hello back"


def test_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    monkeypatch.setenv("YUKI_TRAJECTORIES", "0")
    rec = TrajectoryRecorder(conversation_id="abc")
    rec.record({"type": "user", "text": "hi"})
    assert not (tmp_path / "abc.jsonl").exists()


def test_default_conversation_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    rec = TrajectoryRecorder(conversation_id=None)
    rec.record({"type": "x"})
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1


def test_redacts_secret_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    rec = TrajectoryRecorder(conversation_id="r")
    rec.record(
        {
            "type": "tool_call",
            "args": {
                "api_key": "sk-real-key",
                "query": "weather",
                "headers": {"Authorization": "Bearer abc"},
            },
        }
    )
    line = (tmp_path / "r.jsonl").read_text()
    assert "sk-real-key" not in line
    assert "Bearer abc" not in line
    assert "<redacted>" in line
    assert "weather" in line
