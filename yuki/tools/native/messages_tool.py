"""messages_tool — iMessage via AppleScript (experimental)."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="messages", danger=DangerLevel.EXTERNAL, experimental=True)
async def messages_tool(
    action: str,
    recipient: str = "",
    body: str = "",
    limit: int = 10,
) -> Any:
    """Send iMessage or fetch recent (experimental — AppleScript surface is fragile)."""
    if action == "send_to":
        script = (
            f'tell application "Messages"\n'
            f"  set targetService to 1st service whose service type = iMessage\n"
            f'  set targetBuddy to buddy "{_esc(recipient)}" of targetService\n'
            f'  send "{_esc(body)}" to targetBuddy\n'
            f"end tell"
        )
        await osa("-e", script)
        return {"sent": True}
    if action == "recent":
        return {
            "note": "iMessage read API is not exposed via AppleScript",
            "messages": [],
        }
    raise ValueError(f"Unknown messages action: {action!r}")
