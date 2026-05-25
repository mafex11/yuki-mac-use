"""notes_tool — AppleScript wrapper around Notes.app."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="notes", danger=DangerLevel.DESTRUCTIVE)
async def notes_tool(
    action: str,
    title: str = "",
    body: str = "",
) -> Any:
    """List notes, create a note, read a note's body, or delete a note."""
    if action == "list":
        out = await osa("-e", 'tell application "Notes" to get name of every note')
        return out.splitlines() if "\n" in out else [
            t.strip() for t in (out or "").split(",") if t.strip()
        ]
    if action == "create":
        script = (
            f'tell application "Notes" to make new note '
            f'with properties {{name:"{_esc(title)}", body:"{_esc(body)}"}}'
        )
        await osa("-e", script)
        return {"created": True}
    if action == "read":
        return await osa(
            "-e", f'tell application "Notes" to get body of note "{_esc(title)}"'
        )
    if action == "delete":
        await osa(
            "-e", f'tell application "Notes" to delete note "{_esc(title)}"'
        )
        return {"deleted": True}
    raise ValueError(f"Unknown notes action: {action!r}")
