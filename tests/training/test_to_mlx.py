"""Record -> MLX chat-format conversion."""

from __future__ import annotations

import json

from training.to_mlx import record_to_messages


def _rec() -> dict:
    return {
        "task": "open calculator",
        "screen": "",
        "tool": "app_tool",
        "args": {"thought": "Launch Calculator.", "mode": "launch", "name": "Calculator"},
        "present_tools": ["type_tool", "app_tool", "done_tool", "desktop_tool"],
    }


def test_produces_three_role_messages() -> None:
    msgs = record_to_messages(_rec())["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]


def test_system_lists_present_tools() -> None:
    sys = record_to_messages(_rec())["messages"][0]["content"]
    for tool in ("app_tool", "type_tool", "done_tool", "desktop_tool"):
        assert tool in sys


def test_assistant_is_parseable_target_json() -> None:
    asst = record_to_messages(_rec())["messages"][2]["content"]
    obj = json.loads(asst)
    assert obj["tool"] == "app_tool"
    assert obj["args"]["name"] == "Calculator"
    assert "thought" in obj["args"]


def test_reactive_row_includes_screen_in_user() -> None:
    rec = _rec()
    rec["screen"] = "# id|window|...\n0|Form|AXButton|submit_button|Submit|(1,2)|-|{}"
    user = record_to_messages(rec)["messages"][1]["content"]
    assert "Screen State" in user and "Submit" in user


def test_falls_back_when_no_present_tools() -> None:
    rec = _rec()
    del rec["present_tools"]
    sys = record_to_messages(rec)["messages"][0]["content"]
    assert "app_tool" in sys and "done_tool" in sys
