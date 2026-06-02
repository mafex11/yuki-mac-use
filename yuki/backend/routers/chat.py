"""Chat router — two endpoints:

  POST /chat          — pure LLM round-trip (fast, no Mac control)
  POST /chat/control  — full MacOS-Use desktop agent (slow, needs permissions)

Both stream SSE events. /chat emits {type: token, text: ...} chunks during
generation and a final {type: done, content: ...} when complete. /chat/control
keeps the existing Agent.ainvoke shape (single done with full content).
"""

from __future__ import annotations

import json
import re as _re
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
    "use /chat/control instead — that surface has accessibility access. "
    "If the user states a durable personal fact about themselves, their "
    "tools, people, or projects (e.g. 'I always use Linear for tickets'), "
    "append it ONCE at the very end of your reply as "
    "<remember>the fact, rephrased concisely</remember>. Only for genuine, "
    "lasting facts — never for questions, chit-chat, or one-off requests."
)

_REMEMBER_RE = _re.compile(r"<remember>(.*?)</remember>", _re.IGNORECASE | _re.DOTALL)


def _split_capture(text: str) -> tuple[str, str | None]:
    """Return (visible_text, capture_suggestion|None), stripping the tag."""
    m = _REMEMBER_RE.search(text)
    if not m:
        return text, None
    suggestion = m.group(1).strip() or None
    visible = _REMEMBER_RE.sub("", text).strip()
    return visible, suggestion


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


def _configure_agent_for_model(agent, llm) -> None:
    """Turn on Tool RAG + lean AX-tree for small/local (Ollama) models.
    Cloud models keep full tools + full AX context (they handle it fine)."""
    provider = getattr(llm, "provider", "") or ""
    if provider != "ollama":
        return
    try:
        from yuki.agent.toolrag import ToolSelector
        from yuki.memory.embeddings import OllamaEmbedder

        agent.tool_selector = ToolSelector(
            agent.registry.get_tools(), embedder=OllamaEmbedder()
        )
    except Exception:
        agent.tool_selector = None  # degrade to all-tools; never block
    agent.ax_verbosity = "lean"


async def _stream_chat(
    message: str, conversation_id: str | None
) -> AsyncIterator[dict[str, Any]]:
    """Pure LLM round-trip with persistent global history."""
    import logging

    from yuki.memory import load_hot_context
    from yuki.messages import AIMessage, HumanMessage, SystemMessage
    from yuki.providers.factory import ProviderConfigError, make_llm
    from yuki.runtime.compaction import (
        append_history,
        compact_messages_async,
        get_tracker,
        load_history,
        replace_history,
    )

    log = logging.getLogger("yuki")

    rt = get_runtime()
    rec = TrajectoryRecorder(conversation_id=conversation_id)
    rec.record({"type": "user", "text": message})

    hot = load_hot_context(rt.vault).strip()
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

    tracker = get_tracker(model=getattr(llm, "model_name", "") or "")

    history = load_history()
    user_msg = HumanMessage(content=framed)
    messages: list = [SystemMessage(content=_BASE_SYSTEM_PROMPT), *history, user_msg]

    tracker.update(messages)
    if tracker.should_auto_compact:
        log.info(
            f"auto-compacting at {tracker.percent_used:.0f}% "
            f"({tracker.used_tokens} tokens)"
        )
        compacted = await compact_messages_async([*history, user_msg])
        # Persist the compacted form (without the system prompt; system is rebuilt every turn).
        compacted_no_sys = [m for m in compacted if not isinstance(m, SystemMessage)]
        replace_history(compacted_no_sys)
        messages = [SystemMessage(content=_BASE_SYSTEM_PROMPT), *compacted_no_sys]
        tracker.update(messages)

    try:
        result = await llm.ainvoke(messages=messages, tools=[])
    except Exception as e:
        err = {"type": "error", "content": f"LLM call failed: {e}"}
        rec.record(err)
        yield err
        return

    text = getattr(result, "content", None) or ""
    visible, capture = _split_capture(text)
    text = visible

    # Persist this turn (user msg + AI reply) to global history.
    try:
        append_history([user_msg, AIMessage(content=text)])
    except Exception as e:
        log.warning("history append failed: %s", e)

    # Update tracker now that the new turn is on disk.
    tracker.update([*messages, AIMessage(content=text)])

    final = {
        "type": "done",
        "content": text,
        "ctx_badge": tracker.badge(),
        "ctx_percent": int(tracker.percent_used),
        "capture_suggestion": capture,
    }
    rec.record(final)
    yield final


