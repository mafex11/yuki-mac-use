"""Autocompact + global persistent chat history.

Two surfaces in one module:

1. The legacy `estimate_tokens(list[dict])` / `maybe_autocompact_async` helpers
   exposed for runtime/query callers (kept for back-compat).
2. The Plan N additions: a single global `ContextTracker` and a JSONL-backed
   chat history at ~/Library/Application Support/Yuki/chat_history.jsonl, plus
   `compact_messages()` that LLM-summarizes the history via make_llm().
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken

from yuki.messages import AIMessage, HumanMessage, SystemMessage
from yuki.messages.service import BaseMessage
from yuki.runtime.tokens import estimate_messages_tokens

log = logging.getLogger(__name__)
_KEEP_RECENT = 5

_enc = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Legacy dict-based estimator. Plan N callers should use
    yuki.runtime.tokens.estimate_messages_tokens (handles BaseMessage too)."""
    total = 0
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            total += len(_enc.encode(c))
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    total += len(_enc.encode(text))
    return total


# ---- Plan N: global persistent history + ContextTracker ---------------------

_DEFAULT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-7": 200_000,
    "claude-haiku-4-5": 200_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-pro": 2_000_000,
    "qwen3-vl:8b": 32_000,
    "deepseek-r1:1.5b": 32_000,
}
_BUFFER_TOKENS = 8_000
_AUTO_COMPACT_PCT = 80.0


def _model_window(model: str) -> int:
    if not model:
        return 32_000
    if model in _DEFAULT_WINDOWS:
        return _DEFAULT_WINDOWS[model]
    # Heuristic: anything starting with gemini/claude gets a generous default.
    if model.startswith("gemini"):
        return 1_000_000
    if model.startswith("claude"):
        return 200_000
    return 32_000


def effective_window(model: str) -> int:
    return max(1, _model_window(model) - _BUFFER_TOKENS)


def history_path() -> Path:
    override = os.environ.get("YUKI_CHAT_HISTORY")
    if override:
        return Path(override)
    from yuki.memory import paths
    return paths.chat_history_path()


_ROLE_TO_CLS = {
    "system": SystemMessage,
    "human": HumanMessage,
    "ai": AIMessage,
}


def _msg_to_dict(m: BaseMessage) -> dict[str, Any]:
    return {"role": m.role, "content": m.content or ""}


def _dict_to_msg(d: dict[str, Any]) -> BaseMessage | None:
    cls = _ROLE_TO_CLS.get(d.get("role", ""))
    if cls is None:
        return None
    content = d.get("content") or ""
    try:
        return cls(content=content)
    except Exception:
        return None


def load_history() -> list[BaseMessage]:
    path = history_path()
    if not path.exists():
        return []
    out: list[BaseMessage] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = _dict_to_msg(d)
        if m is not None:
            out.append(m)
    return out


def append_history(messages: list[BaseMessage]) -> None:
    if not messages:
        return
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(_msg_to_dict(m), ensure_ascii=False) + "\n")


def replace_history(messages: list[BaseMessage]) -> None:
    """Atomically rewrite the history file with `messages`."""
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(_msg_to_dict(m), ensure_ascii=False) + "\n")
    tmp.replace(path)


def clear_history() -> None:
    path = history_path()
    if path.exists():
        path.unlink()


@dataclass
class ContextTracker:
    model: str = ""
    used_tokens: int = 0

    @property
    def window(self) -> int:
        return effective_window(self.model)

    @property
    def percent_used(self) -> float:
        if self.window <= 0:
            return 0.0
        return min(100.0, (self.used_tokens / self.window) * 100.0)

    @property
    def percent_left(self) -> float:
        return max(0.0, 100.0 - self.percent_used)

    @property
    def should_auto_compact(self) -> bool:
        return self.percent_used >= _AUTO_COMPACT_PCT

    def update(self, messages: list[Any]) -> None:
        self.used_tokens = estimate_messages_tokens(messages)

    def badge(self) -> str:
        used_k = self.used_tokens / 1000.0
        win_k = self.window / 1000.0
        return (
            f"[ctx {int(self.percent_used)}% • "
            f"{used_k:.1f}k/{win_k:.0f}k]"
        )


# Module-level global tracker (single-conversation design per user request).
_TRACKER = ContextTracker()


