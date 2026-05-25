"""Confirmer protocol + an in-memory implementation for tests."""

from __future__ import annotations

from typing import Any, Protocol

from yuki.safety.decision import Decision


class Confirmer(Protocol):
    async def ask(
        self,
        tool_name: str,
        args: dict[str, Any],
        danger: str,
        preview: str,
    ) -> Decision: ...


class InMemoryConfirmer:
    def __init__(self, responses: list[Decision] | None = None) -> None:
        self._responses = list(responses or [])
        self.asked: list[tuple[str, dict[str, Any], str, str]] = []

    async def ask(
        self,
        tool_name: str,
        args: dict[str, Any],
        danger: str,
        preview: str,
    ) -> Decision:
        self.asked.append((tool_name, dict(args), danger, preview))
        if self._responses:
            return self._responses.pop(0)
        return Decision.approve(payload=dict(args))
