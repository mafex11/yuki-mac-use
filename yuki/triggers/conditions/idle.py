"""idle condition — matches IDLE_START past min_minutes, optionally after_hour."""

from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.IDLE_START:
        return False
    min_minutes = float(trigger.condition.get("min_minutes", 30))
    seconds = float(event.payload.get("seconds", 0))
    if seconds < min_minutes * 60:
        return False
    after_hour = trigger.condition.get("after_hour")
    return not (after_hour is not None and event.ts.hour < int(after_hour))
