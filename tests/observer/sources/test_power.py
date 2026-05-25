"""PowerSource: maps lock/unlock; ignores unknown names."""

from __future__ import annotations

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.power import PowerSource


async def test_emits_lock_unlock() -> None:
    src = PowerSource()
    rb = RingBuffer()
    src.post("lock")
    src.post("unlock")
    for _ in range(2):
        await src.iterate(rb)
    out = await rb.drain()
    assert [e.kind for e in out] == [EventKind.LOCK, EventKind.UNLOCK]


async def test_unknown_event_ignored() -> None:
    src = PowerSource()
    rb = RingBuffer()
    src.post("zzz")
    await src.iterate(rb)
    assert await rb.drain() == []
