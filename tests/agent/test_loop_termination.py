"""should_continue() — defensive predicate for Anthropic-shaped responses."""

from __future__ import annotations

from yuki.agent.loop import should_continue


def _msg(content_blocks: list[dict[str, object]], stop_reason: str = "end_turn") -> object:
    """Mimic an Anthropic assistant message envelope."""
    return type("M", (), {"content": content_blocks, "stop_reason": stop_reason})()


def test_continue_when_tool_use_present_even_if_stop_reason_end_turn() -> None:
    msg = _msg(
        [
            {"type": "text", "text": "I'll click."},
            {"type": "tool_use", "id": "t1", "name": "click", "input": {}},
        ],
        stop_reason="end_turn",
    )
    assert should_continue(msg) is True


def test_stop_when_no_tool_use_blocks() -> None:
    msg = _msg([{"type": "text", "text": "Done."}], stop_reason="end_turn")
    assert should_continue(msg) is False


def test_stop_when_no_blocks_at_all() -> None:
    msg = _msg([], stop_reason="end_turn")
    assert should_continue(msg) is False


def test_stop_reason_max_tokens_with_tool_use_still_continues() -> None:
    msg = _msg(
        [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}],
        stop_reason="max_tokens",
    )
    assert should_continue(msg) is True
