"""Run the REAL agent loop on ANY goal — observe decomposition safely.

Runs the real agent loop (real LLM, real system prompt, real Tool RAG, thinking
ON for cloud models) but intercepts tool EXECUTION so nothing touches the real
Mac: each action is logged + given a synthetic "success", letting you watch the
agent decompose a goal across steps end-to-end. Works for any goal and any
provider — there is NO goal-specific scripting (that would just re-encode one
test case).

    uv run python scripts/demo_full_run.py "check the weather in Tokyo"
    uv run python scripts/demo_full_run.py "open spotify and play lofi" --provider openai
    uv run python scripts/demo_full_run.py "<goal>" --provider openai --real   # drives the Mac

--real removes the interception and lets the agent control the screen for real.
Default is safe (simulated execution). Loads .env so OPENAI/ANTHROPIC/GOOGLE
keys are picked up automatically.
"""

from __future__ import annotations

import argparse


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(".env")

    ap = argparse.ArgumentParser()
    ap.add_argument("goal", help="the goal to give the agent")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--real", action="store_true",
                    help="ACTUALLY drive the Mac (default: simulate execution)")
    args = ap.parse_args()

    from yuki import Agent
    from yuki.agent.registry.views import ToolResult
    from yuki.backend.routers.chat import _configure_agent_for_model
    from yuki.providers.factory import agent_mode_for, make_llm

    llm = make_llm(provider=args.provider, model=args.model)
    mode = agent_mode_for(llm)
    print(f"\nmodel={llm.model_name} provider={llm.provider} prompt_mode={mode} "
          f"thinking={getattr(llm, 'thinking_budget', None)}")
    print(f"goal: {args.goal!r}   mode={'REAL Mac control' if args.real else 'SIMULATED (safe)'}")
    print("=" * 72)

    agent = Agent(llm=llm, mode=mode, max_steps=args.max_steps,
                  log_to_console=False, auto_minimize=False)
    _configure_agent_for_model(agent, llm)

    steps: list[str] = []

    if not args.real:
        def fake_execute(tool_name: str, tool_params: dict, desktop=None):
            thought = tool_params.get("thought", "")
            plan = str(tool_params.get("plan", "")).strip()
            args_only = {k: v for k, v in tool_params.items()
                         if k not in ("thought", "plan", "evaluate")}
            steps.append(tool_name)
            print(f"  step {len(steps)}: {tool_name}  {args_only}")
            if thought:
                print(f"           thought: {thought[:160]}")
            if plan:
                print(f"           plan: {plan.splitlines()[0][:120]} ...")
            if tool_name == "done_tool":
                return ToolResult(is_success=True, content=tool_params.get("answer", "done"))
            return ToolResult(is_success=True, content=f"(simulated {tool_name} ok)")

        async def afake(**kw):
            return fake_execute(**kw)

        agent.registry.execute = fake_execute  # type: ignore[assignment]
        agent.registry.aexecute = afake  # type: ignore[assignment]

    result = agent.invoke(task=args.goal)

    print("=" * 72)
    print(f"steps taken: {len(steps)}  is_done: {result.is_done}")
    print(f"final answer: {(result.content or '')[:300]!r}")


if __name__ == "__main__":
    main()
