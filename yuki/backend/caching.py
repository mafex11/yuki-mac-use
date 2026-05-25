"""Prompt-cache markers for Anthropic.

Spec §11.2: identity hot context + system prompt repeat across calls. Marking
both with cache_control=ephemeral cuts repeat-token cost by ~90%.
"""

from __future__ import annotations

from typing import Any


def build_cached_system_blocks(
    *, base_prompt: str, hot_context: str
) -> list[dict[str, Any]]:
    """Compose Anthropic-shaped system blocks with cache_control markers."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": base_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if hot_context.strip():
        blocks.append(
            {
                "type": "text",
                "text": f"<identity>\n{hot_context}\n</identity>",
                "cache_control": {"type": "ephemeral"},
            }
        )
    return blocks
