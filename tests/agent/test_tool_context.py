"""ToolUseContext — typed scratch threaded through tool calls."""

from __future__ import annotations

import pytest

from yuki.agent.context_scratch import ToolUseContext


@pytest.mark.asyncio
async def test_context_carries_abort_event() -> None:
    ctx = ToolUseContext.bare()
    assert ctx.abort_event is not None
    assert not ctx.abort_event.is_set()
    ctx.abort_event.set()
    assert ctx.abort_event.is_set()


def test_context_app_state_round_trip() -> None:
    ctx = ToolUseContext.bare()
    ctx.set_app_state("k", "v")
    assert ctx.get_app_state("k") == "v"
    assert ctx.get_app_state("missing", default="d") == "d"


def test_context_session_id_unique_when_unset() -> None:
    a = ToolUseContext.bare()
    b = ToolUseContext.bare()
    assert a.session_id != b.session_id


def test_fork_inherits_app_state_but_independent() -> None:
    parent = ToolUseContext.bare()
    parent.set_app_state("k", "v")
    child = parent.fork(agent_id="child-1")
    assert child.get_app_state("k") == "v"
    child.set_app_state("k", "v2")
    assert parent.get_app_state("k") == "v"
    assert child.session_id == parent.session_id
    assert child.agent_id == "child-1"


def test_fork_shares_abort_event() -> None:
    parent = ToolUseContext.bare()
    child = parent.fork(agent_id="child-1")
    parent.abort_event.set()
    assert child.abort_event.is_set()
