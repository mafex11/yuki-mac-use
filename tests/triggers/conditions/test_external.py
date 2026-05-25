"""external: SSID match, ignore other event kinds."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import external
from yuki.triggers.trigger import Trigger


def _t(**cond_extra: Any) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "external", **cond_extra}
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


def _wifi(ssid: str) -> Event:
    return Event(
        ts=datetime.now(UTC),
        kind=EventKind.WIFI_CHANGED,
        payload={"ssid": ssid},
    )


def test_matches_target_ssid() -> None:
    assert external.matches(_t(ssid="Home"), _wifi("Home")) is True
    assert external.matches(_t(ssid="Home"), _wifi("Office")) is False


def test_ignores_other_kinds() -> None:
    e = Event(ts=datetime.now(UTC), kind=EventKind.APP_FOCUS, payload={})
    assert external.matches(_t(ssid="Home"), e) is False
