"""Calendar condition — matches EVENT_STARTING with optional title substring."""

from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.EVENT_STARTING:
        return False
    needle = (trigger.condition.get("title_contains") or "").lower().strip()
    if not needle:
        return True
    title = (event.payload.get("title") or "").lower()
    return needle in title