async def _stream_control(
    message: str, conversation_id: str | None
) -> AsyncIterator[dict[str, Any]]:
    """Full MacOS-Use desktop loop. Slow, needs accessibility/screen permissions."""
    import logging
    import time
    from datetime import UTC, datetime

    from yuki.agent import Agent
    from yuki.feedback.recorder import FailureMode, TaskRecord, append_task_record
    from yuki.memory import load_hot_context
    from yuki.providers.factory import ProviderConfigError, make_llm
    from yuki.providers.stub import ChatStub

    log = logging.getLogger("yuki")
    log.info("=" * 60)
    log.info(f"[/control] task: {message!r} (conv={conversation_id})")

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

    # Control tasks need a tool-capable model. Many local models (gemma3,
    # deepseek-r1, …) chat fine but can't call tools — Ollama 400s after the
    # agent burns retries. Catch it upfront with a clear, actionable message.
    if getattr(llm, "provider", "") == "ollama":
        from yuki.providers.factory import ollama_model_lacks_tools

        model_name = getattr(llm, "model_name", "") or ""
        if ollama_model_lacks_tools(model_name):
            yield {
                "type": "error",
                "content": (
                    f"{model_name} can't control your Mac — it doesn't support "
                    "tool calling. It works for chat, but for tasks switch to a "
                    "tool-capable model (e.g. qwen2.5:3b or llama3.2:3b) in "
                    "Settings → Provider."
                ),
            }
            return

    import asyncio as _asyncio

    from yuki.backend.event_bridge import QueueEventSubscriber, event_to_sse

    from yuki.providers.factory import agent_mode_for

    queue: _asyncio.Queue = _asyncio.Queue()
    # Small local models follow the lean "flash" prompt far better than the
    # full one (which overwhelms them into degenerate/empty tool calls).
    agent = Agent(llm=llm, mode=agent_mode_for(llm),
                  event_subscriber=QueueEventSubscriber(queue))
    _configure_agent_for_model(agent, llm)

    foreground_bundle = ""
    try:
        win = agent.desktop.get_foreground_window()
        if win:
            foreground_bundle = win.bundle_id or ""
    except Exception:
        foreground_bundle = ""
    log.info(f"[/control] foreground app: {foreground_bundle or '(none)'}")

    started = datetime.now(UTC)
    t0 = time.monotonic()
    outcome = "success"
    failure_mode = FailureMode.NONE
    content = ""

    task = _asyncio.create_task(agent.ainvoke(task=framed))
    try:
        while True:
            try:
                ev = await _asyncio.wait_for(queue.get(), timeout=0.25)
                ev_sse = event_to_sse(ev)
                if ev_sse.get("type") == "done":
                    continue
                yield ev_sse
            except _asyncio.TimeoutError:
                if task.done():
                    # Drain any events enqueued right before the agent returned,
                    # so the final tool steps aren't dropped.
                    while not queue.empty():
                        ev = queue.get_nowait()
                        ev_sse = event_to_sse(ev)
                        if ev_sse.get("type") == "done":
                            continue
                        yield ev_sse
                    break
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (_asyncio.CancelledError, Exception):
                pass

    if task.cancelled():
        outcome = "failure"
        failure_mode = FailureMode.PROVIDER_ERROR
        content = "task cancelled (client disconnected)"
    else:
        try:
            result = task.result()
            content = getattr(result, "content", "") or ""
            if not getattr(result, "is_done", True):
                outcome = "failure"
                failure_mode = FailureMode.AGENT_STEP_LIMIT
        except Exception as e:
            outcome = "failure"
            failure_mode = FailureMode.PROVIDER_ERROR
            content = f"agent error: {e}"

    duration_s = round(time.monotonic() - t0, 2)
    steps_used = getattr(getattr(agent, "state", None), "step", 0)
    apps_involved = [foreground_bundle] if foreground_bundle else []
    log.info(
        f"[/control] done in {duration_s}s "
        f"({steps_used} steps, outcome={outcome}, failure_mode={failure_mode.value})"
    )

    try:
        append_task_record(
            TaskRecord(
                task=message,
                conversation_id=conversation_id or "",
                started_at=started,
                duration_s=duration_s,
                steps_used=int(steps_used or 0),
                outcome=outcome,
                apps_involved=apps_involved,
                actions=[],
                failure_mode=failure_mode,
                recovery_attempts=0,
            )
        )
    except Exception:
        pass

    final = {"type": "done", "content": content}
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


@router.post("/compact")
async def post_compact() -> dict[str, Any]:
    """LLM-summarize the global chat history; replaces it with the summary."""
    from yuki.messages import SystemMessage
    from yuki.providers.factory import ProviderConfigError, make_llm
    from yuki.runtime.compaction import (
        compact_messages_async,
        get_tracker,
        load_history,
        replace_history,
    )

    history = load_history()
    if not history:
        tracker = get_tracker()
        tracker.update([])
        return {
            "ok": True,
            "compacted": False,
            "reason": "history empty",
            "ctx_badge": tracker.badge(),
            "ctx_percent": int(tracker.percent_used),
        }

    try:
        llm = make_llm()
        model = getattr(llm, "model_name", "") or ""
    except ProviderConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    tracker = get_tracker(model=model)
    compacted = await compact_messages_async(history, keep_recent=5)
    compacted_no_sys = [m for m in compacted if not isinstance(m, SystemMessage)]
    replace_history(compacted_no_sys)
    tracker.update(compacted_no_sys)
    return {
        "ok": True,
        "compacted": True,
        "ctx_badge": tracker.badge(),
        "ctx_percent": int(tracker.percent_used),
    }


@router.post("/clear")
async def post_clear() -> dict[str, Any]:
    """Wipe the global chat history. Resets context to 0%."""
    from yuki.runtime.compaction import clear_history, get_tracker

    clear_history()
    tracker = get_tracker()
    tracker.update([])
    return {
        "ok": True,
        "ctx_badge": tracker.badge(),
        "ctx_percent": int(tracker.percent_used),
    }


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Report current context usage without sending a message."""
    from yuki.runtime.compaction import get_tracker, load_history

    tracker = get_tracker()
    tracker.update(load_history())
    return {
        "ctx_badge": tracker.badge(),
        "ctx_percent": int(tracker.percent_used),
        "used_tokens": tracker.used_tokens,
        "window": tracker.window,
        "model": tracker.model,
    }
