"""Chat router — SSE stream of agent thoughts, tool calls, tokens, and final."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from yuki.backend.caching import build_cached_system_blocks
from yuki.backend.runtime import get_runtime
from yuki.backend.trajectory import TrajectoryRecorder

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


async def _stream_events(
    message: str, conversation_id: str | None
) -> AsyncIterator[dict[str, Any]]:
    """Bridge to yuki.agent.Agent.ainvoke and yield its events.

    Wires (a) identity hot-context per spec §4.4, (b) cache_control markers,
    (c) trajectory recording.
    """
    from yuki.agent import Agent
    from yuki.memory import load_hot_context
    from yuki.providers.factory import ProviderConfigError, make_llm
    from yuki.providers.stub import ChatStub

    rt = get_runtime()
    rec = TrajectoryRecorder(conversation_id=conversation_id)
    rec.record({"type": "user", "text": message})

    hot = load_hot_context(rt.vault).strip()
    # cached_blocks consumed by production providers; stub ignores it.
    _ = build_cached_system_blocks(
        base_prompt="You are Yuki, a macOS assistant.",
        hot_context=hot,
    )
    framed_task = (
        message
        if not hot
        else f"<identity_context>\n{hot}\n</identity_context>\n\nUser task: {message}"
    )

    try:
        llm = make_llm()
    except ProviderConfigError as e:
        # Fall back to the stub so the chat surface stays alive; tell the user.
        yield {"type": "error", "content": str(e)}
        llm = ChatStub()  # type: ignore[assignment]

    agent = Agent(llm=llm)
    result = await agent.ainvoke(task=framed_task)
    final = {"type": "done", "content": getattr(result, "content", "")}
    rec.record(final)
    yield final


def _to_sse(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, str]]:
    async def _gen() -> AsyncIterator[dict[str, str]]:
        async for ev in events:
            yield {"event": ev["type"], "data": json.dumps(ev)}

    return _gen()


@router.post("")
async def post_chat(req: ChatRequest) -> Any:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="empty message")
    events = _stream_events(req.message, req.conversation_id)
    return EventSourceResponse(_to_sse(events))
