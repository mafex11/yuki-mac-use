"""deviation: missed_recurring_meeting, end_of_day_overrun, unknown."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import deviation
from yuki.triggers.trigger import Trigger


def _t(deviation_kind: str, **extra: Any) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {
        "kind": "deviation",
        "deviation_kind": deviation_kind,
        **extra,
    }
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


def _ev(kind: EventKind, payload: dict[str, Any], hour: int = 9) -> Event:
    return Event(ts=datetime(2026, 5, 22, hour, tzinfo=UTC), kind=kind, payload=payload)


def test_missed_recurring_meeting_fires_when_no_meeting_app() -> None:
    t = _t("missed_recurring_meeting", expected_apps=["us.zoom.xos"])
    e = _ev(EventKind.EVENT_STARTING, {"id": "e", "title": "Standup"})
    assert deviation.matches(t, e) is True


def test_end_of_day_overrun_after_quit_hour() -> None:
    t = _t("end_of_day_overrun", quit_hour=18)
    e_late = _ev(
        EventKind.APP_FOCUS,
        {"bundle_id": "com.linear.linear", "name": "Linear"},
        hour=21,
    )
    e_early = _ev(
        EventKind.APP_FOCUS,
        {"bundle_id": "com.linear.linear", "name": "Linear"},
        hour=10,
    )
    assert deviation.matches(t, e_late) is True
    assert deviation.matches(t, e_early) is False


def test_unknown_deviation_kind_returns_false() -> None:
    assert deviation.matches(_t("aliens"), _ev(EventKind.APP_FOCUS, {})) is False
