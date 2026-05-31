"""Token estimation utilities.

Uses tiktoken's cl100k_base (Anthropic and OpenAI tokenize similarly enough
for an estimator). Falls back to chars/4 if tiktoken can't load.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def _count(text: str) -> int:
        if not text:
            return 0
        return len(_enc.encode(text))
except Exception as e:  # pragma: no cover -- tiktoken always installs
    log.warning("tiktoken unavailable, falling back to chars/4: %s", e)

    def _count(text: str) -> int:
        if not text:
            return 0
        return (len(text) + 3) // 4


_PER_MESSAGE_OVERHEAD = 8


def estimate_text_tokens(text: str) -> int:
    return _count(text)


def estimate_messages_tokens(messages: list[Any]) -> int:
    """Count tokens for a list of BaseMessage instances OR dicts.

    BaseMessage path: read .content (str | list).
    Dict path: read 'content' key.
    """
    total = 0
    for m in messages:
        content: Any
        if isinstance(m, dict):
            content = m.get("content", "")
        else:
            content = getattr(m, "content", "")

        if isinstance(content, str):
            total += _count(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    total += _count(part)
                elif isinstance(part, dict):
                    total += _count(str(part.get("text", "")))
                else:
                    total += _count(str(part))
        else:
            total += _count(str(content))
        total += _PER_MESSAGE_OVERHEAD
    return total
