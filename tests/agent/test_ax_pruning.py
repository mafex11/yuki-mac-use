# tests/agent/test_ax_pruning.py
"""interactive_elements_to_string lean mode caps nodes + trims metadata."""
from __future__ import annotations

from yuki.agent.tree.views import BoundingBox, Center, TreeElementNode, TreeState


def _bbox(idx: int) -> BoundingBox:
    return BoundingBox(left=idx, top=idx, right=idx + 10, bottom=idx + 10,
                       width=10, height=10)


def _node(idx: int, focused: bool = False, canonical: str = "submit_button",
          name: str | None = None, control_type: str = "AXButton",
          value: str = "v") -> TreeElementNode:
    # TreeElementNode requires bounding_box (first field) + center.
    return TreeElementNode(
        bounding_box=_bbox(idx),
        center=Center(x=idx, y=idx),
        name=name if name is not None else f"node{idx}",
        control_type=control_type,
        window_name="Win",
        canonical=canonical,
        is_focused=focused,
        metadata={"value": value, "placeholder": "p", "noise": "x" * 50},
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


def test_lean_mode_clips_huge_node_name() -> None:
    # A text-heavy app (terminal/editor) can report a name that is its ENTIRE
    # content — tens of thousands of chars. Lean mode must clip it so one node
    # can't flood the agent's context and break small-model tool-calling.
    huge = "Z" * 50_000
    ts = TreeState(interactive_nodes=[_node(0, name=huge)], status=True)
    out = ts.interactive_elements_to_string(verbosity="lean")
    assert len(out) < 1000          # bounded, not 50k
    assert "…" in out              # truncation marker present
    assert "ZZZ" in out            # the start is preserved


def test_lean_mode_drops_dock_and_menubar_chrome() -> None:
    # Dock items + menu-bar items are never task targets; lean mode must drop
    # them so they don't fill the node budget with distractors.
    nodes = [
        _node(0, name="Calculator", control_type="AXDockItem"),
        _node(1, name="Bluetooth", control_type="AXMenuBarItem"),
        _node(2, name="Real Button", control_type="AXButton"),
    ]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="lean")
    assert "AXDockItem" not in out
    assert "AXMenuBarItem" not in out
    assert "Real Button" in out


def test_full_mode_keeps_chrome_and_full_names() -> None:
    # Full mode (cloud models) is unchanged: chrome stays, names not clipped.
    huge = "Z" * 5_000
    nodes = [
        _node(0, name=huge),
        _node(1, name="Dock thing", control_type="AXDockItem"),
    ]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="full")
    assert "AXDockItem" in out
    assert huge in out             # not clipped in full mode


def test_full_mode_hard_caps_huge_screens() -> None:
    # A giant Electron app (claw-layerpath, Arc) can expose hundreds of AX nodes.
    # Full mode used to dump ALL of them with full metadata, blowing past even a
    # 128k context (observed: 272k tokens → gpt-4o 400s before step 1). Full mode
    # must hard-cap node count too, and SAY it truncated (no silent drop).
    nodes = [_node(i) for i in range(400)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="full", hard_cap=150)
    assert out.count("AXButton") <= 150
    assert "truncated" in out.lower() or "showing" in out.lower()


def test_full_mode_small_screen_not_truncated() -> None:
    # Under the cap, full mode is unchanged — no truncation note, all nodes.
    nodes = [_node(i) for i in range(10)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="full", hard_cap=150)
    assert out.count("AXButton") == 10
    assert "truncated" not in out.lower()


def test_lean_mode_keeps_state_metadata() -> None:
    # Spec R WS3: lean mode must surface element STATE (checked/selected/
    # expanded), not just value/placeholder — otherwise the model can't tell a
    # toggle's on/off position. Previously these keys were trimmed away.
    n = TreeElementNode(
        bounding_box=_bbox(0),
        center=Center(x=0, y=0),
        name="Bluetooth",
        control_type="AXCheckBox",
        window_name="System Settings",
        canonical="toggle",
        is_focused=False,
        metadata={"checked": False, "noise": "x" * 50},
    )
    ts = TreeState(interactive_nodes=[n], status=True)
    out = ts.interactive_elements_to_string(verbosity="lean")
    assert "checked" in out        # state surfaced
    assert "toggle" in out         # canonical tag surfaced
    assert "noise" not in out      # genuine noise still trimmed
