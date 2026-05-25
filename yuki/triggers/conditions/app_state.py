"""app_state condition — matches APP_FOCUS for a target bundle id."""

from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.APP_FOCUS:
        return False
    target = trigger.condition.get("bundle_id", "")
    return bool(event.payload.get("bundle_id") == target)
