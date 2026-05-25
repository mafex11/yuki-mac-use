"""Filesystem source — emits FILE_MODIFIED via FSEvents.

Production wiring registers an FSEventStream callback that calls post_change.
Within-1s dedupe absorbs FSEvents bursts (npm install, build runs).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class FilesystemSource(Source):
    name = "filesystem"

    def __init__(self, watched_dirs: list[str]) -> None:
        super().__init__()
        self._watched = list(watched_dirs)
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._last_seen: dict[str, float] = {}

    def post_change(self, path: str) -> None:
        self._queue.put_nowait(path)

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            path = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            return
        now = time.time()
        last = self._last_seen.get(path, 0.0)
        if now - last < 1.0:
            return
        self._last_seen[path] = now
        await buffer.push(
            Event(
                ts=datetime.now(UTC),
                kind=EventKind.FILE_MODIFIED,
                payload={"path": path},
            )
        )
