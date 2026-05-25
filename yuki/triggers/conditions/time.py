"""Time condition — fires when a cron expression's previous tick is in the last minute."""

from __future__ import annotations

from datetime import datetime

from croniter import croniter  # type: ignore[import-untyped]

from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, now: datetime) -> bool:
    cron = trigger.condition.get("cron", "")
    try:
        # match() returns True if the cron expression fires at exactly `now`
        # (truncated to minute granularity). This is what we want for both
        # "exactly on schedule" and "ticker fires every 30s and we land on it".
        return bool(croniter.match(cron, now))
    except (ValueError, KeyError):
        return False
