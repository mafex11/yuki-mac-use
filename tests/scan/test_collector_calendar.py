"""Calendar collector — EventKit-mocked."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from yuki.scan.collectors.calendar import CalendarCollector


def _fake_event(
    title: str,
    organizer: str,
    attendees: list[str],
    start: datetime,
    recurring: bool = False,
) -> MagicMock:
    e = MagicMock()
    e.title.return_value = title
    org = MagicMock()
    org.name.return_value = organizer
    e.organizer.return_value = org
    atts = []
    for n in attendees:
        a = MagicMock()
        a.name.return_value = n
        atts.append(a)
    e.attendees.return_value = atts
    e.startDate.return_value = start
    e.hasRecurrenceRules.return_value = recurring
    return e


@pytest.mark.asyncio
async def test_calendar_emits_events_with_attendees() -> None:
    start = datetime(2026, 5, 1, 10, tzinfo=UTC)
    e = _fake_event("1:1 with Sarah", "Sarah Chen", ["user", "Sarah Chen"], start, True)
    fake_store = MagicMock()
    fake_store.eventsMatchingPredicate_.return_value = [e]
    fake_store.predicateForEventsWithStartDate_endDate_calendars_.return_value = object()
    fake_store.requestAccessToEntityType_completion_.return_value = None

    with patch("yuki.scan.collectors.calendar._make_store", return_value=fake_store):
        rows = await CalendarCollector(days=30).collect()

    assert len(rows) == 1
    assert rows[0]["title"] == "1:1 with Sarah"
    assert "Sarah Chen" in rows[0]["attendees"]
    assert rows[0]["recurring"] is True


@pytest.mark.asyncio
async def test_calendar_missing_eventkit_returns_empty() -> None:
    with patch("yuki.scan.collectors.calendar._make_store", return_value=None):
        rows = await CalendarCollector().collect()
    assert rows == []
