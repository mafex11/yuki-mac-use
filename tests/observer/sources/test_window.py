"""WindowSource: emits WINDOW_FOCUS + WINDOW_TITLE; dedupes title."""

from __future__ import annotations

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.window import WindowSource


async def test_emits_window_focus_and_title() -> None:
    src = WindowSource()
    rb = RingBuffer()
    await src._handle({"app": "Safari", "title": "Inbox - Sarah"}, rb)
    out = await rb.drain()
    kinds = [e.kind for e in out]
    assert EventKind.WINDOW_FOCUS in kinds
    assert EventKind.WINDOW_TITLE in kinds


async def test_dedupes_same_title() -> None:
    src = WindowSource()
    rb = RingBuffer()
    await src._handle({"app": "Safari", "title": "X"}, rb)
    await src._handle({"app": "Safari", "title": "X"}, rb)
    out = await rb.drain()
    titles = [e for e in out if e.kind == EventKind.WINDOW_TITLE]
    assert len(titles) == 1
