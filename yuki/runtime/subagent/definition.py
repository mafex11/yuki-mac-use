"""AgentDefinition — typed contract for a subagent."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass
class AgentDefinition:
    name: str
    system_prompt: str
    allowed_tools: list[str] | None = None
    model: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(
                f"Subagent name must be lowercase kebab-case: {self.name!r}"
            )

    @property
    def is_read_only(self) -> bool:
        """If allowed_tools is None, runner restricts to read-only tools by default."""
        return self.allowed_tools is None
