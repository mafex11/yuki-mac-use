"""FIFO single-worker queue so two /control tasks never fight the mouse."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class ControlQueue:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._waiting = 0

    def depth(self) -> int:
        return self._waiting

    async def submit(self, job: Callable[[], Awaitable[Any]]) -> asyncio.Future:
        """Schedule job; returns a future resolving to its result.
        Jobs run one at a time in submission order."""
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiting += 1

        async def _run() -> None:
            async with self._lock:
                self._waiting -= 1
                try:
                    result = await job()
                    fut.set_result(result)
                except Exception as e:
                    fut.set_exception(e)

        asyncio.create_task(_run())
        return fut
