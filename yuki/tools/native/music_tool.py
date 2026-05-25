"""music_tool — control Music.app via AppleScript."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="music", danger=DangerLevel.REVERSIBLE)
async def music_tool(
    action: str,
    playlist: str = "",
) -> Any:
    """Control Apple Music: play, pause, next, previous, now_playing, play_playlist."""
    if action == "play":
        await osa("-e", 'tell application "Music" to play')
        return {"ok": True}
    if action == "pause":
        await osa("-e", 'tell application "Music" to pause')
        return {"ok": True}
    if action == "next":
        await osa("-e", 'tell application "Music" to next track')
        return {"ok": True}
    if action == "previous":
        await osa("-e", 'tell application "Music" to previous track')
        return {"ok": True}
    if action == "now_playing":
        out = await osa(
            "-e",
            'tell application "Music" to (name of current track) & " | " & '
            '(artist of current track) & " | " & (album of current track)',
        )
        parts = [p.strip() for p in out.split("|", 2)]
        while len(parts) < 3:
            parts.append("")
        return {"title": parts[0], "artist": parts[1], "album": parts[2]}
    if action == "play_playlist":
        await osa(
            "-e",
            f'tell application "Music" to play playlist "{_esc(playlist)}"',
        )
        return {"ok": True}
    raise ValueError(f"Unknown music action: {action!r}")
