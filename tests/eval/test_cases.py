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


def test_nonreactive_plans_end_with_done() -> None:
    # Reactive cases are graded on the FIRST step only (run.py), so they carry a
    # single expected step and need not include the terminal done_tool. Full
    # (non-reactive) plans should still end by reporting completion.
    for c in CASES:
        if not c.reactive:
            assert c.expected_plan[-1].tool == "done_tool", c.task


def test_reactive_cases_have_single_expected_step() -> None:
    # The harness only grades emitted[0] for reactive cases; extra expected
    # steps would be silently ignored, so keep them to one.
    for c in CASES:
        if c.reactive:
            assert len(c.expected_plan) == 1, c.task


def test_tool_names_are_real() -> None:
    from yuki.agent.tools import BUILTIN_TOOLS
    valid = {t.name for t in BUILTIN_TOOLS}
    for c in CASES:
        for step in c.expected_plan:
            assert step.tool in valid, f"{c.task}: unknown tool {step.tool}"


def test_load_fixture_returns_text() -> None:
    from yuki.eval.cases import load_fixture
    text = load_fixture("submit_button.txt")
    assert "submit" in text.lower()
    assert "|" in text  # pipe-delimited node rows


def test_missing_fixture_raises() -> None:
    import pytest
    from yuki.eval.cases import load_fixture
    with pytest.raises(FileNotFoundError):
        load_fixture("does_not_exist.txt")
