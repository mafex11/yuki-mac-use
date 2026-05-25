"""RingBuffer push/drain + drop-oldest semantics."""

from __future__ import annotations

from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer


def _e(secs: int) -> Event:
    ts = datetime(2026, 5, 22, 12, 0, secs, tzinfo=UTC)
    return Event(ts=ts, kind=EventKind.APP_FOCUS, payload={"i": secs})


async def test_push_and_drain() -> None:
    rb = RingBuffer(capacity=10)
    await rb.push(_e(1))
    await rb.push(_e(2))
    out = await rb.drain()
    assert [e.payload["i"] for e in out] == [1, 2]
    assert await rb.drain() == []


async def test_drops_oldest_when_full() -> None:
    rb = RingBuffer(capacity=3)
    for i in range(5):
        await rb.push(_e(i))
    out = await rb.drain()
    assert [e.payload["i"] for e in out] == [2, 3, 4]


async def test_size_property() -> None:
    rb = RingBuffer(capacity=10)
    for i in range(4):
        await rb.push(_e(i))
    assert rb.size == 4
