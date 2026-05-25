"""DebounceGuard — blocks fires within trigger.debounce_seconds of last fire."""

from __future__ import annotations

from datetime import datetime, timedelta

from yuki.triggers.trigger import Trigger


class DebounceGuard:
    def __init__(self) -> None:
        self._last: dict[str, datetime] = {}

    def allow(self, trigger: Trigger, now: datetime) -> bool:
        last = self._last.get(trigger.id) or trigger.last_fired
        if last is None:
            return True
        return (now - last) >= timedelta(seconds=trigger.debounce_seconds)

    def mark_fired(self, trigger: Trigger, now: datetime) -> None:
        self._last[trigger.id] = now
        trigger.last_fired = now
