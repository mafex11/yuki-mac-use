"""calendar_tool: list, create, errors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from yuki.tools.native.calendar_tool import calendar_tool


def _fake_event(title: str, start: datetime, end: datetime, eid: str = "e1") -> Any:
    e = MagicMock()
    e.title.return_value = title
    e.startDate.return_value = start
    e.endDate.return_value = end
    e.eventIdentifier.return_value = eid
    return e


async def test_list_returns_events() -> None:
    e = _fake_event(
        "Standup",
        datetime(2026, 5, 22, 10, tzinfo=UTC),
        datetime(2026, 5, 22, 10, 15, tzinfo=UTC),
    )
    store = MagicMock()
    store.eventsMatchingPredicate_.return_value = [e]
    store.predicateForEventsWithStartDate_endDate_calendars_.return_value = object()
    with patch("yuki.tools.native.calendar_tool._make_store", return_value=store):
        out = await calendar_tool(action="list", days=7)
    assert isinstance(out, list)
    assert out[0]["title"] == "Standup"


async def test_unknown_action_raises() -> None:
    store = MagicMock()
    with (
        patch("yuki.tools.native.calendar_tool._make_store", return_value=store),
        pytest.raises(ValueError),
    ):
        await calendar_tool(action="banana")


async def test_no_eventkit_returns_error() -> None:
    with patch("yuki.tools.native.calendar_tool._make_store", return_value=None):
        out = await calendar_tool(action="list", days=1)
    assert out == {"error": "EventKit unavailable"}
