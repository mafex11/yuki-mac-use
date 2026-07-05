"""Record -> MLX native-tool-call chat-format conversion.

Rows are emitted in mlx-lm's tools-aware shape: messages = [system, user,
assistant(tool_calls)] + a `tools` schema list. mlx-lm renders this through the
base model's NATIVE chat template, so training output == serving output.
"""

from __future__ import annotations

from training.to_mlx import record_to_messages


def _rec() -> dict:
    return {
        "task": "open calculator",
        "screen": "",
        "tool": "app_tool",
        "args": {"thought": "Launch Calculator.", "mode": "launch", "name": "Calculator"},
        "present_tools": ["type_tool", "app_tool", "done_tool", "scroll_tool"],
    }


def test_produces_three_role_messages() -> None:
    msgs = record_to_messages(_rec())["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]


def test_tools_field_lists_present_tools_as_function_schemas() -> None:
    row = record_to_messages(_rec())
    names = {t["function"]["name"] for t in row["tools"]}
    # present_tools that exist in the real registry are included as schemas.
    assert "app_tool" in names and "done_tool" in names
    assert all(t["type"] == "function" for t in row["tools"])


def test_assistant_emits_native_tool_call() -> None:
    asst = record_to_messages(_rec())["messages"][2]
    # Native shape: empty content + a tool_calls entry the template renders.
    assert asst["content"] == ""
    call = asst["tool_calls"][0]["function"]
    assert call["name"] == "app_tool"
    assert call["arguments"]["name"] == "Calculator"
    assert "thought" in call["arguments"]


def test_reactive_row_includes_screen_in_user() -> None:
    rec = _rec()
    rec["screen"] = "# id|window|...\n0|Form|AXButton|submit_button|Submit|(1,2)|-|{}"
    user = record_to_messages(rec)["messages"][1]["content"]
    # User message must match the eval/serve format: "Task: ..." + "Screen state:"
    assert user.startswith("Task: ")
    assert "Screen state:" in user and "Submit" in user


def test_falls_back_when_no_present_tools() -> None:
    rec = _rec()
    del rec["present_tools"]
    names = {t["function"]["name"] for t in record_to_messages(rec)["tools"]}
    assert "app_tool" in names and "done_tool" in names
