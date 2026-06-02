"""The eval case suite loads and is well-formed."""
from __future__ import annotations

from yuki.eval.cases import CASES, EvalCase, ExpectedStep


def test_cases_nonempty_and_typed() -> None:
    assert len(CASES) >= 10
    for c in CASES:
        assert isinstance(c, EvalCase)
        assert c.task.strip()
        assert len(c.expected_plan) >= 1
        for step in c.expected_plan:
            assert isinstance(step, ExpectedStep)
            assert step.tool  # non-empty tool name


def test_every_plan_ends_with_done_for_action_tasks() -> None:
    for c in CASES:
        assert c.expected_plan[-1].tool == "done_tool", c.task


def test_tool_names_are_real() -> None:
    from yuki.agent.tools import BUILTIN_TOOLS
    valid = {t.name for t in BUILTIN_TOOLS}
    for c in CASES:
        for step in c.expected_plan:
            assert step.tool in valid, f"{c.task}: unknown tool {step.tool}"
