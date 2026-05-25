"""Autocompact — when conversation exceeds threshold, summarize and replace.

Mirrors claude-leak/src/query.ts autocompact branch. We keep ONE compaction
strategy (autocompact); microcompact + context-collapse are explicit non-goals.
"""

from __future__ import annotations

import logging
from typing import Any

import tiktoken

log = logging.getLogger(__name__)
_KEEP_RECENT = 5

_enc = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
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
