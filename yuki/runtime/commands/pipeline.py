"""process_user_input — first stop for every chat message."""

from __future__ import annotations

from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import REGISTRY


def process_user_input(text: str) -> CommandResult:
    if not text.startswith("/"):
        return CommandResult.agent(text)

    head, _, tail = text[1:].partition(" ")
    cmd = REGISTRY.get(head)
    if cmd is None:
        # Unknown slash → treat as plain message; the agent can decide.
        return CommandResult.agent(text)

    if isinstance(cmd, LocalCommand):
        return cmd.run(tail.strip())
    rendered = cmd.prompt_template.format(args=tail.strip())
    return CommandResult.agent(rendered)
