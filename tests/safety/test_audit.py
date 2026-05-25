"""Action audit: dated file, append multiple."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.safety.audit import append_action_audit


def test_writes_to_dated_file(tmp_safety_env: Path) -> None:
    append_action_audit(
        tool_name="calendar",
        args={"action": "list"},
        danger="read_only",
        reason="auto_read_only",
        ts=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
    )
    out = tmp_safety_env / "60-Episodes" / "actions-2026-05-22.md"
    assert out.exists()
    text = out.read_text()
    assert "calendar" in text
    assert "auto_read_only" in text


def test_appends_multiple(tmp_safety_env: Path) -> None:
    base = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    for i in range(3):
        append_action_audit(
            tool_name=f"t{i}",
            args={},
            danger="reversible",
            reason="user",
            ts=base,
        )
    out = (tmp_safety_env / "60-Episodes" / "actions-2026-05-22.md").read_text()
    assert "t0" in out and "t1" in out and "t2" in out
