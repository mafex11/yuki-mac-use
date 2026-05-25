"""Runtime tests: scripted-LLM fixture."""

from __future__ import annotations

from typing import Any

import pytest


class _FakeLLM:
    def __init__(self) -> None:
        self.responses: list[list[dict[str, Any]]] = []
        self.calls: list[dict[str, Any]] = []

    def queue(self, blocks: list[dict[str, Any]]) -> None:
        self.responses.append(blocks)

    async def invoke(self, messages: Any, **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, **kwargs})

        class R:
            def __init__(self, blocks: list[dict[str, Any]]) -> None:
                self.content = blocks
                self.stop_reason = "end_turn"
                self.usage = type(
                    "U",
                    (),
                    {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    },
                )()
                self.model = "claude-sonnet-4-6"

        return R(self.responses.pop(0) if self.responses else [])


@pytest.fixture
def fake_llm() -> _FakeLLM:
    return _FakeLLM()
