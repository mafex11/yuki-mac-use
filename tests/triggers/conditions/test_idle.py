"""idle: above threshold, after_hour gate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import idle
from yuki.triggers.trigger import Trigger


def _t(min_minutes: int = 30, after_hour: int | None = None) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "idle", "min_minutes": min_minutes}
    if after_hour is not None:
        cond["after_hour"] = after_hour
    note = TriggerNote(
        id="t",
        type="trigger",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        enabled=True,
        condition=cond,  # type: ignore[arg-type]
        debounce="1h",
        action={"kind": "suggestion"},  # type: ignore[arg-type]
        fire_count=0,
        acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def _idle_event(seconds: float, hour: int = 19) -> Event:
    return Event(
        ts=datetime(2026, 5, 22, hour, tzinfo=UTC),
        kind=EventKind.IDLE_START,
        payload={"seconds": seconds},
    )


def test_matches_idle_above_threshold() -> None:
    assert idle.matches(_t(min_minutes=30), _idle_event(seconds=2000)) is True


def test_no_match_below_threshold() -> None:
    assert idle.matches(_t(min_minutes=30), _idle_event(seconds=300)) is False


def test_after_hour_gate() -> None:
    t = _t(min_minutes=30, after_hour=18)
    assert idle.matches(t, _idle_event(seconds=2000, hour=10)) is False
    assert idle.matches(t, _idle_event(seconds=2000, hour=20)) is True
