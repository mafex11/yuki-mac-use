"""type_tool grounds its feedback: honest about WHERE the text actually went.

Live run revealed type_tool returned 'Typed X at (x,y)' unconditionally — even
when it typed into the wrong app's chrome (no text field there). The model saw
'success' and moved on, then falsely reported the task done. These tests pin the
honest feedback that lets the model self-correct.
"""

from __future__ import annotations

from yuki.agent.desktop.views import DesktopState
from yuki.agent.tools.service import type_tool
from yuki.agent.tree.views import BoundingBox, Center, TreeElementNode, TreeState


class _FakeDesktop:
    """Minimal desktop double: records type() calls, exposes a desktop_state."""

    def __init__(self, nodes: list[TreeElementNode]) -> None:
        self.desktop_state = DesktopState(
            active_window=None,
            windows=[],
            tree_state=TreeState(interactive_nodes=nodes),
        )
        self.typed: list[tuple] = []

    def type(self, loc, text, caret_position="idle", clear=False, press_enter=False):
        self.typed.append((tuple(loc), text))


def _field(x: int, y: int, canonical: str, control_type: str = "AXTextField",
           name: str = "Field") -> TreeElementNode:
    return TreeElementNode(
        bounding_box=BoundingBox(x - 20, y - 10, x + 20, y + 10, 40, 20),
        center=Center(x, y),
        name=name,
        control_type=control_type,
        window_name="App",
        canonical=canonical,
    )


def test_typing_into_text_field_reports_success() -> None:
    d = _FakeDesktop([_field(100, 100, "url_bar", name="Address")])
    out = type_tool.function(loc=[100, 100], text="youtube.com", desktop=d)
    assert "youtube.com" in out
    assert "url_bar" in out
    assert d.typed == [((100, 100), "youtube.com")]


def test_typing_where_no_element_warns() -> None:
    # Coordinate hits nothing in the last state — likely wrong window / stale coords.
    d = _FakeDesktop([_field(100, 100, "url_bar")])
    out = type_tool.function(loc=[999, 999], text="hello", desktop=d)
    assert "NO interactive element" in out
    assert "wrong window" in out.lower() or "focused" in out.lower()
    # It still typed (we don't block), but the feedback is honest.
    assert d.typed == [((999, 999), "hello")]


def test_typing_into_non_text_element_warns() -> None:
    # Coordinate lands on a button, not a text field.
    d = _FakeDesktop([_field(50, 50, "button", control_type="AXButton", name="OK")])
    out = type_tool.function(loc=[50, 50], text="hello", desktop=d)
    assert "not a text input" in out
    assert "AXButton" in out
