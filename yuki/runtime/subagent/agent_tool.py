"""agent_tool — exposes run_subagent as a @tool the parent agent can call."""

from __future__ import annotations

from typing import Any

from yuki.runtime.subagent.definition import AgentDefinition
from yuki.runtime.subagent.runner import run_subagent
from yuki.tools.native.registry import DangerLevel, tool


@tool(
    name="agent",
    danger=DangerLevel.READ_ONLY,
    prompt=(
        "Spawn a subagent for parallel research or focused exploration. "
        "The subagent runs read-only by default."
    ),
)
async def agent_tool(
    agent_name: str,
    prompt: str,
    system_prompt: str = "",
) -> dict[str, Any]:
    """Spawn a subagent. Returns the subagent's final answer.

    The subagent is read-only by default — it cannot mutate the vault, send
    mail, or take destructive action. Use it for exploration, research,
    summarization.
    """
    from yuki.providers.stub import ChatStub

    llm = ChatStub()

    definition = AgentDefinition(
        name=agent_name,
        system_prompt=system_prompt or f"You are the {agent_name} subagent.",
    )

    final: dict[str, Any] = {"content": ""}
    async for event in run_subagent(definition=definition, prompt=prompt, llm=llm):
        if event.get("type") == "result":
            final = {"agent_id": event["agent_id"], "content": event["content"]}
    return final
