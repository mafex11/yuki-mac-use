"""external condition — wifi / power events match a target SSID or state."""

from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind == EventKind.WIFI_CHANGED:
        target = trigger.condition.get("ssid")
        if target is None:
            return False
        return bool(event.payload.get("ssid") == target)
    if event.kind == EventKind.POWER_SOURCE_CHANGED:
        target = trigger.condition.get("source")
        if target is None:
            return False
        return bool(event.payload.get("source") == target)
    return False
