"""Calendar source — emits EVENT_STARTING and EVENT_ENDED via EventKit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

_LEAD = timedelta(minutes=5)


async def _default_fetch() -> list[dict[str, Any]]:  # pragma: no cover — real macOS only
    try:
        from EventKit import EKEventStore  # type: ignore[import-untyped]
    except Exception:
        return []
    store = EKEventStore.alloc().init()
    end = datetime.now(UTC) + timedelta(hours=24)
    start = datetime.now(UTC) - timedelta(hours=2)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(start, end, None)
    out: list[dict[str, Any]] = []
    for ek in store.eventsMatchingPredicate_(pred) or []:
        out.append(
            {
                "id": str(ek.eventIdentifier()),
                "title": ek.title() or "",
                "start": datetime.fromtimestamp(
                    ek.startDate().timeIntervalSince1970(), tz=UTC
                ),
                "end": datetime.fromtimestamp(
                    ek.endDate().timeIntervalSince1970(), tz=UTC
                ),
            }
        )
    return out


class CalendarSource(Source):
    name = "calendar"

    def __init__(
        self,
        fetch_events: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        self._fetch = fetch_events or _default_fetch
        self._now = now or (lambda: datetime.now(UTC))
        self._fired_starting: set[str] = set()
        self._fired_ended: set[str] = set()

    async def iterate(self, buffer: RingBuffer) -> None:
        events = await self._fetch()
        now = self._now()
        for ev in events:
            eid = str(ev["id"])
            start: datetime = ev["start"]
            end: datetime = ev["end"]
            lead_secs = (start - now).total_seconds()
            if (
                eid not in self._fired_starting
                and 0 <= lead_secs <= _LEAD.total_seconds()
            ):
                self._fired_starting.add(eid)
                await buffer.push(
                    Event(
                        ts=now,
                        kind=EventKind.EVENT_STARTING,
                        payload={
                            "id": eid,
                            "title": ev.get("title", ""),
                            "start": start.isoformat(),
                        },
                    )
                )
            if eid not in self._fired_ended and end <= now:
                self._fired_ended.add(eid)
                await buffer.push(
                    Event(
                        ts=now,
                        kind=EventKind.EVENT_ENDED,
                        payload={"id": eid, "title": ev.get("title", "")},
                    )
                )
