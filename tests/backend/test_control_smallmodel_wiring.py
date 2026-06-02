# tests/backend/test_control_smallmodel_wiring.py
"""_configure_agent_for_model attaches Tool RAG + lean AX for Ollama only."""
from __future__ import annotations

from yuki import Agent
from yuki.backend.routers.chat import _configure_agent_for_model
from yuki.providers.stub.llm import ChatStub


class _Ollamaish(ChatStub):
    @property
    def provider(self) -> str:
        return "ollama"


def test_ollama_gets_selector_and_lean() -> None:
    agent = Agent(llm=_Ollamaish(), log_to_console=False, auto_minimize=False)
    _configure_agent_for_model(agent, _Ollamaish())
    assert agent.tool_selector is not None
    assert agent.ax_verbosity == "lean"


def test_cloud_model_untouched() -> None:
    agent = Agent(llm=ChatStub(), log_to_console=False, auto_minimize=False)
    _configure_agent_for_model(agent, ChatStub())  # provider == "stub"
    assert agent.tool_selector is None
    assert agent.ax_verbosity == "full"
