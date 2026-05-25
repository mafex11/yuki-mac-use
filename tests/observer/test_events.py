"""Event dataclass round-trip + row encoding."""

from __future__ import annotations

from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind


def test_event_round_trip() -> None:
    ts = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    e = Event(ts=ts, kind=EventKind.APP_FOCUS, payload={"bundle_id": "com.apple.Safari"})
    e2 = Event.from_dict(e.to_dict())
    assert e2 == e


def test_event_to_row_returns_int_ms() -> None:
    ts = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    e = Event(ts=ts, kind=EventKind.IDLE_START, payload={"seconds": 60})
    ts_ms, kind, payload_json = e.to_row()
    assert isinstance(ts_ms, int)
    assert kind == "idle_start"
    assert "seconds" in payload_json


def test_eventkind_values() -> None:
    assert EventKind.APP_FOCUS.value == "app_focus"
    assert EventKind.IDLE_END.value == "idle_end"
    assert EventKind.WIFI_CHANGED.value == "wifi_changed"
