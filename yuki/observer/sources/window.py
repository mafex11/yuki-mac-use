"""Window source — emits WINDOW_FOCUS and WINDOW_TITLE via AX notifications."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class WindowSource(Source):
    name = "window"

    def __init__(self) -> None:
        super().__init__()
        self._last_title: str | None = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _handle(self, info: dict[str, Any], buffer: RingBuffer) -> None:
        ts = datetime.now(UTC)
        app = str(info.get("app", ""))
        await buffer.push(
            Event(ts=ts, kind=EventKind.WINDOW_FOCUS, payload={"app": app})
        )
        title = str(info.get("title", ""))
        if title and title != self._last_title:
            self._last_title = title
            await buffer.push(
                Event(
                    ts=ts,
                    kind=EventKind.WINDOW_TITLE,
                    payload={"app": app, "title": title},
                )
            )

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            info = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            return
        await self._handle(info, buffer)

    def post_window(self, app: str, title: str) -> None:
        self._queue.put_nowait({"app": app, "title": title})


async def _default_get_frontmost() -> tuple[str, str]:  # pragma: no cover — real macOS
    """(app_name, window_title) of the frontmost app via NSWorkspace + AX."""
    def _read() -> tuple[str, str]:
        from AppKit import NSWorkspace  # type: ignore[import-untyped]

        ws_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if ws_app is None:
            return "", ""
        name = str(ws_app.localizedName() or "")
        title = ""
        try:
            import yuki.ax as ax

            app = ax.GetRunningApplicationByBundleId(
                str(ws_app.bundleIdentifier() or "")
            )
            if app and (win := app.MainWindow):
                title = str(
                    ax.GetAttribute(win.Element, ax.Attribute.Title) or ""
                )
        except Exception:
            pass
        return name, title

    return await asyncio.to_thread(_read)


class WindowPollSource(Source):
    """Polls the frontmost app + window title every few seconds.

    Unlike WindowSource (push-based, needs an AX-notification feeder that was
    never wired), this is self-contained: it works the moment the daemon
    starts. 5s resolution is plenty for "what does the user do all day".
    """

    name = "window_poll"

    def __init__(
        self,
        get_frontmost: Any = None,
        poll_seconds: float = 5.0,
    ) -> None:
        super().__init__()
        self._get_frontmost = get_frontmost or _default_get_frontmost
        self._poll = poll_seconds
        self._last: tuple[str, str] | None = None

    async def iterate(self, buffer: RingBuffer) -> None:
        app, title = await self._get_frontmost()
        if app and (app, title) != self._last:
            ts = datetime.now(UTC)
            if self._last is None or app != self._last[0]:
                await buffer.push(
                    Event(ts=ts, kind=EventKind.APP_FOCUS, payload={"app": app})
                )
            if title:
                await buffer.push(
                    Event(
                        ts=ts,
                        kind=EventKind.WINDOW_TITLE,
                        payload={"app": app, "title": title},
                    )
                )
            self._last = (app, title)
        await asyncio.sleep(self._poll)