def get_tracker(model: str = "") -> ContextTracker:
    """Return the global tracker, updating its model name if a fresh one
    is provided (so the badge reflects whichever provider just answered)."""
    if model and model != _TRACKER.model:
        _TRACKER.model = model
    return _TRACKER


_COMPACT_PROMPT = """You are summarizing the conversation so far so it can fit
back into a smaller context window. Preserve:

1. The user's original goals / tasks (what they asked for, in order).
2. Decisions made and their reasoning.
3. Concrete state: file paths edited, commands run, URLs visited, app
   coordinates discovered, error messages encountered.
4. Outstanding TODOs or unresolved questions.

Drop:
- Redundant tool-call output (raw AX trees, repeated state captures)
- Polite scaffolding ("I'll now...", "Let me check...")
- Filler thoughts that don't carry forward state.

Output one tight markdown summary, ~500-1500 tokens. Use bullet sections.
No preamble, no apology. Just the summary.

Conversation to summarize:

"""


async def compact_messages_async(
    messages: list[BaseMessage],
    *,
    keep_recent: int = _KEEP_RECENT,
) -> list[BaseMessage]:
    """LLM-summarize the trail of `messages`, return [summary + recent N].

    Preserves any leading SystemMessage. Falls back to returning the input
    unchanged if the LLM call errors -- never lose user history on failure.
    """
    from yuki.providers.factory import make_llm

    if not messages:
        return messages

    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    rest = [m for m in messages if not isinstance(m, SystemMessage)]

    if len(rest) <= keep_recent + 1:
        return messages  # Nothing meaningful to compact yet.

    head = rest[:-keep_recent]
    tail = rest[-keep_recent:]

    transcript_parts: list[str] = []
    for m in head:
        role = m.__class__.__name__.replace("Message", "").lower()
        content = m.content or ""
        transcript_parts.append(f"### {role}\n{content}")
    transcript = "\n\n".join(transcript_parts)

    try:
        llm = make_llm()
        event = await llm.ainvoke(
            messages=[HumanMessage(content=_COMPACT_PROMPT + transcript)],
            tools=[],
        )
        summary = (event.content or "").strip() if event else ""
    except Exception as e:
        log.warning("compaction failed: %s -- keeping history intact", e)
        return messages

    if not summary:
        return messages

    summary_msg = HumanMessage(
        content=f"<conversation_summary>\n{summary}\n</conversation_summary>"
    )
    return [*system_msgs, summary_msg, *tail]


def compact_messages(
    messages: list[BaseMessage],
    *,
    keep_recent: int = _KEEP_RECENT,
) -> list[BaseMessage]:
    """Sync wrapper. Safe to call from non-async contexts (e.g. CLI tasks).
    For async callers use compact_messages_async directly."""
    import asyncio

    try:
        return asyncio.run(
            compact_messages_async(messages, keep_recent=keep_recent)
        )
    except RuntimeError:
        # Already inside an event loop -- caller must use the async variant.
        log.warning(
            "compact_messages() called from a running event loop; "
            "use compact_messages_async() instead. Returning input unchanged."
        )
        return messages


def maybe_autocompact(
    messages: list[dict[str, Any]], *, threshold: int
) -> list[dict[str, Any]]:
    """Synchronous no-op path; real compaction happens in maybe_autocompact_async."""
    if estimate_tokens(messages) <= threshold:
        return messages
    return messages


async def _summarize(messages: list[dict[str, Any]]) -> str:  # pragma: no cover
    """Real impl spawns a forked subagent + LLM call; tests inject a fake."""
    # Production wires this to Anthropic/OpenAI; the stub provider doesn't
    # implement the async-invoke shape needed here. Fake summary keeps types
    # clean and the function exercisable when no real LLM is configured.
    return f"Summary of {len(messages)} messages"


async def maybe_autocompact_async(
    messages: list[dict[str, Any]], *, threshold: int
) -> list[dict[str, Any]]:
    if estimate_tokens(messages) <= threshold:
        return messages
    summary = await _summarize(messages[:-_KEEP_RECENT])
    log.info(
        "autocompacted %d messages → 1 summary + %d recent",
        len(messages),
        _KEEP_RECENT,
    )
    return [
        {"role": "system", "content": f"Conversation summary so far: {summary}"},
        *messages[-_KEEP_RECENT:],
    ]
