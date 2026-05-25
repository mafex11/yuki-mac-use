"""Trusted-routine registry: enter trusted/untrusted, success threshold, exit."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.memory.schemas import RoutineNote
from yuki.memory.vault import Vault
from yuki.safety.trusted import TrustedRoutineRegistry


def _routine(slug: str, trusted: bool = False) -> RoutineNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return RoutineNote(
        id=f"routine-{slug}",
        type="routine",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["scan"],
        name=slug.title(),
        schedule="weekdays 9am",
        steps=[],
        trusted=trusted,
    )


def test_is_trusted_returns_false_when_not_active(tmp_safety_env: Path) -> None:
    reg = TrustedRoutineRegistry()
    assert reg.is_active() is False


def test_enter_makes_routine_active(tmp_safety_env: Path) -> None:
    v = Vault()
    v.write(_routine("morning", trusted=True), body="")
    reg = TrustedRoutineRegistry()
    reg.enter("routine-morning")
    assert reg.is_active() is True
    assert reg.current_id() == "routine-morning"


def test_enter_untrusted_routine_is_noop(tmp_safety_env: Path) -> None:
    v = Vault()
    v.write(_routine("untrusted", trusted=False), body="")
    reg = TrustedRoutineRegistry()
    reg.enter("routine-untrusted")
    assert reg.is_active() is False


def test_record_success_then_propose_trust(tmp_safety_env: Path) -> None:
    v = Vault()
    v.write(_routine("morning", trusted=False), body="")
    reg = TrustedRoutineRegistry()
    for _ in range(4):
        assert reg.record_success("routine-morning") is False
    assert reg.record_success("routine-morning") is True


def test_exit_clears_active(tmp_safety_env: Path) -> None:
    v = Vault()
    v.write(_routine("morning", trusted=True), body="")
    reg = TrustedRoutineRegistry()
    reg.enter("routine-morning")
    reg.exit()
    assert reg.is_active() is False
