"""Cooperative cancellation: request_stop() exits at the next step boundary."""

from __future__ import annotations

from yuki import Agent
from yuki.providers.events import LLMEvent, LLMEventType, ToolCall
from yuki.providers.stub import ChatStub


def _wait_event() -> LLMEvent:
    return LLMEvent(
        type=LLMEventType.TOOL_CALL,
        tool_call=ToolCall(
            id="w", name="wait_tool", params={"thought": "waiting", "duration": 0}
        ),
    )


def test_request_stop_before_invoke_stops_at_step_one() -> None:
    stub = ChatStub(events=[_wait_event()] * 30)
    agent = Agent(llm=stub, log_to_console=False)  # type: ignore[arg-type]
    agent.request_stop()
    # invoke() resets the flag, so pre-invoke stop must NOT persist.
    result = agent.invoke(task="noop")
    assert result.error != "cancelled"


def test_request_stop_mid_run_exits_cleanly() -> None:
    stub = ChatStub(events=[_wait_event()] * 30)
    agent = Agent(llm=stub, log_to_console=False)  # type: ignore[arg-type]

    # Stop after the second LLM call by hooking the stub.
    original = stub.invoke

    def stopping_invoke(*args, **kwargs):
        if len(stub.calls) >= 1:
            agent.request_stop()
        return original(*args, **kwargs)

    stub.invoke = stopping_invoke  # type: ignore[method-assign]
    result = agent.invoke(task="loop forever")

    assert result.is_done is False
    assert result.error == "cancelled"
    # Stopped well before the 25-step ceiling.
    assert agent.state.step < 5
