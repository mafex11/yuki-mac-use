"""Headless autonomy demo — does Yuki DECOMPOSE a goal, or act like a robot?

Builds the REAL system prompt + tools and asks the configured/!specified model
the one-line goal "open a MrBeast video on YouTube in Chrome" with a synthetic
empty-desktop state. We do NOT run the agent loop (that would drive the real
Mac); we inspect the model's FIRST tool call:

  - robot behavior  -> a single literal action, empty/absent `plan`
  - intelligent     -> first action is app_tool(Chrome) AND `plan` lists the
                       remaining steps (new tab, navigate, search, click, done)

Usage:
    uv run python scripts/demo_autonomy.py --provider ollama --model qwen2.5:7b
    uv run python scripts/demo_autonomy.py --provider anthropic   # needs key
"""

from __future__ import annotations

import argparse
import json

from yuki.agent.desktop.views import Browser
from yuki.agent.prompt.service import Prompt
from yuki.agent.tools import BUILTIN_TOOLS
from yuki.messages import HumanMessage
from yuki.providers.factory import agent_mode_for, make_llm

GOAL = "open a MrBeast video on YouTube in Chrome"

# A plausible "nothing open yet" desktop state, built with the REAL human.md
# template so the model sees exactly the framing the live agent sends.
def _empty_state_message(max_steps: int) -> str:
    from importlib.resources import files

    template = files("yuki.agent.prompt").joinpath("human.md").read_text(encoding="utf-8")
    return template.format(
        steps=0,
        max_steps=max_steps,
        loop_warning="",
        cursor_location="(640,400)",
        active_window="Finder (com.apple.finder) - Active",
        windows="(none)",
        interactive_elements=(
            "# id|window|control_type|canonical|name|coords|focused|metadata\n"
            "(no application windows open)"
        ),
        scrollable_elements="(none)",
        query="",  # query is delivered as its own TASK message below
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--goal", default=GOAL)
    args = ap.parse_args()

    llm = make_llm(provider=args.provider, model=args.model)
    mode = agent_mode_for(llm)
    print(f"\nmodel={llm.model_name} provider={llm.provider} prompt_mode={mode}")
    print(f"thinking_budget={getattr(llm, 'thinking_budget', None)}")
    print(f"goal: {args.goal!r}\n" + "=" * 70)

    # Build the SAME system prompt the live agent uses.
    from yuki.agent.desktop.service import Desktop

    desktop = Desktop(use_vision=False, use_annotation=False, use_accessibility=True)
    system = Prompt.system(
        mode=mode, desktop=desktop, browser=Browser.CHROME,
        max_steps=25, instructions=[],
    )

    from yuki.messages import SystemMessage

    # Replicate the LIVE control path: for Ollama, the backend applies Tool RAG
    # (top-K relevant tools + core) instead of all 16. Dumping all 16 tools is a
    # KNOWN failure mode for local models (they emit no/garbage tool calls) — so
    # a fair test must use the same tool selection the real agent uses.
    tools = BUILTIN_TOOLS
    if llm.provider == "ollama":
        try:
            from yuki.agent.toolrag import ToolSelector
            from yuki.memory.embeddings import OllamaEmbedder

            selector = ToolSelector(list(BUILTIN_TOOLS), embedder=OllamaEmbedder())
            tools = selector.select(args.goal)
            print(f"[Tool RAG] {len(tools)}/{len(BUILTIN_TOOLS)} tools: "
                  f"{[t.name for t in tools]}")
        except Exception as e:
            print(f"[Tool RAG unavailable: {type(e).__name__}; using all tools]")

    # Mirror the live agent's message order: system, TASK, then desktop state.
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"TASK: {args.goal}"),
        HumanMessage(content=_empty_state_message(25)),
    ]

    event = llm.invoke(messages=messages, tools=tools)

    tc = getattr(event, "tool_call", None)
    thinking = getattr(getattr(event, "thinking", None), "content", None)

    if thinking:
        print(f"\n[THINKING]\n{thinking}\n")

    if tc is None:
        print("NO TOOL CALL — model returned text instead:")
        print(getattr(event, "content", "")[:500])
        print("\nVERDICT: robotic/failed (no action emitted)")
        return

    params = dict(tc.params or {})
    plan = str(params.get("plan", "")).strip()
    thought = str(params.get("thought", "")).strip()
    print(f"\n[FIRST TOOL CALL] {tc.name}")
    print(json.dumps(params, indent=2)[:800])

    # Goal-agnostic scoring: an intelligent first step has a real reasoning
    # `thought` and either a non-empty `plan` (multi-step goals) or a sensible
    # terminal answer (pure-question goals). We do NOT check for any specific
    # app or keyword — that would just re-encode one test case.
    plan_steps = [ln for ln in plan.splitlines() if ln.strip()]
    has_thought = len(thought) > 10
    has_plan = len(plan_steps) >= 2
    is_action = tc.name != "done_tool"

    print("\n" + "=" * 70)
    print(f"emitted a reasoning thought:  {has_thought}")
    print(f"laid out a multi-step plan:   {has_plan} ({len(plan_steps)} lines)")
    print(f"first step is an action:      {is_action} ({tc.name})")
    if has_thought and (has_plan or not is_action):
        print("\nVERDICT: ✅ reasoning + decomposition present")
    elif is_action and has_thought:
        print("\nVERDICT: ⚠️ acts with reasoning but thin/absent plan field")
    else:
        print("\nVERDICT: ❌ robotic — no reasoning/decomposition")


if __name__ == "__main__":
    main()
