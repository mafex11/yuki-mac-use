"""Media source — polls Spotify / Music for the now-playing track.

This is the taste signal: what the user actually listens to (and implicitly
skips — tracks that appear for <30s). AppleScript via static argv, same
pattern as the browser source; only running players are queried so we never
launch an app just to poll it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

_PLAYERS = ("Spotify", "Music")


async def _osa(*args: str) -> str:  # pragma: no cover — real macOS only
    proc = await asyncio.create_subprocess_exec(
        "osascript",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace").strip()


async def _default_now_playing() -> dict[str, str] | None:  # pragma: no cover
    for player in _PLAYERS:
        running = await _osa(
            "-e",
            f'tell application "System Events" to (name of processes) contains "{player}"',
        )
        if running != "true":
            continue
        out = await _osa(
            "-e",
            f'tell application "{player}" to if player state is playing then '
            '(name of current track) & "\\n" & (artist of current track) & "\\n" '
            "& (album of current track)",
        )
        if not out:
            continue
        parts = out.split("\n")
        while len(parts) < 3:
            parts.append("")
        return {
            "player": player,
            "track": parts[0],
            "artist": parts[1],
            "album": parts[2],
        }
    return None


class MediaSource(Source):
    """Emits MEDIA_PLAYING when the current track changes."""

    name = "media"

    def __init__(
        self,
        now_playing: Any = None,
        poll_seconds: float = 15.0,
    ) -> None:
        super().__init__()
        self._now_playing = now_playing or _default_now_playing
        self._poll = poll_seconds
        self._last: tuple[str, str] | None = None

    async def iterate(self, buffer: RingBuffer) -> None:
        info = await self._now_playing()
        if info and info.get("track"):
            key = (info["track"], info.get("artist", ""))
            if key != self._last:
                self._last = key
                await buffer.push(
                    Event(
                        ts=datetime.now(UTC),
                        kind=EventKind.MEDIA_PLAYING,
                        payload=info,
                    )
                )
        else:
            self._last = None
        await asyncio.sleep(self._poll)
