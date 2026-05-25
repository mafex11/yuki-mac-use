"""Audit: file per date; appends multiple entries."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.triggers.audit import append_to_audit
from yuki.triggers.presenter import Suggestion


def test_audit_creates_file_per_date(tmp_trigger_env: Path) -> None:
    s = Suggestion(
        trigger_id="trigger-standup",
        text="Standup time",
        urgency="medium",
        ts=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
    )
    append_to_audit(s, accepted=True)
    out = tmp_trigger_env / "60-Episodes" / "triggers-2026-05-22.md"
    assert out.exists()
    text = out.read_text()
    assert "trigger-standup" in text
    assert "accepted" in text


def test_audit_appends_multiple(tmp_trigger_env: Path) -> None:
    base = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    for i in range(3):
        append_to_audit(
            Suggestion(
                trigger_id=f"t{i}",
                text=f"x{i}",
                urgency="low",
                ts=base,
            ),
            accepted=False,
        )
    out = (tmp_trigger_env / "60-Episodes" / "triggers-2026-05-22.md").read_text()
    assert "t0" in out and "t1" in out and "t2" in out
