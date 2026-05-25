"""Confirmer: queued responses, default approve, history."""

from __future__ import annotations

from yuki.safety.confirmer import InMemoryConfirmer
from yuki.safety.decision import Decision, Reason


async def test_in_memory_returns_queued_decision() -> None:
    c = InMemoryConfirmer(
        responses=[
            Decision.approve(payload={"x": 1}),
            Decision.deny(reason=Reason.USER),
        ]
    )
    a = await c.ask(tool_name="t", args={}, danger="reversible", preview="p")
    b = await c.ask(tool_name="t", args={}, danger="reversible", preview="p")
    assert a.approved is True
    assert b.approved is False


async def test_in_memory_default_approves() -> None:
    c = InMemoryConfirmer()
    decision = await c.ask(tool_name="t", args={}, danger="reversible", preview="p")
    assert decision.approved is True


async def test_records_history() -> None:
    c = InMemoryConfirmer()
    await c.ask(
        tool_name="calendar",
        args={"action": "list"},
        danger="read_only",
        preview="",
    )
    assert c.asked == [("calendar", {"action": "list"}, "read_only", "")]
