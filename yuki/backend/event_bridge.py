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
    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._loop = asyncio.get_event_loop()

    def invoke(self, event: AgentEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


def event_to_sse(ev: AgentEvent) -> dict[str, Any]:
    d: dict[str, Any] = {"type": ev.type.value}
    d.update(ev.data)
    return d
