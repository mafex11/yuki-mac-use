"""Bridge agent events into an asyncio.Queue the SSE generator drains.

The agent loop may emit from a worker thread, so put_nowait must hop back to
the event loop via call_soon_threadsafe.
"""

from __future__ import annotations

import asyncio
from typing import Any

from yuki.agent.events.subscriber import BaseEventSubscriber
from yuki.agent.events.views import AgentEvent


class QueueEventSubscriber(BaseEventSubscriber):
    def __init__(self, queue: asyncio.Queue,
                 loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._queue = queue
        self._loop = loop

    def invoke(self, event: AgentEvent) -> None:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


def event_to_sse(ev: AgentEvent) -> dict[str, Any]:
    return {**ev.data, "type": ev.type.value}
