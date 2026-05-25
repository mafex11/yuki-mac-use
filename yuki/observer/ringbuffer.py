"""Bounded async ring buffer for observer events."""

from __future__ import annotations

import asyncio
from collections import deque

from yuki.observer.events import Event


class RingBuffer:
    def __init__(self, capacity: int = 100_000) -> None:
        self._buf: deque[Event] = deque(maxlen=capacity)
        self._lock = asyncio.Lock()

    async def push(self, event: Event) -> None:
        async with self._lock:
            self._buf.append(event)

    async def drain(self) -> list[Event]:
        async with self._lock:
            out = list(self._buf)
            self._buf.clear()
            return out

    @property
    def size(self) -> int:
        return len(self._buf)
