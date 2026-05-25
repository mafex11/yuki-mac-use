"""Time condition: cron-due, outside, invalid."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.triggers.conditions import time as time_cond
from yuki.triggers.trigger import Trigger


def _t(cron: str) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "time", "cron": cron}
    note = TriggerNote(
        id="t",
        type="trigger",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        enabled=True,
        condition=cond,  # type: ignore[arg-type]
        debounce="1m",
        action={"kind": "suggestion"},  # type: ignore[arg-type]
        fire_count=0,
        acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def test_matches_when_cron_due() -> None:
    trigger = _t("0 10 * * *")
    now = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    assert time_cond.matches(trigger, now) is True


def test_no_match_outside_cron() -> None:
    trigger = _t("0 10 * * *")
    now = datetime(2026, 5, 22, 11, 30, tzinfo=UTC)
    assert time_cond.matches(trigger, now) is False


def test_invalid_cron_returns_false() -> None:
    trigger = _t("not-a-cron")
    now = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    assert time_cond.matches(trigger, now) is False
