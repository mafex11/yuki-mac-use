# tests/agent/test_ax_pruning.py
"""interactive_elements_to_string lean mode caps nodes + trims metadata."""
from __future__ import annotations

from yuki.agent.tree.views import TreeState, TreeElementNode, Center, BoundingBox


def _bbox(idx: int) -> BoundingBox:
    return BoundingBox(left=idx, top=idx, right=idx + 10, bottom=idx + 10,
                       width=10, height=10)


def _node(idx: int, focused: bool = False, canonical: str = "submit_button") -> TreeElementNode:
    # TreeElementNode requires bounding_box (first field) + center.
    return TreeElementNode(
        bounding_box=_bbox(idx),
        center=Center(x=idx, y=idx),
        name=f"node{idx}",
        control_type="AXButton",
        window_name="Win",
        canonical=canonical,
        is_focused=focused,
        metadata={"value": "v", "placeholder": "p", "noise": "x" * 50},
    )


def test_full_mode_unchanged_includes_all_nodes() -> None:
    nodes = [_node(i) for i in range(40)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="full")
    assert out.count("AXButton") == 40


def test_lean_mode_caps_nodes() -> None:
    nodes = [_node(i) for i in range(40)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="lean", max_nodes=25)
    assert out.count("AXButton") <= 25


def test_lean_mode_trims_noise_metadata() -> None:
    nodes = [_node(0)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="lean")
    assert "noise" not in out
    assert "v" in out


def test_lean_mode_keeps_focused_block() -> None:
    # Use canonical="primary_input" to trigger focused block emission
    nodes = [_node(0, focused=True, canonical="primary_input")]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="lean")
    assert "<focused_input>" in out
