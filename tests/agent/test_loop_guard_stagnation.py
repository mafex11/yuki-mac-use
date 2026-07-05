"""Stagnation only counts after UI-mutating tools — read-only steps are exempt."""

from __future__ import annotations

from yuki.agent.loop import LoopGuard


class _State:
    """Minimal DesktopState stand-in with a fixed fingerprint."""

    class _Win:
        bundle_id = "com.test.app"
        pid = 1
        name = "Test Window"

    active_window = _Win()
    tree_state = None


def _stagnate(g: LoopGuard, tool: str, times: int) -> None:
    state = _State()
    g.record_state(state)  # baseline
    for _ in range(times):
        g.record_action(tool, {"x": 1}, is_success=True)
        g.record_state(state)  # unchanged screen


def test_read_only_tools_do_not_trigger_stagnation_warning() -> None:
    g = LoopGuard()
    _stagnate(g, "read_app_note", times=6)
    warning = g.check() or ""
    assert "UI has not changed" not in warning


def test_ui_mutating_tools_still_trigger_stagnation_warning() -> None:
    g = LoopGuard()
    _stagnate(g, "click_tool", times=6)
    warning = g.check() or ""
    assert "UI has not changed" in warning


def test_change_summary_empty_after_read_only_tool() -> None:
    g = LoopGuard()
    state = _State()
    g.record_state(state)
    g.record_action("memory_tool", {"mode": "view"}, is_success=True)
    g.record_state(state)
    assert g.change_summary() == ""


def test_change_summary_reports_miss_after_click() -> None:
    g = LoopGuard()
    state = _State()
    g.record_state(state)
    g.record_action("click_tool", {"loc": [1, 2]}, is_success=True)
    g.record_state(state)
    assert "NO visible change" in g.change_summary()
