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
        mk("wait_tool", "Wait for the UI to settle"),
        mk("memory_tool", "Persist data across steps"),
        mk("spotify_tool", "Control Spotify playback"),
    ]

# The GUI primitives every multi-step task needs — must survive Tool RAG.
_GUI_PRIMITIVES = {
    "done_tool", "app_tool", "type_tool", "click_tool",
    "shortcut_tool", "wait_tool", "shell_tool",
}


def test_core_tools_always_included() -> None:
    sel = ToolSelector(_tools(), embedder=StubEmbedder(dim=32), top_k=2)
    chosen = {t.name for t in sel.select("open calculator")}
    assert chosen >= _GUI_PRIMITIVES


def test_type_and_click_always_present() -> None:
    # Regression: a GUI goal whose embedding doesn't rank type/click top-K must
    # STILL get them — without type_tool the agent can open an app but never
    # type, so it stalls. (Real failure on qwen2.5:7b + "MrBeast on YouTube".)
    sel = ToolSelector(_tools(), embedder=StubEmbedder(dim=32), top_k=2)
    chosen = {t.name for t in sel.select("open spotify")}
    assert "type_tool" in chosen
    assert "click_tool" in chosen


def test_select_returns_subset_not_all() -> None:
    tools = _tools()
    sel = ToolSelector(tools, embedder=StubEmbedder(dim=32), top_k=2)
    chosen = sel.select("manage my virtual desktops")
    assert len(chosen) < len(tools)


def test_select_is_capped_by_k_plus_core() -> None:
    tools = _tools()
    sel = ToolSelector(tools, embedder=StubEmbedder(dim=32), top_k=2)
    chosen = sel.select("anything")
    assert len(chosen) <= 2 + len(_GUI_PRIMITIVES)


def test_empty_task_returns_core_only() -> None:
    sel = ToolSelector(_tools(), embedder=StubEmbedder(dim=32), top_k=2)
    chosen = {t.name for t in sel.select("")}
    assert chosen >= _GUI_PRIMITIVES
