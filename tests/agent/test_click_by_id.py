"""click_tool/type_tool id-based targeting resolves nodes from the snapshot."""

from __future__ import annotations

from yuki.agent.tools.service import click_tool, type_tool
from yuki.agent.tree.views import BoundingBox, Center, TreeElementNode


def _node(display_id: int, name: str = "Play", x: int = 100, y: int = 200):
    bb = BoundingBox(left=x - 10, top=y - 10, right=x + 10, bottom=y + 10,
                     width=20, height=20)
    n = TreeElementNode(
        bounding_box=bb, center=Center(x=x, y=y), name=name,
        control_type="AXButton", window_name="Spotify", canonical="button",
    )
    n.display_id = display_id
    return n


class _Tree:
    def __init__(self, nodes):
        self.interactive_nodes = nodes


class _State:
    def __init__(self, nodes):
        self.tree_state = _Tree(nodes)


class _StubDesktop:
    def __init__(self, nodes):
        self.desktop_state = _State(nodes)
        self.clicked: list = []
        self.typed: list = []

    def node_by_display_id(self, display_id: int):
        for n in self.desktop_state.tree_state.interactive_nodes:
            if n.display_id == display_id:
                return n
        return None

    def click_element(self, node, button="left", clicks=1) -> str:
        self.clicked.append((node.display_id, button, clicks))
        return f"clicked {node.name!r} at ({node.center.x},{node.center.y})"

    def click(self, loc, button="left", clicks=1) -> None:
        self.clicked.append((tuple(loc), button, clicks))

    def type(self, loc, text, caret_position="idle", clear=False, press_enter=False):
        self.typed.append((tuple(loc), text))


def test_click_by_id_resolves_node() -> None:
    d = _StubDesktop([_node(0), _node(3, name="Search", x=300, y=50)])
    out = click_tool.function(id=3, desktop=d)
    assert d.clicked == [(3, "left", 1)]
    assert "Search" in out


def test_click_by_unknown_id_reports_without_clicking() -> None:
    d = _StubDesktop([_node(0)])
    out = click_tool.function(id=99, desktop=d)
    assert d.clicked == []
    assert "Nothing was clicked" in out
    assert "re-read" in out


def test_click_by_loc_still_works() -> None:
    d = _StubDesktop([])
    out = click_tool.function(loc=[10, 20], desktop=d)
    assert d.clicked == [((10, 20), "left", 1)]
    assert "(10,20)" in out


def test_click_with_neither_id_nor_loc() -> None:
    d = _StubDesktop([])
    out = click_tool.function(desktop=d)
    assert d.clicked == []
    assert "Nothing was clicked" in out


def test_type_by_id_targets_field_center() -> None:
    field = _node(1, name="Search box", x=300, y=50)
    field.control_type = "AXTextField"
    field.canonical = "search_field"
    d = _StubDesktop([field])
    out = type_tool.function(id=1, text="japanese", desktop=d)
    assert d.typed == [((300, 50), "japanese")]
    assert "search_field" in out or "Search box" in out


def test_type_by_unknown_id_types_nothing() -> None:
    d = _StubDesktop([])
    out = type_tool.function(id=7, text="hello", desktop=d)
    assert d.typed == []
    assert "Nothing was typed" in out
