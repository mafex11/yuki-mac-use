"""IdleSource: threshold crossings → IDLE_START / IDLE_END."""

from __future__ import annotations

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.idle import IdleSource


async def test_idle_start_then_end() -> None:
    seconds = iter([10.0, 70.0, 80.0, 5.0])

    async def fake_idle() -> float:
        return next(seconds)

    src = IdleSource(get_idle=fake_idle, threshold=60)
    rb = RingBuffer()
    for _ in range(4):
        await src.iterate(rb)
    out = await rb.drain()
    kinds = [e.kind for e in out]
    assert EventKind.IDLE_START in kinds
    assert EventKind.IDLE_END in kinds
    assert kinds.index(EventKind.IDLE_START) < kinds.index(EventKind.IDLE_END)


async def test_no_event_below_threshold() -> None:
    seconds = iter([10.0, 20.0, 30.0, 40.0])

    async def fake_idle() -> float:
        return next(seconds)

    src = IdleSource(get_idle=fake_idle, threshold=60)
    rb = RingBuffer()
    for _ in range(4):
        await src.iterate(rb)
    assert await rb.drain() == []
