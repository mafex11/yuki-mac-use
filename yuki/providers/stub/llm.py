"""ChatStub — deterministic LLM provider for tests.

Returns a scripted sequence of LLMEvents. Each invoke/ainvoke pops the
next event off the queue. By default emits a single `done_tool` call
that terminates the agent loop in one step.

Used by tests/agent/test_agent_loop_with_stub.py and similar — never
shipped to users.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Iterator

from pydantic import BaseModel

from yuki.messages import BaseMessage
from yuki.providers.events import LLMEvent, LLMEventType, LLMStreamEvent, ToolCall
from yuki.providers.views import Metadata, TokenUsage
from yuki.tools import Tool


def _default_done_event() -> LLMEvent:
    return LLMEvent(
        type=LLMEventType.TOOL_CALL,
        tool_call=ToolCall(
            id="stub-call-1",
            name="done_tool",
            params={"thought": "stub thinking", "answer": "stub answer"},
        ),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


class ChatStub:
    """Scripted LLM provider for tests. Implements BaseChatLLM duck-typing.

    Mutable default args mirror the BaseChatLLM Protocol from
    yuki/providers/base.py — switching to None would break Protocol matching.
    """

    def __init__(
        self,
        events: list[LLMEvent] | None = None,
        model_name: str = "stub-model",
    ) -> None:
        self._queue: list[LLMEvent] = list(events) if events else [_default_done_event()]
        self._model_name = model_name
        self.calls: list[list[BaseMessage]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider(self) -> str:
        return "stub"

    def _next(self) -> LLMEvent:
        if not self._queue:
            # Default to done_tool so loops always terminate even past the script.
            return _default_done_event()
        return self._queue.pop(0)

    def invoke(
        self,
        messages: list[BaseMessage] | Iterable[BaseMessage],
        tools: list[Tool] = [],  # noqa: B006 — protocol compatibility
        structured_output: BaseModel | None = None,
        json_mode: bool = False,
    ) -> LLMEvent:
        self.calls.append(list(messages))
        return self._next()

    async def ainvoke(
        self,
        messages: list[BaseMessage] | Iterable[BaseMessage],
        tools: list[Tool] = [],  # noqa: B006 — protocol compatibility
        structured_output: BaseModel | None = None,
        json_mode: bool = False,
    ) -> LLMEvent:
        return self.invoke(messages, tools, structured_output, json_mode)

    def stream(
        self,
        messages: list[BaseMessage] | Iterable[BaseMessage],
        tools: list[Tool] = [],  # noqa: B006 — protocol compatibility
        structured_output: BaseModel | None = None,
        json_mode: bool = False,
    ) -> Iterator[LLMStreamEvent]:
        # Stub doesn't implement streaming — agent.service.py uses invoke/ainvoke.
        raise NotImplementedError("ChatStub does not implement stream()")

    async def astream(
        self,
        messages: list[BaseMessage] | Iterable[BaseMessage],
        tools: list[Tool] = [],  # noqa: B006 — protocol compatibility
        structured_output: BaseModel | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[LLMStreamEvent]:
        raise NotImplementedError("ChatStub does not implement astream()")
        yield  # pragma: no cover — required to make this an async generator

    def get_metadata(self) -> Metadata:
        return Metadata(name=self._model_name, context_window=200_000, owned_by="stub")

    def sanitize_schema(self, tool_schema: dict) -> dict:
        """Inherited Protocol behavior — pass-through that mimics the base impl."""
        params = tool_schema.get("parameters", {})
        return {
            "name": tool_schema.get("name"),
            "description": tool_schema.get("description"),
            "parameters": {
                "type": "object",
                "properties": params.get("properties", {}),
                "required": params.get("required", []),
            },
        }
