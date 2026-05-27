"""LoopGuard.hard_stop_reason: triggers on 3 consecutive identical actions."""

from __future__ import annotations

from yuki.agent.loop import LoopGuard


def test_hard_stop_after_three_identical_actions() -> None:
    g = LoopGuard()
    g.record_action("click_tool", {"loc": [100, 200]}, is_success=False)
    assert g.hard_stop_reason() is None
    g.record_action("click_tool", {"loc": [100, 200]}, is_success=False)
    assert g.hard_stop_reason() is None
    g.record_action("click_tool", {"loc": [100, 200]}, is_success=False)
    reason = g.hard_stop_reason()
    assert reason is not None
    assert "click_tool" in reason
    assert "3" in reason


def test_hard_stop_resets_on_different_action() -> None:
    g = LoopGuard()
    g.record_action("click_tool", {"loc": [100, 200]}, is_success=False)
    g.record_action("click_tool", {"loc": [100, 200]}, is_success=False)
    g.record_action("type_tool", {"text": "x"}, is_success=False)  # different
    g.record_action("click_tool", {"loc": [100, 200]}, is_success=False)
    # Streak broken; only 1 consecutive click after the type.
    assert g.hard_stop_reason() is None


def test_hard_stop_ignores_thought_evaluate_plan_diffs() -> None:
    """Different evaluate/plan/thought should still count as same action."""
    g = LoopGuard()
    g.record_action(
        "click_tool",
        {"loc": [100, 200], "thought": "first try", "evaluate": "neutral", "plan": "A"},
        is_success=False,
    )
    g.record_action(
        "click_tool",
        {"loc": [100, 200], "thought": "second try", "evaluate": "fail", "plan": "B"},
        is_success=False,
    )
    g.record_action(
        "click_tool",
        {"loc": [100, 200], "thought": "third try", "evaluate": "fail", "plan": "C"},
        is_success=False,
    )
    assert g.hard_stop_reason() is not None


def test_done_tool_and_wait_tool_are_exempt() -> None:
    """Repeated wait_tool / done_tool calls should never trigger hard stop."""
    g = LoopGuard()
    for _ in range(5):
        g.record_action("wait_tool", {"duration": 1}, is_success=True)
    assert g.hard_stop_reason() is None


def test_reset_clears_hard_stop_state() -> None:
    g = LoopGuard()
    for _ in range(3):
        g.record_action("click_tool", {"loc": [1, 2]}, is_success=False)
    assert g.hard_stop_reason() is not None
    g.reset()
    assert g.hard_stop_reason() is None
