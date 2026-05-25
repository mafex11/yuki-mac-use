"""Source protocol with error-swallowing run loop.

Each Source is an asyncio task that pushes Events into a shared RingBuffer.
The run() wrapper catches per-iteration exceptions so a flaky source can't
take down the whole daemon.
"""

from __future__ import annotations

import asyncio
import logging

from yuki.observer.ringbuffer import RingBuffer

log = logging.getLogger(__name__)


class Source:
    name: str = "source"

    def __init__(self) -> None:
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def iterate(self, buffer: RingBuffer) -> None:
        """Override: do one unit of work, push 0..N events."""
        raise NotImplementedError

    async def run(self, buffer: RingBuffer, tick: float = 1.0) -> None:
        while not self._stopped:
            try:
                await self.iterate(buffer)
            except Exception as e:
                log.warning("source %s failed: %s", self.name, e)
            if tick > 0:
                await asyncio.sleep(tick)
