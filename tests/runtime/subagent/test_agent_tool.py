"""agent_tool: registered, dispatches subagent."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from typing import Any

import pytest

from yuki.runtime.subagent import agent_tool as agent_mod
from yuki.runtime.subagent.agent_tool import agent_tool
from yuki.tools.native.registry import REGISTRY, DangerLevel


def test_agent_tool_registered() -> None:
    importlib.reload(agent_mod)
    assert "agent" in REGISTRY
    assert REGISTRY["agent"].danger == DangerLevel.READ_ONLY


async def test_agent_tool_runs_subagent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_runner(
        *,
        definition: Any,
        prompt: str,
        llm: Any,
        parent_ctx: Any = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "result", "agent_id": "x", "content": "subagent answer"}

    monkeypatch.setattr(
        "yuki.runtime.subagent.agent_tool.run_subagent", fake_runner
    )
    out = await agent_tool(
        agent_name="explore",
        prompt="find all TODOs",
        system_prompt="You are read-only.",
    )
    assert out["content"] == "subagent answer"
