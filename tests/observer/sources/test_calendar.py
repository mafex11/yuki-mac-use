"""CalendarSource: lead-time fire + end-time fire + no-double-fire."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.calendar import CalendarSource


async def test_emits_event_starting_5min_before() -> None:
    base = datetime(2026, 5, 22, 9, 55, tzinfo=UTC)
    cal_event: dict[str, Any] = {
        "id": "e1",
        "title": "Standup",
        "start": base + timedelta(minutes=5),
        "end": base + timedelta(minutes=20),
    }

    async def fake_events() -> list[dict[str, Any]]:
        return [cal_event]

    src = CalendarSource(fetch_events=fake_events, now=lambda: base)
    rb = RingBuffer()
    await src.iterate(rb)
    out = await rb.drain()
    assert any(e.kind == EventKind.EVENT_STARTING for e in out)


async def test_emits_event_ended_after_end() -> None:
    base = datetime(2026, 5, 22, 10, 25, tzinfo=UTC)
    cal_event: dict[str, Any] = {
        "id": "e1",
        "title": "Standup",
        "start": base - timedelta(minutes=25),
        "end": base - timedelta(minutes=5),
    }

    async def fake_events() -> list[dict[str, Any]]:
        return [cal_event]

    src = CalendarSource(fetch_events=fake_events, now=lambda: base)
    rb = RingBuffer()
    await src.iterate(rb)
    out = await rb.drain()
    assert any(e.kind == EventKind.EVENT_ENDED for e in out)


async def test_no_double_fire() -> None:
    base = datetime(2026, 5, 22, 9, 55, tzinfo=UTC)
    cal_event: dict[str, Any] = {
        "id": "e1",
        "title": "X",
        "start": base + timedelta(minutes=5),
        "end": base + timedelta(minutes=20),
    }

    async def fake_events() -> list[dict[str, Any]]:
        return [cal_event]

    src = CalendarSource(fetch_events=fake_events, now=lambda: base)
    rb = RingBuffer()
    await src.iterate(rb)
    await src.iterate(rb)
    starting = [e for e in await rb.drain() if e.kind == EventKind.EVENT_STARTING]
    assert len(starting) == 1
