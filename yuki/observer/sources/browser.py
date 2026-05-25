"""Browser source — emits URL_CHANGE when a browser is focused.

Production uses asyncio.create_subprocess_exec with osascript and a static
arg list; no user-controlled string is interpolated. Tests inject get_url.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

_BROWSERS = {"Safari", "Google Chrome", "Firefox", "Microsoft Edge"}


async def _osa(*args: str) -> str:  # pragma: no cover — real macOS only
    proc = await asyncio.create_subprocess_exec(
        "osascript",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace").strip()


async def _default_get_url() -> tuple[str | None, str | None]:  # pragma: no cover
    app = await _osa(
        "-e",
        'tell application "System Events" to set fname to '
        "name of first process whose frontmost is true",
    )
    if app not in _BROWSERS:
        return None, None
    if app == "Safari":
        url = await _osa(
            "-e", 'tell application "Safari" to URL of current tab of front window'
        )
    else:
        url = await _osa(
            "-e", f'tell application "{app}" to URL of active tab of front window'
        )
    return (url or None), app


class BrowserSource(Source):
    name = "browser"

    def __init__(
        self,
        get_url: Callable[[], Awaitable[tuple[str | None, str | None]]] | None = None,
    ) -> None:
        super().__init__()
        self._get_url = get_url or _default_get_url
        self._last_url: str | None = None

    async def iterate(self, buffer: RingBuffer) -> None:
        url, app = await self._get_url()
        if not url or not app:
            self._last_url = None
            return
        if url == self._last_url:
            return
        self._last_url = url
        await buffer.push(
            Event(
                ts=datetime.now(UTC),
                kind=EventKind.URL_CHANGE,
                payload={"url": url, "browser": app},
            )
        )
