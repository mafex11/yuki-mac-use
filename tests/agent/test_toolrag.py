# tests/agent/test_toolrag.py
"""ToolSelector picks task-relevant tools + always-include core."""
from __future__ import annotations

from yuki.agent.toolrag import ToolSelector
from yuki.memory.embeddings import StubEmbedder
from yuki.tools import Tool


def _tools() -> list[Tool]:
    def mk(name: str, desc: str) -> Tool:
        return Tool(name=name, description=desc)
    return [
        mk("app_tool", "Open or switch to a macOS application by name"),
        mk("type_tool", "Type text into a focused input field"),
        mk("click_tool", "Click a UI element at coordinates"),
        mk("shell_tool", "Run a shell command or AppleScript"),
        mk("done_tool", "Finish and answer the user"),
        mk("scroll_tool", "Scroll the screen up or down"),
        mk("shortcut_tool", "Press a keyboard shortcut"),
    ]


def test_core_tools_always_included() -> None:
    sel = ToolSelector(_tools(), embedder=StubEmbedder(dim=32), top_k=2)
    chosen = {t.name for t in sel.select("open calculator")}
    assert {"done_tool", "app_tool", "shell_tool"} <= chosen


def test_select_returns_subset_not_all() -> None:
    tools = _tools()
    sel = ToolSelector(tools, embedder=StubEmbedder(dim=32), top_k=2)
    chosen = sel.select("type some text")
    assert len(chosen) < len(tools)


def test_select_is_capped_by_k_plus_core() -> None:
    tools = _tools()
    sel = ToolSelector(tools, embedder=StubEmbedder(dim=32), top_k=2)
    chosen = sel.select("anything")
    assert len(chosen) <= 2 + 3


def test_empty_task_returns_core_only() -> None:
    sel = ToolSelector(_tools(), embedder=StubEmbedder(dim=32), top_k=2)
    chosen = {t.name for t in sel.select("")}
    assert {"done_tool", "app_tool", "shell_tool"} <= chosen
