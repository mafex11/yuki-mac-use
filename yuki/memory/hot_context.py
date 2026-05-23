"""Hot context: identity notes always injected into the system prompt.

Spec §4.4 — every chat call ships ~1-2KB of identity. Anthropic prompt caching
keeps the per-call cost near zero.
"""

from __future__ import annotations

from yuki.memory.vault import Vault


def load_hot_context(vault: Vault, max_chars: int = 4000) -> str:
    """Return concatenated identity notes ready for the system prompt."""
    parts: list[str] = []
    for note, body in vault.list_section("00-Identity"):
        title = getattr(note, "name", note.id)
        parts.append(f"## {title}\n\n{body.strip()}\n")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
