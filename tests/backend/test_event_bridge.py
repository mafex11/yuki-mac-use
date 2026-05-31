import asyncio
import pytest
from yuki.agent.events.views import AgentEvent, EventType
from yuki.backend.event_bridge import QueueEventSubscriber, event_to_sse


async def test_subscriber_pushes_to_queue():
    q: asyncio.Queue = asyncio.Queue()
    sub = QueueEventSubscriber(q)
    sub.invoke(AgentEvent(type=EventType.THOUGHT, data={"thought": "hi"}))
    ev = await asyncio.wait_for(q.get(), timeout=1.0)
    assert ev.type == EventType.THOUGHT
    assert ev.data["thought"] == "hi"


async def test_event_to_sse_shapes():
    ev = AgentEvent(type=EventType.TOOL_CALL,
                    data={"tool_name": "app_tool", "tool_params": {"name": "Chrome"}})
    sse = event_to_sse(ev)
    assert sse["type"] == "tool_call"
    assert sse["tool_name"] == "app_tool"
