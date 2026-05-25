"""calendar_tool — list/create/delete via EventKit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _make_store() -> Any:  # pragma: no cover — pyobjc only
    try:
        from EventKit import EKEventStore  # type: ignore[import-untyped]

        return EKEventStore.alloc().init()
    except Exception:
        return None


def _list(store: Any, days: int) -> list[dict[str, Any]]:
    end = datetime.now(UTC) + timedelta(days=days)
    start = datetime.now(UTC)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(start, end, None)
    out: list[dict[str, Any]] = []
    for e in store.eventsMatchingPredicate_(pred) or []:
        out.append(
            {
                "id": str(e.eventIdentifier()),
                "title": e.title() or "",
                "start": str(e.startDate()),
                "end": str(e.endDate()),
            }
        )
    return out


def _create(store: Any, title: str, start: str, end: str) -> dict[str, Any]:  # pragma: no cover
    from EventKit import EKEvent, EKSpanThisEvent

    ev = EKEvent.eventWithEventStore_(store)
    ev.setTitle_(title)
    ev.setStartDate_(datetime.fromisoformat(start))
    ev.setEndDate_(datetime.fromisoformat(end))
    ev.setCalendar_(store.defaultCalendarForNewEvents())
    ok, _ = store.saveEvent_span_error_(ev, EKSpanThisEvent, None)
    return {"created": bool(ok), "id": str(ev.eventIdentifier()) if ok else None}


def _delete(store: Any, event_id: str) -> dict[str, Any]:  # pragma: no cover
    from EventKit import EKSpanThisEvent

    ev = store.eventWithIdentifier_(event_id)
    if ev is None:
        return {"deleted": False, "error": "not found"}
    ok, _ = store.removeEvent_span_error_(ev, EKSpanThisEvent, None)
    return {"deleted": bool(ok)}


@tool(name="calendar", danger=DangerLevel.EXTERNAL)
async def calendar_tool(
    action: str,
    days: int = 7,
    title: str = "",
    start: str = "",
    end: str = "",
    event_id: str = "",
) -> Any:
    """List, create, or delete macOS calendar events via EventKit."""
    store = _make_store()
    if store is None:
        return {"error": "EventKit unavailable"}
    if action == "list":
        return _list(store, days)
    if action == "create":
        return _create(store, title, start, end)
    if action == "delete":
        return _delete(store, event_id)
    raise ValueError(f"Unknown calendar action: {action!r}")
