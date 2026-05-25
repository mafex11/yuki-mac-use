"""Gatekeeper: danger matrix, escape valves, audit."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import RoutineNote
from yuki.memory.vault import Vault
from yuki.safety.burst import BurstMode
from yuki.safety.confirmer import InMemoryConfirmer
from yuki.safety.decision import Decision, Reason
from yuki.safety.gatekeeper import Gatekeeper
from yuki.safety.trusted import TrustedRoutineRegistry
from yuki.tools.native.registry import DangerLevel, ToolSpec


def _spec(name: str, danger: DangerLevel) -> ToolSpec:
    async def fn(**kwargs: Any) -> None:
        return None

    return ToolSpec(
        name=name,
        danger=danger,
        description="",
        parameters={},
        fn=fn,
    )


async def test_read_only_auto_approves(tmp_safety_env: Path) -> None:
    g = Gatekeeper(
        confirmer=InMemoryConfirmer(),
        trusted=TrustedRoutineRegistry(),
        burst=BurstMode(),
    )
    d = await g.gate(_spec("calendar", DangerLevel.READ_ONLY), {"action": "list"})
    assert d.approved is True
    assert d.reason == Reason.AUTO_READ_ONLY


async def test_reversible_default_confirms(tmp_safety_env: Path) -> None:
    confirmer = InMemoryConfirmer(responses=[Decision.deny()])
    g = Gatekeeper(
        confirmer=confirmer,
        trusted=TrustedRoutineRegistry(),
        burst=BurstMode(),
    )
    d = await g.gate(_spec("notes", DangerLevel.REVERSIBLE), {"action": "delete"})
    assert d.approved is False


async def test_reversible_in_burst_auto_approves(tmp_safety_env: Path) -> None:
    burst = BurstMode()
    burst.engage(duration=10)
    g = Gatekeeper(
        confirmer=InMemoryConfirmer(),
        trusted=TrustedRoutineRegistry(),
        burst=burst,
    )
    d = await g.gate(_spec("notes", DangerLevel.REVERSIBLE), {"x": 1})
    assert d.approved is True
    assert d.reason == Reason.AUTO_BURST_MODE


async def test_reversible_in_trusted_routine_auto_approves(
    tmp_safety_env: Path,
) -> None:
    v = Vault()
    now = datetime(2026, 5, 22, tzinfo=UTC)
    v.write(
        RoutineNote(
            id="routine-x",
            type="routine",
            created_at=now,
            updated_at=now,
            confidence=1.0,
            source=[],
            name="X",
            schedule="?",
            steps=[],
            trusted=True,
        ),
        body="",
    )
    trusted = TrustedRoutineRegistry()
    trusted.enter("routine-x")
    g = Gatekeeper(confirmer=InMemoryConfirmer(), trusted=trusted, burst=BurstMode())
    d = await g.gate(_spec("notes", DangerLevel.REVERSIBLE), {})
    assert d.approved is True
    assert d.reason == Reason.AUTO_TRUSTED_ROUTINE


async def test_external_always_confirms_even_in_trusted(
    tmp_safety_env: Path,
) -> None:
    v = Vault()
    now = datetime(2026, 5, 22, tzinfo=UTC)
    v.write(
        RoutineNote(
            id="routine-x",
            type="routine",
            created_at=now,
            updated_at=now,
            confidence=1.0,
            source=[],
            name="X",
            schedule="?",
            steps=[],
            trusted=True,
        ),
        body="",
    )
    trusted = TrustedRoutineRegistry()
    trusted.enter("routine-x")
    confirmer = InMemoryConfirmer(responses=[Decision.deny()])
    g = Gatekeeper(confirmer=confirmer, trusted=trusted, burst=BurstMode())
    d = await g.gate(_spec("mail", DangerLevel.EXTERNAL), {"to": "x"})
    assert d.approved is False


async def test_record_executed_writes_audit(tmp_safety_env: Path) -> None:
    g = Gatekeeper(
        confirmer=InMemoryConfirmer(),
        trusted=TrustedRoutineRegistry(),
        burst=BurstMode(),
    )
    spec = _spec("notes", DangerLevel.REVERSIBLE)
    d = Decision.approve(payload={"x": 1}, reason=Reason.USER)
    g.record_executed(spec, {"x": 1}, d)
    files = list((tmp_safety_env / "60-Episodes").glob("actions-*.md"))
    assert len(files) == 1
