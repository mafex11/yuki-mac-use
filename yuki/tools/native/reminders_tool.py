"""reminders_tool — list/create/complete via EventKit reminders."""

from __future__ import annotations

import asyncio
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _make_store() -> Any:  # pragma: no cover
    try:
        from EventKit import EKEventStore  # type: ignore[import-untyped]

        return EKEventStore.alloc().init()
    except Exception:
        return None


async def _fetch(store: Any) -> list[Any]:  # pragma: no cover
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[list[Any]] = loop.create_future()

    def cb(items: Any) -> None:
        loop.call_soon_threadsafe(fut.set_result, list(items or []))

    pred = store.predicateForRemindersInCalendars_(None)
    store.fetchRemindersMatchingPredicate_completion_(pred, cb)
    return await asyncio.wait_for(fut, timeout=10.0)


def _create(store: Any, title: str) -> dict[str, Any]:  # pragma: no cover
    from EventKit import EKReminder

    r = EKReminder.reminderWithEventStore_(store)
    r.setTitle_(title)
    r.setCalendar_(store.defaultCalendarForNewReminders())
    ok, _ = store.saveReminder_commit_error_(r, True, None)
    return {"created": bool(ok), "id": str(r.calendarItemIdentifier()) if ok else None}


def _complete(store: Any, reminder_id: str) -> dict[str, Any]:  # pragma: no cover
    item = store.calendarItemWithIdentifier_(reminder_id)
    if item is None:
        return {"completed": False, "error": "not found"}
    item.setCompleted_(True)
    ok, _ = store.saveReminder_commit_error_(item, True, None)
    return {"completed": bool(ok)}


@tool(name="reminders", danger=DangerLevel.REVERSIBLE)
async def reminders_tool(
    action: str,
    title: str = "",
    reminder_id: str = "",
) -> Any:
    """List, create, or complete reminders via EventKit."""
    store = _make_store()
    if store is None:
        return {"error": "EventKit unavailable"}
    if action == "list":
        items = await _fetch(store)
        return [
            {"id": str(i.calendarItemIdentifier()), "title": i.title() or ""}
            for i in items
            if not i.isCompleted()
        ]
    if action == "create":
        return _create(store, title)
    if action == "complete":
        return _complete(store, reminder_id)
    raise ValueError(f"Unknown reminders action: {action!r}")
