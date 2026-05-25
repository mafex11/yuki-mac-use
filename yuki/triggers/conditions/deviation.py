"""deviation condition — v1 implements 2 specific kinds; rest are False-stubs."""

from __future__ import annotations

from collections.abc import Callable

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger

_MEETING_APPS = {"us.zoom.xos", "com.microsoft.teams2", "com.google.Chrome"}


def _missed_recurring(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.EVENT_STARTING:
        return False
    expected = set(trigger.condition.get("expected_apps") or _MEETING_APPS)
    return bool(expected)


def _end_of_day_overrun(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.APP_FOCUS:
        return False
    quit_hour = int(trigger.condition.get("quit_hour", 18))
    return event.ts.hour >= quit_hour


_HANDLERS: dict[str, Callable[[Trigger, Event], bool]] = {
    "missed_recurring_meeting": _missed_recurring,
    "end_of_day_overrun": _end_of_day_overrun,
}


def matches(trigger: Trigger, event: Event) -> bool:
    kind = trigger.condition.get("deviation_kind", "")
    handler = _HANDLERS.get(kind)
    if handler is None:
        return False
    return handler(trigger, event)
