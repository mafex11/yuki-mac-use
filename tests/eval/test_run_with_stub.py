# tests/eval/test_run_with_stub.py
"""run_case scores a single case against a stubbed LLM."""
from __future__ import annotations

from yuki.eval.cases import EvalCase, ExpectedStep
from yuki.eval.run import run_case
from yuki.providers.events import LLMEvent, LLMEventType, ToolCall
from yuki.providers.stub.llm import ChatStub


def _stub_emitting(tool: str, args: dict) -> ChatStub:
    ev = LLMEvent(
        type=LLMEventType.TOOL_CALL,
        tool_call=ToolCall(id="x", name=tool, params=args),
    )
    return ChatStub(events=[ev])


def test_run_case_scores_correct_first_tool() -> None:
    case = EvalCase(
        task="open calculator",
        expected_plan=[ExpectedStep("app_tool", {"name": r"calc"}),
                       ExpectedStep("done_tool")],
    )
    stub = _stub_emitting("app_tool", {"thought": "t", "name": "Calculator"})
    result = run_case(case, stub)
    assert result["toolset_score"] == 1.0
    assert result["first_tool"] == "app_tool"


def test_run_case_wrong_tool_scores_zero() -> None:
    case = EvalCase(
        task="open calculator",
        expected_plan=[ExpectedStep("app_tool", {"name": r"calc"}),
                       ExpectedStep("done_tool")],
    )
    stub = _stub_emitting("done_tool", {"thought": "t", "answer": "hi"})
    result = run_case(case, stub)
    assert result["toolset_score"] == 0.0
