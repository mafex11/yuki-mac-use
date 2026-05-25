"""Caching: cached system blocks shape."""

from __future__ import annotations

from yuki.backend.caching import build_cached_system_blocks


def test_returns_two_blocks_when_hot_context_present() -> None:
    blocks = build_cached_system_blocks(
        base_prompt="You are Yuki.",
        hot_context="## Profile\n\nName: Sudhanshu",
    )
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert "Sudhanshu" in blocks[1]["text"]


def test_single_block_when_no_hot_context() -> None:
    blocks = build_cached_system_blocks(base_prompt="You are Yuki.", hot_context="")
    assert len(blocks) == 1
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_long_context_still_one_cache_marker_each() -> None:
    blocks = build_cached_system_blocks(base_prompt="x" * 5000, hot_context="y" * 3000)
    assert all(b["cache_control"] == {"type": "ephemeral"} for b in blocks)
