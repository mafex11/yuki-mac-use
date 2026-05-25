"""Pruner: proposes disable when low acceptance after enough fires."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote
from yuki.triggers.pruner import maybe_propose_disable
from yuki.triggers.trigger import Trigger


def _t(fire_count: int, acceptance_rate: float) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    cond: dict[str, Any] = {"kind": "time", "cron": "* * * * *"}
    note = TriggerNote(
        id="trigger-x",
        type="trigger",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        enabled=True,
        condition=cond,  # type: ignore[arg-type]
        debounce="1m",
        action={"kind": "suggestion"},  # type: ignore[arg-type]
        fire_count=fire_count,
        acceptance_rate=acceptance_rate,
    )
    return Trigger.from_note(note, Path(), "")


def test_proposes_when_low_acceptance(tmp_trigger_env: Path) -> None:
    out = maybe_propose_disable(_t(fire_count=10, acceptance_rate=0.2))
    assert out is not None
    assert out.exists()
    assert "trigger-x" in out.read_text()


def test_no_propose_when_not_enough_fires(tmp_trigger_env: Path) -> None:
    assert maybe_propose_disable(_t(fire_count=5, acceptance_rate=0.1)) is None


def test_no_propose_when_acceptance_high(tmp_trigger_env: Path) -> None:
    assert maybe_propose_disable(_t(fire_count=20, acceptance_rate=0.8)) is None


def test_idempotent(tmp_trigger_env: Path) -> None:
    t = _t(fire_count=10, acceptance_rate=0.1)
    a = maybe_propose_disable(t)
    b = maybe_propose_disable(t)
    assert a == b
