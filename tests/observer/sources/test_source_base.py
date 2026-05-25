"""Source.run() wrapper: emits until stopped, swallows iteration errors."""

from __future__ import annotations

from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class _Emitter(Source):
    name = "emitter"

    def __init__(self) -> None:
        super().__init__()
        self.iters = 0

    async def iterate(self, buffer: RingBuffer) -> None:
        self.iters += 1
        await buffer.push(
            Event(
                ts=datetime.now(UTC),
                kind=EventKind.APP_FOCUS,
                payload={"i": self.iters},
            )
        )
        if self.iters >= 3:
            self.stop()


class _Boom(Source):
    name = "boom"

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def iterate(self, buffer: RingBuffer) -> None:
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("oops")
        self.stop()


async def test_source_emits_until_stopped() -> None:
    rb = RingBuffer()
    src = _Emitter()
    await src.run(rb, tick=0.0)
    out = await rb.drain()
    assert len(out) == 3


async def test_source_swallows_iteration_errors() -> None:
    rb = RingBuffer()
    src = _Boom()
    await src.run(rb, tick=0.0)
    assert src.calls == 3
