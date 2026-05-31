"""POST /route — classify a user message as 'chat' or 'control'.

LLM-first with a deterministic heuristic fallback so the UI never stalls.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("yuki")
router = APIRouter(prefix="/route", tags=["route"])

_ACTION_VERBS = {
    "open", "close", "click", "type", "send", "message", "search", "find",
    "play", "pause", "scroll", "switch", "launch", "quit", "copy", "paste",
    "screenshot", "navigate", "go", "fill", "submit", "download", "delete",
    "rename", "move", "drag", "select", "press",
}


class RouteRequest(BaseModel):
    message: str


def _heuristic_route(message: str) -> str:
    first = re.findall(r"[a-z']+", message.lower())[:3]
    if any(w in _ACTION_VERBS for w in first):
        return "control"
    return "chat"


_PROMPT = """Classify the user's request as either "chat" or "control".

- "control": the user wants you to DO something on their Mac (open apps, send
  messages, click, type, automate, find/play media, manipulate files).
- "chat": the user is asking a question or wants information, with no action
  on their machine.

Examples:
- "open whatsapp and message mom" -> control
- "what's the weather" -> chat
- "find me an interesting video and play it" -> control
- "explain quantum tunneling" -> chat

Respond with ONLY one word: chat or control.

User request: {message}"""


@router.post("")
async def post_route(req: RouteRequest) -> dict[str, Any]:
    msg = req.message.strip()
    if not msg:
        return {"route": "chat", "reason": "empty"}
    try:
        from yuki.messages import HumanMessage
        from yuki.providers.factory import make_llm
        llm = make_llm()
        event = await llm.ainvoke(
            messages=[HumanMessage(content=_PROMPT.format(message=msg))],
            tools=[],
        )
        text = (event.content or "").strip().lower() if event else ""
        if "control" in text:
            return {"route": "control", "reason": "llm"}
        if "chat" in text:
            return {"route": "chat", "reason": "llm"}
    except Exception as e:
        log.warning("route classifier llm failed: %s; using heuristic", e)
    return {"route": _heuristic_route(msg), "reason": "heuristic"}
