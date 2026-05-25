"""Window source — emits WINDOW_FOCUS and WINDOW_TITLE via AX notifications."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class WindowSource(Source):
    name = "window"

    def __init__(self) -> None:
        super().__init__()
        self._last_title: str | None = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _handle(self, info: dict[str, Any], buffer: RingBuffer) -> None:
        ts = datetime.now(UTC)
        app = str(info.get("app", ""))
        await buffer.push(
            Event(ts=ts, kind=EventKind.WINDOW_FOCUS, payload={"app": app})
        )
        title = str(info.get("title", ""))
        if title and title != self._last_title:
            self._last_title = title
            await buffer.push(
                Event(
                    ts=ts,
                    kind=EventKind.WINDOW_TITLE,
                    payload={"app": app, "title": title},
                )
            )

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            info = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            return
        await self._handle(info, buffer)

    def post_window(self, app: str, title: str) -> None:
        self._queue.put_nowait({"app": app, "title": title})
