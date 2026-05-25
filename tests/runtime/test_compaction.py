"""Compaction: estimate, no-op below threshold, async compact above."""

from __future__ import annotations

from typing import Any

import pytest

from yuki.runtime.compaction import (
    estimate_tokens,
    maybe_autocompact,
    maybe_autocompact_async,
)


def test_estimate_tokens_returns_positive() -> None:
    msgs = [{"role": "user", "content": "hello world"}]
    assert estimate_tokens(msgs) > 0


def test_below_threshold_no_compact() -> None:
    msgs: list[dict[str, Any]] = [{"role": "user", "content": "x"}]
    out = maybe_autocompact(msgs, threshold=10_000)
    assert out is msgs


async def test_above_threshold_triggers_compact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    big: list[dict[str, Any]] = [{"role": "user", "content": "x" * 200}] * 100

    async def fake_summarize(msgs: list[dict[str, Any]]) -> str:
        return "Summary: lots of x"

    monkeypatch.setattr("yuki.runtime.compaction._summarize", fake_summarize)
    out = await maybe_autocompact_async(big, threshold=100)
    assert len(out) < len(big)
    assert any("Summary" in str(m.get("content", "")) for m in out)
