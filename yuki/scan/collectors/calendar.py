"""Calendar collector — reads recent events via EventKit (pyobjc)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)


def _make_store() -> Any:  # pragma: no cover — real macOS only
    try:
        from EventKit import EKEntityTypeEvent, EKEventStore  # type: ignore[import-untyped]
    except Exception:
        return None
    store = EKEventStore.alloc().init()
    granted = {"v": False}

    def cb(ok: bool, err: object) -> None:
        granted["v"] = bool(ok)

    store.requestAccessToEntityType_completion_(EKEntityTypeEvent, cb)
    return store


class CalendarCollector:
    name = "calendar"

    def __init__(self, days: int = 90) -> None:
        self._days = days

    async def collect(self) -> list[dict[str, Any]]:
        store = _make_store()
        if store is None:
            return []
        end = datetime.now(UTC)
        start = end - timedelta(days=self._days)
        try:
            pred = store.predicateForEventsWithStartDate_endDate_calendars_(start, end, None)
            events = store.eventsMatchingPredicate_(pred)
        except Exception as e:
            log.warning("EventKit query failed: %s", e)
            return []
        rows: list[dict[str, Any]] = []
        for ev in events or []:
            try:
                organizer = ev.organizer()
                organizer_name = organizer.name() if organizer else ""
                attendees = [a.name() for a in (ev.attendees() or [])]
                rows.append(
                    {
                        "title": ev.title() or "",
                        "organizer": organizer_name,
                        "attendees": attendees,
                        "start": str(ev.startDate()),
                        "recurring": bool(ev.hasRecurrenceRules()),
                    }
                )
            except Exception:
                continue
        return rows
