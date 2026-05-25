"""clipboard_tool — read/write/history via NSPasteboard."""

from __future__ import annotations

from collections import deque
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool

_HISTORY: deque[str] = deque(maxlen=20)


def _pb_write(text: str) -> None:  # pragma: no cover
    from AppKit import (  # type: ignore[import-untyped]
        NSPasteboard,
        NSPasteboardTypeString,
    )

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _pb_read() -> str:  # pragma: no cover
    from AppKit import (
        NSPasteboard,
        NSPasteboardTypeString,
    )

    pb = NSPasteboard.generalPasteboard()
    return pb.stringForType_(NSPasteboardTypeString) or ""


@tool(name="clipboard", danger=DangerLevel.REVERSIBLE)
async def clipboard_tool(
    action: str,
    text: str = "",
) -> Any:
    """Read clipboard, write to it, or fetch in-process history (last 20)."""
    if action == "read":
        return _pb_read()
    if action == "write":
        _HISTORY.appendleft(text)
        _pb_write(text)
        return {"ok": True}
    if action == "history":
        return list(_HISTORY)
    raise ValueError(f"Unknown clipboard action: {action!r}")
