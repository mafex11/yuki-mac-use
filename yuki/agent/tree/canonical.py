"""Universal AX element classifier.

For every interactive node returned by the AX walk, assign a stable canonical
role string the LLM can rely on across apps. Rules use AX attributes only --
no app-specific code, no bundle-id checks. Apps that follow the macOS AX
spec (which Apple requires) get classified; apps that don't get None and
fall back to generic AX info.
"""

from __future__ import annotations

import re

from yuki.agent.tree.views import TreeElementNode

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_SEARCH_RE = re.compile(r"\bsearch\b", re.IGNORECASE)
_ADDR_RE = re.compile(r"\b(address|url|location)\b", re.IGNORECASE)

_SUBMIT_NAMES = {"submit", "send", "go", "ok", "confirm", "search", "post"}
_CANCEL_NAMES = {"cancel", "close", "dismiss", "back"}

_TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}


def _meta(node: TreeElementNode, key: str) -> str:
    return str(node.metadata.get(key) or "")


def classify(node: TreeElementNode, *, is_focused: bool) -> str | None:
    """Return canonical role tag, or None if no rule matches."""
    role = node.control_type or ""
    name = (node.name or "").strip().lower()
    subrole = _meta(node, "subrole")
    role_desc = _meta(node, "role_description").lower()
    placeholder = _meta(node, "placeholder").lower()
    value = _meta(node, "value")

    axid = _meta(node, "axidentifier").lower()

    if role in ("AXTextField", "AXSearchField"):
        if _ADDR_RE.search(role_desc):
            return "url_bar"
        if "address" in axid or "url" in axid or "location" in axid or "omnibox" in axid:
            return "url_bar"
        if _ADDR_RE.search(name):
            return "url_bar"
        if "type a url" in placeholder or "search google or type" in placeholder:
            return "url_bar"
        if value and _URL_RE.match(value.strip()):
            return "url_bar"

    if role == "AXSearchField":
        return "search_field"
    if role == "AXTextField":
        if subrole == "AXSearchField":
            return "search_field"
        if _SEARCH_RE.search(placeholder):
            return "search_field"
        if "search" in axid:
            return "search_field"

    if is_focused and role in _TEXT_ROLES:
        return "primary_input"

    if role in _TEXT_ROLES:
        return "text_input"

    if role == "AXButton":
        if name in _SUBMIT_NAMES:
            return "submit_button"
        if name in _CANCEL_NAMES:
            return "cancel_button"

    if role == "AXLink":
        return "link"

    if node.metadata.get("in_tab_group") and role in ("AXRadioButton", "AXButton"):
        return "tab"

    return None
