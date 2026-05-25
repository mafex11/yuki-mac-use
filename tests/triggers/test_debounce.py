"""DebounceGuard: first fire allowed, repeat blocked, expiration re-allows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.triggers.debounce import DebounceGuard
from yuki.triggers.trigger import Trigger


def _t(debounce: str, last_fired: datetime | None = None) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "time", "cron": "* * * * *"}
    note = TriggerNote(
        id="t",
        type="trigger",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        enabled=True,
        condition=cond,  # type: ignore[arg-type]
        debounce=debounce,
        action={"kind": "suggestion"},  # type: ignore[arg-type]
        last_fired=last_fired,
        fire_count=0,
        acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def test_first_fire_allowed() -> None:
    g = DebounceGuard()
    now = datetime(2026, 5, 22, 10, tzinfo=UTC)
    assert g.allow(_t("1m"), now) is True


def test_repeat_within_debounce_blocked() -> None:
    g = DebounceGuard()
    now = datetime(2026, 5, 22, 10, tzinfo=UTC)
    t = _t("1m")
    g.mark_fired(t, now)
    assert g.allow(t, now + timedelta(seconds=30)) is False


def test_repeat_after_debounce_allowed() -> None:
    g = DebounceGuard()
    now = datetime(2026, 5, 22, 10, tzinfo=UTC)
    t = _t("1m")
    g.mark_fired(t, now)
    assert g.allow(t, now + timedelta(minutes=2)) is True
