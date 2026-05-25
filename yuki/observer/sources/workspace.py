"""Workspace source — emits APP_FOCUS via NSWorkspace notifications.

Production wiring (registering with NSWorkspace's notification center to call
post_focus) lives in the daemon's start_native_observers() (Task 12).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class WorkspaceSource(Source):
    name = "workspace"

    def __init__(self) -> None:
        super().__init__()
        self._last_bundle: str | None = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _handle_app(self, info: dict[str, Any], buffer: RingBuffer) -> None:
        bundle = str(info.get("bundle_id", ""))
        if bundle == self._last_bundle:
            return
        self._last_bundle = bundle
        await buffer.push(
            Event(
                ts=datetime.now(UTC),
                kind=EventKind.APP_FOCUS,
                payload={"bundle_id": bundle, "name": info.get("name", "")},
            )
        )

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            info = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            return
        await self._handle_app(info, buffer)

    def post_focus(self, bundle_id: str, name: str) -> None:
        self._queue.put_nowait({"bundle_id": bundle_id, "name": name})
