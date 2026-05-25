"""mail_tool — AppleScript wrapper around Mail.app."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="mail", danger=DangerLevel.EXTERNAL)
async def mail_tool(
    action: str,
    to: str = "",
    subject: str = "",
    body: str = "",
    limit: int = 10,
) -> Any:
    """List unread mail or send a new message via Mail.app."""
    if action == "list_unread":
        script = (
            'tell application "Mail" to get '
            "{sender, subject} of (messages of inbox whose read status is false)"
        )
        out = await osa("-e", script)
        rows: list[dict[str, str]] = []
        for line in out.splitlines():
            parts = line.split("|", 1)
            if len(parts) == 2:
                rows.append({"sender": parts[0].strip(), "subject": parts[1].strip()})
        return rows[:limit]
    if action == "send":
        script = (
            f'tell application "Mail"\n'
            f"  set m to make new outgoing message with properties "
            f'{{subject:"{_esc(subject)}", content:"{_esc(body)}", visible:false}}\n'
            f"  tell m to make new to recipient with properties "
            f'{{address:"{_esc(to)}"}}\n'
            f"  send m\n"
            f"end tell"
        )
        await osa("-e", script)
        return {"sent": True}
    raise ValueError(f"Unknown mail action: {action!r}")
