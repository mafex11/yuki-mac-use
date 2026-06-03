"""Fine-tuned Yuki models use the trained 'dialect' (text tools + JSON call)
instead of Ollama's native tools= API."""

from __future__ import annotations

from yuki.messages import HumanMessage, SystemMessage
from yuki.providers.ollama.llm import ChatOllama
from yuki.providers.events import LLMEventType
from yuki.tools import Tool


def _tools() -> list[Tool]:
    return [
        Tool(name="app_tool", description="Open or switch to a macOS application."),
        Tool(name="done_tool", description="Answer the user or report completion."),
    ]


def test_detection_only_for_yuki_models() -> None:
    assert ChatOllama(model="yuki-1b")._is_yuki_tuned() is True
    assert ChatOllama(model="yuki-3b")._is_yuki_tuned() is True
    assert ChatOllama(model="qwen2.5:7b")._is_yuki_tuned() is False
    assert ChatOllama(model="llama3.2:1b")._is_yuki_tuned() is False


def test_dialect_params_have_no_native_tools_and_text_system() -> None:
    llm = ChatOllama(model="yuki-1b")
    params = llm._yuki_params(
        [SystemMessage(content="ignored"), HumanMessage(content="open calculator")],
        _tools(),
    )
    assert "tools" not in params  # native tools= NOT used
    sys = params["messages"][0]
    assert sys["role"] == "system"
    assert "app_tool" in sys["content"] and "done_tool" in sys["content"]
    # original system message replaced by the trained-format one
    assert "ignored" not in sys["content"]


def test_parse_yuki_toolcall_extracts_json() -> None:
    llm = ChatOllama(model="yuki-1b")
    resp = {"message": {"content":
            'sure: {"tool": "app_tool", "args": {"thought": "t", "name": "Calculator"}}'}}
    ev = llm._parse_yuki_toolcall(resp)
    assert ev.type == LLMEventType.TOOL_CALL
    assert ev.tool_call.name == "app_tool"
    assert ev.tool_call.params["name"] == "Calculator"


def test_parse_yuki_toolcall_falls_back_to_text() -> None:
    llm = ChatOllama(model="yuki-1b")
    ev = llm._parse_yuki_toolcall({"message": {"content": "no json here"}})
    assert ev.type == LLMEventType.TEXT
