"""meeting_tool — Zoom/Meet/Teams detection and basic control (experimental)."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool

_MEETING_APPS = {"zoom.us", "Microsoft Teams", "Microsoft Teams (work or school)"}


async def _frontmost() -> str:
    return await osa(
        "-e",
        'tell application "System Events" to set f to '
        "name of first process whose frontmost is true",
    )


@tool(name="meeting", danger=DangerLevel.EXTERNAL, experimental=True)
async def meeting_tool(action: str) -> Any:
    """Detect or control the current meeting (experimental)."""
    app = await _frontmost()
    in_meeting = app in _MEETING_APPS
    if action == "current":
        return {"app": app, "in_meeting": in_meeting}
    if action == "toggle_mute":
        if not in_meeting:
            return {"ok": False, "reason": "no meeting app frontmost"}
        await osa(
            "-e",
            'tell application "System Events" to keystroke "a" using {shift down, command down}',
        )
        return {"ok": True}
    if action == "leave":
        if not in_meeting:
            return {"ok": False, "reason": "no meeting app frontmost"}
        await osa(
            "-e",
            'tell application "System Events" to keystroke "w" using {command down}',
        )
        return {"ok": True}
    raise ValueError(f"Unknown meeting action: {action!r}")
