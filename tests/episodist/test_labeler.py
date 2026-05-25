"""Labeler: dominant app, browser fallback, idle, empty."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from yuki.episodist.labeler import label
from yuki.episodist.sessions import Session
from yuki.observer.events import Event, EventKind


def _session(events: list[Event], start_minute: int = 0) -> Session:
    base = datetime(2026, 5, 21, 9, 0, tzinfo=UTC)
    return Session(
        start=base + timedelta(minutes=start_minute),
        end=base + timedelta(minutes=start_minute + 30),
        events=events,
    )


def _ev(kind: EventKind, payload: dict[str, Any], minute: int = 0) -> Event:
    base = datetime(2026, 5, 21, 9, 0, tzinfo=UTC)
    return Event(ts=base + timedelta(minutes=minute), kind=kind, payload=payload)


def test_label_uses_dominant_app() -> None:
    events = [
        _ev(EventKind.APP_FOCUS, {"name": "Slack", "bundle_id": "x"}),
        _ev(EventKind.WINDOW_TITLE, {"title": "general", "app": "Slack"}, 5),
        _ev(EventKind.WINDOW_TITLE, {"title": "design", "app": "Slack"}, 10),
    ]
    out = label(_session(events))
    assert "Slack" in out


def test_label_falls_back_to_browser_domain() -> None:
    payload = {"url": "https://github.com/me/yuki/pull/3", "browser": "Safari"}
    events = [_ev(EventKind.URL_CHANGE, payload, 2)]
    out = label(_session(events))
    assert "github.com" in out


def test_label_idle_session() -> None:
    events = [_ev(EventKind.IDLE_START, {"seconds": 60})]
    assert "idle" in label(_session(events)).lower()


def test_empty_session_label() -> None:
    s = Session(
        start=datetime(2026, 5, 21, tzinfo=UTC),
        end=datetime(2026, 5, 21, tzinfo=UTC),
        events=[],
    )
    assert label(s) == "Unknown"
