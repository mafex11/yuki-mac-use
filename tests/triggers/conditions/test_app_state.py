"""app_state: matches APP_FOCUS for target bundle, ignores other events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import app_state
from yuki.triggers.trigger import Trigger


def _t(bundle: str) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "app_state", "bundle_id": bundle, "state": "opened"}
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


def _ev_focus(bundle: str) -> Event:
    return Event(
        ts=datetime.now(UTC),
        kind=EventKind.APP_FOCUS,
        payload={"bundle_id": bundle, "name": "X"},
    )


def test_matches_target_app_focus() -> None:
    assert app_state.matches(_t("com.linear.linear"), _ev_focus("com.linear.linear")) is True


def test_no_match_other_app() -> None:
    assert app_state.matches(_t("com.linear.linear"), _ev_focus("com.apple.Safari")) is False


def test_ignores_non_app_focus_events() -> None:
    e = Event(ts=datetime.now(UTC), kind=EventKind.URL_CHANGE, payload={})
    assert app_state.matches(_t("com.linear.linear"), e) is False
