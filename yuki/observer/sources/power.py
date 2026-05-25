"""Power source — lock/unlock/sleep/wake/power-source via IOKit notifications."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

_KIND_MAP = {
    "lock": EventKind.LOCK,
    "unlock": EventKind.UNLOCK,
    "sleep": EventKind.SLEEP,
    "wake": EventKind.WAKE,
    "power_source_changed": EventKind.POWER_SOURCE_CHANGED,
}


class PowerSource(Source):
    name = "power"

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def post(self, name: str) -> None:
        self._queue.put_nowait(name)

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            name = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            return
        kind = _KIND_MAP.get(name)
        if kind is None:
            return
        await buffer.push(Event(ts=datetime.now(UTC), kind=kind, payload={}))
