# tests/eval/test_score.py
"""score_plan grades an emitted plan against an EvalCase."""
from __future__ import annotations

from yuki.eval.cases import EvalCase, ExpectedStep
from yuki.eval.score import score_plan


def _case() -> EvalCase:
    return EvalCase(
        task="open calculator and type 5+5",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"calc"}),
            ExpectedStep("type_tool", {"text": r"5\+5"}),
            ExpectedStep("done_tool"),
        ],
    )


def test_perfect_plan_scores_one() -> None:
    emitted = [
        {"tool": "app_tool", "args": {"name": "Calculator"}},
        {"tool": "type_tool", "args": {"text": "5+5"}},
        {"tool": "done_tool", "args": {"answer": "done"}},
    ]
    r = score_plan(_case(), emitted)
    assert r["graph_score"] == 1.0
    assert r["toolset_score"] == 1.0


def test_wrong_order_fails_graph_passes_toolset() -> None:
    emitted = [
        {"tool": "type_tool", "args": {"text": "5+5"}},
        {"tool": "app_tool", "args": {"name": "Calculator"}},
        {"tool": "done_tool", "args": {}},
    ]
    r = score_plan(_case(), emitted)
    assert r["graph_score"] == 0.0
    assert r["toolset_score"] == 1.0  # same set, wrong order


def test_arg_mismatch_fails_graph() -> None:
    emitted = [
        {"tool": "app_tool", "args": {"name": "Safari"}},  # wrong app
        {"tool": "type_tool", "args": {"text": "5+5"}},
        {"tool": "done_tool", "args": {}},
    ]
    assert score_plan(_case(), emitted)["graph_score"] == 0.0


def test_reactive_grades_first_step_only() -> None:
    case = EvalCase(
        task="click submit",
        expected_plan=[ExpectedStep("click_tool"), ExpectedStep("done_tool")],
        reactive=True,
    )
    emitted = [{"tool": "click_tool", "args": {"loc": [1, 2]}}]
    assert score_plan(case, emitted)["graph_score"] == 1.0


def test_empty_emitted_scores_zero() -> None:
    assert score_plan(_case(), [])["graph_score"] == 0.0
    assert score_plan(_case(), [])["toolset_score"] == 0.0


def test_missing_tool_key_not_treated_as_tool() -> None:
    # Expected single tool; emitted has the right tool + a junk step with no tool key.
    case = EvalCase(task="x", expected_plan=[ExpectedStep("done_tool")])
    emitted = [{"tool": "done_tool", "args": {}}, {"args": {}}]
    r = score_plan(case, emitted)
    # With the junk step dropped, toolset is exactly {done_tool} == expected.
    assert r["toolset_score"] == 1.0
