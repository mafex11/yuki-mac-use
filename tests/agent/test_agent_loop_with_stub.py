"""Integration test: drive one full agent loop iteration with the stub LLM.

Proves Plan A vendoring + namespace rewrite + telemetry strip + stub provider
all hang together — the public API can run a complete invoke from outside.

Note: this DOES instantiate Desktop and WatchDog. Both work on a developer's
Mac without special permissions for the construction path; only when tools
actually drive the screen do permissions matter. The stub returns done_tool
on the first turn, so no real desktop interaction occurs.
"""

from __future__ import annotations

import pytest

from yuki import Agent
from yuki.providers.events import LLMEvent, LLMEventType, ToolCall
from yuki.providers.stub import ChatStub


def _agent(stub: ChatStub) -> Agent:
    # mypy's view of BaseChatLLM Protocol expects astream as a coroutine returning
    # an AsyncIterator (via @overload), while ChatStub uses the more natural
    # generator form. Structurally compatible at runtime; ignore here.
    return Agent(llm=stub, log_to_console=False, auto_minimize=False)  # type: ignore[arg-type]


def test_invoke_terminates_on_done_tool() -> None:
    stub = ChatStub()
    agent = _agent(stub)

    result = agent.invoke(task="say hello")

    assert result.is_done is True
    assert result.content == "stub answer"
    # The stub was called at least once.
    assert len(stub.calls) >= 1


def test_invoke_passes_messages_to_llm() -> None:
    stub = ChatStub()
    agent = _agent(stub)

    agent.invoke(task="trace me")

    # Each call should have received messages — exact shape varies, just confirm non-empty.
    assert all(len(call) > 0 for call in stub.calls)


def test_custom_answer_propagates_to_result() -> None:
    custom = LLMEvent(
        type=LLMEventType.TOOL_CALL,
        tool_call=ToolCall(
            id="x",
            name="done_tool",
            params={"thought": "ok", "answer": "custom answer 42"},
        ),
    )
    stub = ChatStub(events=[custom])
    agent = _agent(stub)

    result = agent.invoke(task="anything")

    assert result.content == "custom answer 42"


@pytest.mark.asyncio
async def test_ainvoke_also_terminates_on_done_tool() -> None:
    stub = ChatStub()
    agent = _agent(stub)

    result = await agent.ainvoke(task="say hello async")

    assert result.is_done is True
    assert result.content == "stub answer"
