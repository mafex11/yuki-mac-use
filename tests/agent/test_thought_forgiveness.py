# tests/agent/test_thought_forgiveness.py
"""Registry forgives a missing `thought` preamble (small models drop it)."""
from __future__ import annotations

from yuki.agent.registry.service import Registry
from yuki.agent.tools import BUILTIN_TOOLS


def _registry() -> Registry:
    return Registry(BUILTIN_TOOLS)


def test_done_tool_missing_thought_is_forgiven() -> None:
    reg = _registry()
    # done_tool with a valid answer but NO thought — small-model pattern.
    result = reg.execute(
        tool_name="done_tool",
        tool_params={"answer": "The calculator is now open.", "evaluate": "success"},
        desktop=None,
    )
    assert result.is_success, f"expected forgiveness, got: {result.error}"


def test_done_tool_missing_both_thought_and_answer_still_fails() -> None:
    reg = _registry()
    # Missing answer (the functionally-required field) must NOT be forgiven.
    result = reg.execute(
        tool_name="done_tool",
        tool_params={"evaluate": "success"},
        desktop=None,
    )
    assert not result.is_success
