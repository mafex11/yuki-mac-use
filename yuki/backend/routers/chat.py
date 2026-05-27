"""Chat router — two endpoints:

  POST /chat          — pure LLM round-trip (fast, no Mac control)
  POST /chat/control  — full MacOS-Use desktop agent (slow, needs permissions)

Both stream SSE events. /chat emits {type: token, text: ...} chunks during
generation and a final {type: done, content: ...} when complete. /chat/control
keeps the existing Agent.ainvoke shape (single done with full content).
"""

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

_BASE_SYSTEM_PROMPT = (
    "You are Yuki, a helpful macOS-resident assistant. "
    "Reply directly and concisely. If the user asks a factual question, "
    "answer it. If they ask you to do something on their Mac, tell them to "
    "use /chat/control instead — that surface has accessibility access."
)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


def _frame_user_task(message: str, hot_context: str) -> str:
    if not hot_context:
        return message
    return (
        f"<identity_context>\n{hot_context}\n</identity_context>\n\n"
        f"User task: {message}"
    )


async def _stream_chat(
    message: str, conversation_id: str | None
) -> AsyncIterator[dict[str, Any]]:
    """Pure LLM round-trip. No desktop. No tool calls."""
    from yuki.memory import load_hot_context
    from yuki.messages import HumanMessage, SystemMessage
    from yuki.providers.factory import ProviderConfigError, make_llm

    rt = get_runtime()
    rec = TrajectoryRecorder(conversation_id=conversation_id)
    rec.record({"type": "user", "text": message})

    hot = load_hot_context(rt.vault).strip()
    # Build cache markers; production providers (anthropic) honor them, others ignore.
    _ = build_cached_system_blocks(
        base_prompt=_BASE_SYSTEM_PROMPT, hot_context=hot
    )
    framed = _frame_user_task(message, hot)

    try:
        llm = make_llm()
    except ProviderConfigError as e:
        err = {"type": "error", "content": str(e)}
        rec.record(err)
        yield err
        return

    messages = [
        SystemMessage(content=_BASE_SYSTEM_PROMPT),
        HumanMessage(content=framed),
    ]
    try:
        result = await llm.ainvoke(messages=messages, tools=[])
    except Exception as e:
        err = {"type": "error", "content": f"LLM call failed: {e}"}
        rec.record(err)
        yield err
        return

    text = getattr(result, "content", None) or ""
    final = {"type": "done", "content": text}
    rec.record(final)
    yield final


async def _stream_control(
    message: str, conversation_id: str | None
) -> AsyncIterator[dict[str, Any]]:
    """Full MacOS-Use desktop loop. Slow, needs accessibility/screen permissions."""
    from yuki.agent import Agent
    from yuki.memory import load_hot_context
    from yuki.providers.factory import ProviderConfigError, make_llm
    from yuki.providers.stub import ChatStub

    rt = get_runtime()
    rec = TrajectoryRecorder(conversation_id=conversation_id)
    rec.record({"type": "user", "text": message})

    hot = load_hot_context(rt.vault).strip()
    framed = _frame_user_task(message, hot)

    try:
        llm = make_llm()
    except ProviderConfigError as e:
        yield {"type": "error", "content": str(e)}
        llm = ChatStub()  # type: ignore[assignment]

    agent = Agent(llm=llm)
    result = await agent.ainvoke(task=framed)
    final = {"type": "done", "content": getattr(result, "content", "")}
    rec.record(final)
    yield final


def _to_sse(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, str]]:
    async def _gen() -> AsyncIterator[dict[str, str]]:
        async for ev in events:
            yield {"event": ev["type"], "data": json.dumps(ev)}

    return _gen()


# Back-compat for tests that monkeypatch _stream_events.
_stream_events = _stream_chat


@router.post("")
async def post_chat(req: ChatRequest) -> Any:
    """Fast path — LLM round-trip only, no Mac control."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="empty message")
    events = _stream_chat(req.message, req.conversation_id)
    return EventSourceResponse(_to_sse(events))


@router.post("/control")
async def post_chat_control(req: ChatRequest) -> Any:
    """Slow path — full desktop agent. Needs Accessibility + Screen Recording perms."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="empty message")
    events = _stream_control(req.message, req.conversation_id)
    return EventSourceResponse(_to_sse(events))
