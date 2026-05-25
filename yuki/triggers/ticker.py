"""TimeTicker — pulses a callback every N seconds for time-condition checks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime

log = logging.getLogger(__name__)


class TimeTicker:
    def __init__(
        self,
        callback: Callable[[datetime], Awaitable[None]],
        interval: float = 30.0,
    ) -> None:
        self._cb = callback
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self._cb(datetime.now(UTC))
            except Exception as e:
                log.warning("time ticker callback failed: %s", e)
            await asyncio.sleep(self._interval)
