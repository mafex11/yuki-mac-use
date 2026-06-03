"""Fine-tuned Yuki models are served through Ollama's NATIVE tools= API — the
same path as every other model. They were retrained on the base model's native
tool-call template ({"name":..,"parameters":..}), so no custom dialect exists.

Regression guard: an earlier version trained a custom {"tool","args"} dialect
and special-cased yuki-* in the provider. That fought the 1B's pretrained prior
and degenerated at inference. These tests pin the native-path contract.
"""

from __future__ import annotations

from yuki.providers.ollama.llm import ChatOllama


def test_no_yuki_dialect_methods_remain() -> None:
    """The custom dialect was deleted; serving is uniform across models."""
    llm = ChatOllama(model="yuki-1b")
    for gone in ("_is_yuki_tuned", "_yuki_system_prompt",
                 "_parse_yuki_toolcall", "_yuki_params"):
        assert not hasattr(llm, gone), f"{gone} should have been removed"


def test_yuki_tools_use_native_function_schema() -> None:
    """yuki-* tools are converted to Ollama's native function schema (type=
    function) — the same shape they were trained on, no special-casing."""
    from yuki.agent.tools import BUILTIN_TOOLS

    llm = ChatOllama(model="yuki-1b")
    app_tool = next(t for t in BUILTIN_TOOLS if t.name == "app_tool")
    converted = llm._convert_tools([app_tool])
    assert converted[0]["type"] == "function"
    assert converted[0]["function"]["name"] == "app_tool"
