"""Daemon supervisor — owns ring buffer + persister + N source tasks.

start() launches every source as its own asyncio task plus a periodic flusher.
stop() cancels gracefully and flushes remaining events.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from yuki.observer.persistence import Persister
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

log = logging.getLogger(__name__)


class Daemon:
    def __init__(
        self,
        sources: list[Source],
        flush_interval: float = 60.0,
        ring_capacity: int = 100_000,
    ) -> None:
        self._sources = list(sources)
        self._flush_interval = flush_interval
        self.buffer = RingBuffer(capacity=ring_capacity)
        self.persister = Persister()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self.persister.open()
        for src in self._sources:
            self._tasks.append(asyncio.create_task(src.run(self.buffer, tick=0.0)))
        self._tasks.append(asyncio.create_task(self._flusher()))

    async def stop(self) -> None:
        for src in self._sources:
            src.stop()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with suppress(asyncio.CancelledError):
                await t
        await self._flush_once()
        self.persister.close()
        self._tasks.clear()

    async def _flusher(self) -> None:
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush_once()

    async def _flush_once(self) -> None:
        try:
            events = await self.buffer.drain()
            self.persister.flush(events)
            self.persister.purge_old()
        except Exception as e:
            log.warning("flush failed: %s", e)
