"""Command protocols + result envelope."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

CommandKind = Literal["agent", "local_text", "skip"]


@dataclass
class CommandResult:
    kind: CommandKind
    text: str = ""

    @classmethod
    def agent(cls, text: str) -> CommandResult:
        return cls(kind="agent", text=text)

    @classmethod
    def local_text(cls, text: str) -> CommandResult:
        return cls(kind="local_text", text=text)

    @classmethod
    def skip(cls) -> CommandResult:
        return cls(kind="skip")


@dataclass
class PromptCommand:
    """Expands to a templated user message that goes to the agent."""

    name: str
    prompt_template: str  # "{args}" gets substituted
    description: str = ""


@dataclass
class LocalCommand:
    """Runs locally; returns a CommandResult directly."""

    name: str
    run: Callable[[str], CommandResult]
    description: str = ""
