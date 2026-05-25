"""Session segmentation: 5min gap splits into separate sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from yuki.episodist.sessions import segment
from yuki.observer.events import Event, EventKind


def _e(
    min_offset: int,
    kind: EventKind = EventKind.APP_FOCUS,
    payload: dict[str, Any] | None = None,
) -> Event:
    base = datetime(2026, 5, 21, 9, 0, tzinfo=UTC)
    return Event(ts=base + timedelta(minutes=min_offset), kind=kind, payload=payload or {})


def test_single_session_when_close_in_time() -> None:
    events = [_e(0), _e(1), _e(3), _e(4)]
    sessions = segment(events, gap_minutes=5)
    assert len(sessions) == 1
    assert sessions[0].duration_minutes() >= 4


def test_split_on_gap() -> None:
    events = [_e(0), _e(1), _e(20), _e(21)]
    sessions = segment(events, gap_minutes=5)
    assert len(sessions) == 2


def test_empty_events_returns_no_sessions() -> None:
    assert segment([], gap_minutes=5) == []


def test_one_event_creates_one_session() -> None:
    sessions = segment([_e(0)], gap_minutes=5)
    assert len(sessions) == 1
    assert sessions[0].duration_minutes() == 0
