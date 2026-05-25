"""Command registry."""

from __future__ import annotations

from yuki.runtime.commands.base import LocalCommand, PromptCommand

Command = LocalCommand | PromptCommand
REGISTRY: dict[str, Command] = {}


def register(cmd: Command) -> None:
    REGISTRY[cmd.name] = cmd
