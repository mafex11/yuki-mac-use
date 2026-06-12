"""Full multi-step agent run on the MrBeast goal — observe decomposition safely.

Runs the REAL agent loop (real LLM, real system prompt, real Tool RAG, thinking
ON for cloud) but intercepts tool EXECUTION so nothing touches the real Mac.
Each action is logged and given a synthetic "success" + a scripted next screen,
so we can watch the agent decompose "open a MrBeast video on YouTube in Chrome"
across steps end-to-end.

    uv run python scripts/demo_full_run.py --provider anthropic
    uv run python scripts/demo_full_run.py --provider anthropic --real   # ACTUALLY drives the Mac

--real removes the interception and lets the agent control the screen for real.
Default is safe (simulated execution).
"""

from __future__ import annotations

import argparse

from yuki import Agent
from yuki.agent.desktop.views import Browser
from yuki.providers.factory import agent_mode_for, make_llm

GOAL = "open a MrBeast video on YouTube in Chrome"

# Scripted screens returned after each successful action, so the simulated loop
# advances through a believable Chrome→YouTube→play trajectory. Keyed by the
# count of actions executed so far.
_SCRIPTED_SCREENS = [
    # after action 1 (launch Chrome): a focused new-tab URL bar
    ("New Tab - Google Chrome (com.google.Chrome) - Active",
     "0|Chrome|AXTextField|url_bar|Address and search bar|(640,72)|YES|{\"value\":\"\"}"),
    # after action 2 (type youtube.com / open tab): YouTube home w/ search
    ("YouTube - Google Chrome (com.google.Chrome) - Active",
     "0|Chrome|AXTextField|search_field|Search|(700,90)|YES|{\"value\":\"\"}\n"
     "1|Chrome|AXLink|video_thumb|MrBeast - $1 vs $1,000,000 video|(360,320)|-|{}"),
    # after action 3 (search MrBeast): results with a MrBeast video
    ("MrBeast - YouTube - Google Chrome (com.google.Chrome) - Active",
     "0|Chrome|AXLink|video_thumb|MrBeast - I Survived 50 Hours|(360,300)|-|{}\n"
     "1|Chrome|AXLink|video_thumb|MrBeast - $1 vs $1,000,000|(360,520)|-|{}"),
    # after action 4 (click video): a playing video
    ("MrBeast video - YouTube - Google Chrome (com.google.Chrome) - Active",
     "0|Chrome|AXButton|button|Pause|(360,700)|-|{}"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--goal", default=GOAL)
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--real", action="store_true",
                    help="ACTUALLY drive the Mac (default: simulate execution)")
    args = ap.parse_args()

    llm = make_llm(provider=args.provider, model=args.model)
    mode = agent_mode_for(llm)
    print(f"\nmodel={llm.model_name} provider={llm.provider} prompt_mode={mode} "
          f"thinking={getattr(llm, 'thinking_budget', None)}")
    print(f"goal: {args.goal!r}   mode={'REAL Mac control' if args.real else 'SIMULATED (safe)'}")
    print("=" * 72)

    agent = Agent(llm=llm, mode=mode, max_steps=args.max_steps,
                  log_to_console=False, auto_minimize=False)
    # Apply the same Tool RAG + lean AX the live control endpoint uses.
    from yuki.backend.routers.chat import _configure_agent_for_model
    _configure_agent_for_model(agent, llm)

    steps: list[str] = []

    if not args.real:
        # Intercept execution: log the action, fake success, advance the screen.
        from yuki.agent.registry.views import ToolResult

        action_count = {"n": 0}

        def fake_execute(tool_name: str, tool_params: dict, desktop=None):  # noqa: ANN001
            thought = tool_params.get("thought", "")
            plan = tool_params.get("plan", "")
            args_only = {k: v for k, v in tool_params.items()
                         if k not in ("thought", "plan", "evaluate")}
            line = f"  step {len(steps)+1}: {tool_name}  {args_only}"
            steps.append(line)
            print(line)
            if thought:
                print(f"           thought: {thought}")
            if plan and plan.strip():
                print(f"           plan: {plan.strip().splitlines()[0]} ...")
            action_count["n"] += 1
            if tool_name == "done_tool":
                return ToolResult(is_success=True, content=tool_params.get("answer", "done"))
            return ToolResult(is_success=True, content=f"(simulated {tool_name} ok)")

        agent.registry.execute = fake_execute  # type: ignore[assignment]
        agent.registry.aexecute = lambda **kw: _async_wrap(fake_execute(**kw))  # type: ignore

    result = agent.invoke(task=args.goal)

    print("=" * 72)
    print(f"steps taken: {len(steps)}")
    print(f"is_done: {result.is_done}")
    print(f"final answer: {(result.content or '')[:300]!r}")

    # Crude success heuristic for the simulated run.
    joined = " ".join(steps).lower()
    decomposed = (
        any("app_tool" in s and "chrome" in s.lower() for s in steps)
        and ("type_tool" in joined or "youtube" in joined)
        and result.is_done
    )
    print("\nVERDICT:", "✅ decomposed + finished" if decomposed
          else "⚠️ see steps above")


async def _async_wrap(value):  # noqa: ANN001
    return value


if __name__ == "__main__":
    main()
