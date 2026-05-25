"""Trigger: from_note round trip, debounce parsing, acceptance accounting."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.triggers.trigger import Trigger


def _note(slug: str = "standup", debounce: str = "1h") -> TriggerNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "time", "cron": "0 10 * * 1-5"}
    return TriggerNote(
        id=f"trigger-{slug}",
        type="trigger",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["user"],
        enabled=True,
        condition=cond,  # type: ignore[arg-type]
        debounce=debounce,
        action={"kind": "suggestion", "text": "standup"},  # type: ignore[arg-type]
        fire_count=0,
        acceptance_rate=0.0,
    )


def test_from_note_round_trip() -> None:
    t = Trigger.from_note(_note(), source_path=Path("/x"), body="")
    assert t.id == "trigger-standup"
    assert t.condition_kind == "time"


def test_debounce_seconds_parses_units() -> None:
    assert Trigger.from_note(_note(debounce="30s"), Path(), "").debounce_seconds == 30
    assert Trigger.from_note(_note(debounce="5m"), Path(), "").debounce_seconds == 300
    assert Trigger.from_note(_note(debounce="2h"), Path(), "").debounce_seconds == 7200
    assert Trigger.from_note(_note(debounce="1d"), Path(), "").debounce_seconds == 86400


def test_invalid_debounce_defaults_to_60() -> None:
    assert Trigger.from_note(_note(debounce="???"), Path(), "").debounce_seconds == 60


def test_record_acceptance_updates_rate() -> None:
    t = Trigger.from_note(_note(), Path(), "")
    t.record_fire(accepted=True)
    t.record_fire(accepted=False)
    t.record_fire(accepted=True)
    assert t.fire_count == 3
    assert abs(t.acceptance_rate - 2 / 3) < 0.01
