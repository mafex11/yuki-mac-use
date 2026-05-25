"""Hard guards — abort the agent loop with structured reasons.

Mirrors claude-leak/src/QueryEngine.ts (max-turns enforcement).
"""

from __future__ import annotations

from typing import Any


class GuardViolation(Exception):  # noqa: N818 — name reads better than GuardViolationError
    """The loop must terminate. Carries the structured reason."""

    def __init__(self, reason: str, detail: dict[str, Any] | None = None) -> None:
        self.reason = reason
        self.detail = detail or {}
        super().__init__(f"{reason}: {detail}")


def check_max_turns(*, current_turns: int, max_turns: int) -> None:
    if current_turns > max_turns:
        raise GuardViolation(
            "max_turns_exceeded",
            {"current": current_turns, "limit": max_turns},
        )


def check_max_budget(*, totals: dict[str, Any], max_total_tokens: int) -> None:
    used = int(totals.get("input_tokens", 0)) + int(totals.get("output_tokens", 0))
    if used > max_total_tokens:
        raise GuardViolation(
            "max_budget_exceeded",
            {"used": used, "limit": max_total_tokens},
        )
