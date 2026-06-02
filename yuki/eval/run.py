# yuki/eval/run.py
"""Run the plan-correctness eval suite against an LLM.

Pre-planner (Phase A1): grade the model's FIRST tool call for the task,
scoring it against the FIRST expected step (treated as a reactive/first-step
match). Post-planner (Phase A2) will add full-plan grading.

CLI:  uv run python -m yuki.eval.run --model llama3.2:1b --mode flash
"""
from __future__ import annotations

import argparse
from typing import Any

from yuki.eval.cases import CASES, EvalCase, load_fixture
from yuki.eval.score import score_plan


def _extract_first_tool_call(
    llm: Any,
    case: EvalCase,
    tools: list[Any],
) -> list[dict[str, Any]]:
    """Ask the LLM for the task and return [{tool, args}] from its tool call.

    Args:
        llm: The language model to query.
        case: The evaluation case containing task and context.
        tools: The tool list to pass to the model (already filtered by caller).
    """
    from yuki.messages import HumanMessage, SystemMessage

    sys = SystemMessage(content=(
        "You are a macOS control agent. Choose the single best tool to begin "
        "the user's task. Always emit a tool call."
    ))
    parts = [f"Task: {case.task}"]
    if case.ax_fixture:
        parts.append("Screen state:\n" + load_fixture(case.ax_fixture))
    user = HumanMessage(content="\n\n".join(parts))
    event = llm.invoke(messages=[sys, user], tools=tools)
    tc = getattr(event, "tool_call", None)
    if tc is None:
        return []
    return [{"tool": tc.name, "args": dict(tc.params or {})}]


def run_case(case: EvalCase, llm: Any, selector: Any = None) -> dict[str, Any]:
    """Run a single eval case against an LLM.

    Args:
        case: The evaluation case to run.
        llm: The language model to test.
        selector: Optional ToolSelector to apply Tool RAG. If None, uses all BUILTIN_TOOLS.
    """
    from yuki.agent.tools import BUILTIN_TOOLS

    if selector is not None:
        tools = selector.select(case.task)
    else:
        tools = BUILTIN_TOOLS

    emitted = _extract_first_tool_call(llm, case, tools)
    # Pre-planner: grade the first emitted tool against the first expected step.
    first_step_case = EvalCase(
        task=case.task,
        expected_plan=[case.expected_plan[0]],
        reactive=True,
    )
    scores = score_plan(first_step_case, emitted)
    return {
        "task": case.task,
        "first_tool": emitted[0]["tool"] if emitted else None,
        **scores,
    }


def run_suite(
    llm: Any,
    cases: list[EvalCase] = CASES,
    selector: Any = None,
) -> dict[str, Any]:
    """Run the full eval suite against an LLM.

    Args:
        llm: The language model to test.
        cases: The list of evaluation cases to run.
        selector: Optional ToolSelector to apply Tool RAG to all cases.
    """
    per_case = [run_case(c, llm, selector) for c in cases]
    n = len(per_case) or 1
    return {
        "graph_score": sum(r["graph_score"] for r in per_case) / n,
        "toolset_score": sum(r["toolset_score"] for r in per_case) / n,
        "per_case": per_case,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Ollama model name")
    parser.add_argument("--mode", default="flash", choices=["flash", "normal"])
    parser.add_argument(
        "--no-toolrag",
        action="store_true",
        help="Disable Tool RAG (pass all 16 tools to the model)",
    )
    args = parser.parse_args()

    if args.model:
        from yuki.providers.ollama.llm import ChatOllama
        llm = ChatOllama(model=args.model)
    else:
        from yuki.providers.factory import make_llm
        llm = make_llm()

    selector = None
    if args.model and not args.no_toolrag:
        # Apply Tool RAG for Ollama models: filter to ~5 task-relevant tools.
        from yuki.agent.tools import BUILTIN_TOOLS
        from yuki.agent.toolrag import ToolSelector
        from yuki.memory.embeddings import OllamaEmbedder

        selector = ToolSelector(BUILTIN_TOOLS, OllamaEmbedder(), top_k=5)

    result = run_suite(llm, selector=selector)
    toolrag_status = "toolrag=on" if selector else "toolrag=off"
    print(f"model={args.model or 'default'} mode={args.mode} {toolrag_status}")
    print(f"  graph_score:   {result['graph_score']:.2f}")
    print(f"  toolset_score: {result['toolset_score']:.2f}")
    for r in result["per_case"]:
        mark = "OK" if r["toolset_score"] == 1.0 else "XX"
        print(f"  {mark} {r['task'][:48]:48} first={r['first_tool']}")


if __name__ == "__main__":
    main()
