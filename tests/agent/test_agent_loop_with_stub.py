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


def test_malformed_done_tool_is_not_premature_success() -> None:
    """A done_tool missing its required `answer` must NOT terminate as a
    success with empty content. It's a validation failure: the loop rejects
    it and retries. (Regression: small models emitting a bare done_tool used
    to exit with 0 steps / empty reply / outcome=success — doing nothing.)
    """
    malformed = LLMEvent(
        type=LLMEventType.TOOL_CALL,
        tool_call=ToolCall(
            id="bad",
            name="done_tool",
            params={},  # missing required `answer` (and `thought`)
        ),
    )
    # First call: malformed done (rejected). The stub's queue then empties,
    # so the next call returns the default VALID done → legitimate finish.
    stub = ChatStub(events=[malformed])
    agent = _agent(stub)

    result = agent.invoke(task="open calculator")

    # It must have re-invoked the model (not accepted the malformed done).
    assert len(stub.calls) >= 2
    # And when it does finish, it carries the real answer — never the empty
    # string the malformed call would have produced.
    assert result.is_done is True
    assert result.content == "stub answer"
    assert result.content != ""
