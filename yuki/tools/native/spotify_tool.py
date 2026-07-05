"""spotify_tool — control Spotify.app via AppleScript + URI schemes."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="spotify", danger=DangerLevel.REVERSIBLE)
async def spotify_tool(
    action: str,
    uri: str = "",
    query: str = "",
) -> Any:
    """Control Spotify directly: play, pause, next, previous, now_playing,
    play_uri (track/album/playlist spotify: URI), search (opens results in app).

    - play/pause/next/previous: playback transport, no UI interaction needed.
    - now_playing: returns current track, artist, album and player state.
    - play_uri: starts playback of a spotify:track:/spotify:album:/spotify:playlist: URI immediately.
    - search: opens spotify:search:<query> inside the app; the results then
      appear on screen for selection. Use when you don't know the URI —
      e.g. to find a user playlist by name, search its name, then click the
      playlist in the results and press its Play button.
    """
    if action == "play":
        await osa("-e", 'tell application "Spotify" to play')
        return {"ok": True}
    if action == "pause":
        await osa("-e", 'tell application "Spotify" to pause')
        return {"ok": True}
    if action == "next":
        await osa("-e", 'tell application "Spotify" to next track')
        return {"ok": True}
    if action == "previous":
        await osa("-e", 'tell application "Spotify" to previous track')
        return {"ok": True}
    if action == "now_playing":
        out = await osa(
            "-e",
            'tell application "Spotify" to (name of current track) & " | " & '
            '(artist of current track) & " | " & (album of current track) & " | " & '
            "(player state as text)",
        )
        parts = [p.strip() for p in out.split("|", 3)]
        while len(parts) < 4:
            parts.append("")
        return {
            "title": parts[0],
            "artist": parts[1],
            "album": parts[2],
            "state": parts[3],
        }
    if action == "play_uri":
        if not uri.startswith("spotify:"):
            raise ValueError(f"uri must be a spotify: URI, got {uri!r}")
        await osa(
            "-e",
            f'tell application "Spotify" to play track "{_esc(uri)}"',
        )
        state = await osa(
            "-e", 'tell application "Spotify" to player state as text'
        )
        return {"ok": state == "playing", "player_state": state}
    if action == "search":
        if not query:
            raise ValueError("query is required for search")
        encoded = query.replace(" ", "%20")
        await osa(
            "-e",
            f'tell application "Spotify" to open location "spotify:search:{_esc(encoded)}"',
        )
        await osa("-e", 'tell application "Spotify" to activate')
        return {
            "ok": True,
            "note": "Search results are now visible in the Spotify window. "
            "Read the Desktop State to select a result.",
        }
    raise ValueError(f"Unknown spotify action: {action!r}")
