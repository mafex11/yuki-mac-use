"""Universal AX classifier — full interactive-role coverage (Spec R, WS3).

Before this work the classifier tagged ~8 roles; everything else returned None,
so the model saw bare `AXCheckBox`/`AXSlider` rows with no semantic hook and no
state. These tests pin the expanded coverage: every interactive role gets a
canonical tag, and stateful controls expose their state.
"""

from __future__ import annotations

from yuki.agent.tree.canonical import classify
from yuki.agent.tree.views import BoundingBox, Center, TreeElementNode


def _node(
    control_type: str = "AXButton",
    name: str = "",
    metadata: dict | None = None,
) -> TreeElementNode:
    return TreeElementNode(
        bounding_box=BoundingBox(0, 0, 100, 30, 100, 30),
        center=Center(50, 15),
        name=name,
        control_type=control_type,
        window_name="App",
        metadata=metadata or {},
    )


# --- existing tags still work (regression guard) ---------------------------


def test_url_bar_by_role_description() -> None:
    n = _node("AXTextField", "Address", {"role_description": "address and search bar"})
    assert classify(n, is_focused=False) == "url_bar"


def test_search_field_by_subrole() -> None:
    n = _node("AXTextField", "Search", {"subrole": "AXSearchField"})
    assert classify(n, is_focused=False) == "search_field"


def test_primary_input_when_focused() -> None:
    n = _node("AXTextField", "Message", {"placeholder": "Type a message"})
    assert classify(n, is_focused=True) == "primary_input"


def test_submit_button() -> None:
    assert classify(_node("AXButton", "Send"), is_focused=False) == "submit_button"


def test_cancel_button() -> None:
    assert classify(_node("AXButton", "Cancel"), is_focused=False) == "cancel_button"


def test_link() -> None:
    assert classify(_node("AXLink", "example.com"), is_focused=False) == "link"


# --- NEW: generic button (was None before) ---------------------------------


def test_generic_button_gets_button_tag() -> None:
    # A plain "Reload" button matched no SUBMIT/CANCEL name → used to be None.
    assert classify(_node("AXButton", "Reload"), is_focused=False) == "button"


# --- NEW: checkboxes / toggles / switches with state -----------------------


def test_checkbox_unchecked() -> None:
    n = _node("AXCheckBox", "Remember me", {"value": 0})
    assert classify(n, is_focused=False) == "checkbox"


def test_toggle_via_switch_subrole() -> None:
    n = _node("AXCheckBox", "Bluetooth", {"subrole": "AXSwitch", "value": 1})
    assert classify(n, is_focused=False) == "toggle"


# --- NEW: radio button (outside a tab group) -------------------------------


def test_radio_button_tag() -> None:
    n = _node("AXRadioButton", "Option A", {"value": 0})
    assert classify(n, is_focused=False) == "radio_button"


def test_radio_in_tab_group_still_tab() -> None:
    n = _node("AXRadioButton", "Inbox", {"in_tab_group": True})
    assert classify(n, is_focused=False) == "tab"


# --- NEW: slider / stepper / popup / menu / disclosure / image -------------


def test_slider_tag() -> None:
    assert classify(_node("AXSlider", "Volume", {"value": 0.7}), is_focused=False) == "slider"


def test_stepper_tag() -> None:
    assert classify(_node("AXStepper", "Quantity"), is_focused=False) == "stepper"


def test_popup_button_tag() -> None:
    assert classify(_node("AXPopUpButton", "Country"), is_focused=False) == "popup_button"


def test_menu_item_tag() -> None:
    assert classify(_node("AXMenuItem", "New File"), is_focused=False) == "menu_item"


def test_disclosure_tag() -> None:
    assert classify(_node("AXDisclosureTriangle", "Advanced"), is_focused=False) == "disclosure"


def test_image_tag() -> None:
    assert classify(_node("AXImage", "logo"), is_focused=False) == "image"


# --- a truly unknown role still returns None -------------------------------


def test_unknown_role_returns_none() -> None:
    assert classify(_node("AXSomethingWeird", "x"), is_focused=False) is None
