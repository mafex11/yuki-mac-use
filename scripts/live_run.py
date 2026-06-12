"""Run the agent FOR REAL on the Mac and log every reasoning step.

This actually drives the screen (no simulation). It subscribes to the agent's
event stream and prints each STATE / EVALUATE / PLAN / THOUGHT / TOOL_CALL /
TOOL_RESULT / DONE so you can see whether Yuki decomposed the goal and carried
it out end-to-end.

    uv run python scripts/live_run.py "open the Calculator and compute 47 times 89" --provider openai
"""

from __future__ import annotations

import argparse


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(".env")

    ap = argparse.ArgumentParser()
    ap.add_argument("goal")
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-steps", type=int, default=12)
    args = ap.parse_args()

    from yuki import Agent
    from yuki.agent.events.views import AgentEvent, EventType
    from yuki.backend.routers.chat import _configure_agent_for_model
    from yuki.providers.factory import agent_mode_for, make_llm

    llm = make_llm(provider=args.provider, model=args.model)
    mode = agent_mode_for(llm)

    transcript: list[str] = []

    def on_event(ev: AgentEvent) -> None:
        d = ev.data
        if ev.type == EventType.STATE:
            line = f"\n── step {d.get('step', 0) + 1} ── app={d.get('active_app', '?')}"
        elif ev.type == EventType.THOUGHT:
            line = f"   🧠 {d.get('thought', '')}"
        elif ev.type == EventType.PLAN:
            line = f"   📋 plan: {d.get('plan', '')}"
        elif ev.type == EventType.TOOL_CALL:
            p = {k: v for k, v in (d.get('tool_params') or {}).items()
                 if k not in ('thought', 'plan', 'evaluate')}
            line = f"   🛠️  {d.get('tool_name')}({p})"
        elif ev.type == EventType.TOOL_RESULT:
            ok = d.get('is_success', True)
            line = f"   {'✅' if ok else '❌'} {str(d.get('content', ''))[:140]}"
        elif ev.type == EventType.DONE:
            line = f"\n🏁 DONE: {d.get('content', '')}"
        elif ev.type == EventType.ERROR:
            line = f"\n🚨 ERROR: {d.get('error', '')}"
        else:
            return
        print(line, flush=True)
        transcript.append(line)

    print(f"model={llm.model_name} provider={llm.provider} prompt_mode={mode} "
          f"thinking={getattr(llm, 'thinking_budget', None)}")
    print(f"GOAL (live, real Mac control): {args.goal!r}")
    print("=" * 72)

    agent = Agent(llm=llm, mode=mode, max_steps=args.max_steps,
                  log_to_console=False, auto_minimize=False,
                  event_subscriber=on_event)
    _configure_agent_for_model(agent, llm)

    result = agent.invoke(task=args.goal)

    print("=" * 72)
    print(f"is_done={result.is_done}  steps={getattr(agent.state, 'step', '?')}")
    print(f"final: {(result.content or '')[:400]}")


if __name__ == "__main__":
    main()
