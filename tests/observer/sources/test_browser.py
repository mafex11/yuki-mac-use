"""BrowserSource: emits URL_CHANGE only when URL changes."""

from __future__ import annotations

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.browser import BrowserSource


async def test_emits_on_url_change() -> None:
    urls = iter(["https://a.com", "https://a.com", "https://b.com"])

    async def fake_get() -> tuple[str | None, str | None]:
        return next(urls), "Safari"

    src = BrowserSource(get_url=fake_get)
    rb = RingBuffer()
    for _ in range(3):
        await src.iterate(rb)
    out = await rb.drain()
    url_events = [e for e in out if e.kind == EventKind.URL_CHANGE]
    assert len(url_events) == 2


async def test_no_event_when_not_browser() -> None:
    async def fake_get() -> tuple[str | None, str | None]:
        return None, None

    src = BrowserSource(get_url=fake_get)
    rb = RingBuffer()
    await src.iterate(rb)
    assert await rb.drain() == []
