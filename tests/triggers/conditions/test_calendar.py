"""Calendar condition: substring filter, EVENT_STARTING gating."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import calendar as cal_cond
from yuki.triggers.trigger import Trigger


def _t(title_contains: str = "") -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "calendar", "title_contains": title_contains}
    note = TriggerNote(
        id="t",
        type="trigger",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        enabled=True,
        condition=cond,  # type: ignore[arg-type]
        debounce="5m",
        action={"kind": "suggestion"},  # type: ignore[arg-type]
        fire_count=0,
        acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def _ev(title: str) -> Event:
    return Event(
        ts=datetime.now(UTC),
        kind=EventKind.EVENT_STARTING,
        payload={"title": title, "id": "e1", "start": "2026-05-22T10:00:00+00:00"},
    )


def test_matches_any_event_starting_when_no_filter() -> None:
    assert cal_cond.matches(_t(""), _ev("Standup")) is True


def test_matches_substring_filter() -> None:
    assert cal_cond.matches(_t("standup"), _ev("Daily Standup")) is True
    assert cal_cond.matches(_t("standup"), _ev("Lunch")) is False


def test_ignores_non_calendar_events() -> None:
    e = Event(ts=datetime.now(UTC), kind=EventKind.APP_FOCUS, payload={})
    assert cal_cond.matches(_t(""), e) is False
