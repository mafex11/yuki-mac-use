"""Pruner — propose disabling triggers with low acceptance after enough fires."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.memory import paths
from yuki.triggers.trigger import Trigger

_MIN_FIRES = 10
_LOW_ACCEPT = 0.3


def maybe_propose_disable(trigger: Trigger) -> Path | None:
    if trigger.fire_count < _MIN_FIRES:
        return None
    if trigger.acceptance_rate >= _LOW_ACCEPT:
        return None
    inbox = paths.vault_dir() / "90-Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    out = inbox / f"propose-disable-{trigger.id}.md"
    if not out.exists():
        out.write_text(
            f"# Propose disabling {trigger.id}\n\n"
            f"- fires: {trigger.fire_count}\n"
            f"- acceptance_rate: {trigger.acceptance_rate:.2f}\n"
            f"- timestamp: {datetime.now(UTC).isoformat()}\n",
            encoding="utf-8",
        )
    return out
