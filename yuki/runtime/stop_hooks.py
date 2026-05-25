"""Stop hooks — last chance to re-open the loop with one more user message.

Mirrors claude-leak/src/query.ts (stop hooks reinjection).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class StopVerdict:
    action: Literal["pass", "inject"]
    injected_message: str = ""

    @classmethod
    def pass_through(cls) -> StopVerdict:
        return cls(action="pass")

    @classmethod
    def inject(cls, message: str) -> StopVerdict:
        return cls(action="inject", injected_message=message)


Hook = Callable[[list[Any]], StopVerdict]


class StopHookRegistry:
    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        self._hooks.append(hook)

    def evaluate(self, *, messages: list[Any]) -> StopVerdict:
        for hook in self._hooks:
            verdict = hook(messages)
            if verdict.action == "inject":
                return verdict
        return StopVerdict.pass_through()
