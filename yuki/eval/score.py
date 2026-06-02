# yuki/eval/score.py
"""Grade an emitted tool-call plan against an EvalCase.

graph_score (strict): right tools, right order, args satisfy the matchers.
toolset_score (lenient): right set of tools, order-independent.
For reactive cases, only the first step is considered.
"""
from __future__ import annotations

import re
from typing import Any, TypedDict

from yuki.eval.cases import EvalCase, ExpectedStep


class ScoreResult(TypedDict):
    graph_score: float
    toolset_score: float


def _args_match(expected: ExpectedStep, emitted_args: dict[str, Any]) -> bool:
    for key, pattern in expected.args_matcher.items():
        val = emitted_args.get(key)
        if val is None:
            return False
        if re.search(pattern, str(val), re.IGNORECASE) is None:
            return False
    return True


def _step_match(expected: ExpectedStep, emitted: dict[str, Any]) -> bool:
    return (
        emitted.get("tool") == expected.tool
        and _args_match(expected, emitted.get("args") or {})
    )


def score_plan(case: EvalCase, emitted: list[dict[str, Any]]) -> ScoreResult:
    expected = case.expected_plan
    if case.reactive:
        ok = bool(emitted) and _step_match(expected[0], emitted[0])
        return {"graph_score": 1.0 if ok else 0.0,
                "toolset_score": 1.0 if ok else 0.0}

    if not emitted:
        return {"graph_score": 0.0, "toolset_score": 0.0}

    graph_ok = len(emitted) == len(expected) and all(
        _step_match(exp, emitted[i]) for i, exp in enumerate(expected)
    )

    expected_tools = sorted(s.tool for s in expected)
    emitted_tools = sorted(str(e.get("tool")) for e in emitted)
    toolset_ok = expected_tools == emitted_tools

    return {"graph_score": 1.0 if graph_ok else 0.0,
            "toolset_score": 1.0 if toolset_ok else 0.0}
