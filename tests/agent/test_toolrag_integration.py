# tests/agent/test_toolrag_integration.py
"""Agent.tools filters via ToolSelector when one is set."""
from __future__ import annotations

from yuki import Agent
from yuki.agent.toolrag import ToolSelector
from yuki.memory.embeddings import StubEmbedder
from yuki.providers.stub.llm import ChatStub


def test_tools_unfiltered_by_default() -> None:
    agent = Agent(llm=ChatStub(), log_to_console=False, auto_minimize=False)
    assert len(agent.tools) >= 14


def test_tools_filtered_when_selector_set() -> None:
    agent = Agent(llm=ChatStub(), log_to_console=False, auto_minimize=False)
    agent.tool_selector = ToolSelector(
        agent.registry.get_tools(), embedder=StubEmbedder(dim=32), top_k=2
    )
    agent.state.task = "open calculator"
    filtered = agent.tools
    assert len(filtered) < len(agent.registry.get_tools())
    assert any(t.name == "done_tool" for t in filtered)
