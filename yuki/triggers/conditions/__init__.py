"""Trigger conditions — one module per kind, each exports matches()."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from yuki.observer.events import Event
from yuki.triggers.conditions import app_state, calendar, deviation, external, idle, time
from yuki.triggers.trigger import Trigger

REGISTRY: dict[str, Callable[[Trigger, Any], bool]] = {
    "time": time.matches,
    "calendar": calendar.matches,
    "app_state": app_state.matches,
    "idle": idle.matches,
    "deviation": deviation.matches,
    "external": external.matches,
}


def matches_any(trigger: Trigger, event_or_now: Event | datetime) -> bool:
    fn = REGISTRY.get(trigger.condition_kind)
    if fn is None:
        return False
    return fn(trigger, event_or_now)
