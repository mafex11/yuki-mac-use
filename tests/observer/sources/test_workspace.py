"""WorkspaceSource: dedupes consecutive same-app focus."""

from __future__ import annotations

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.workspace import WorkspaceSource


async def test_emits_on_focus_change() -> None:
    src = WorkspaceSource()
    rb = RingBuffer()
    await src._handle_app({"bundle_id": "com.apple.Safari", "name": "Safari"}, rb)
    await src._handle_app({"bundle_id": "com.tinyspeck.slackmacgap", "name": "Slack"}, rb)
    out = await rb.drain()
    assert [e.kind for e in out] == [EventKind.APP_FOCUS, EventKind.APP_FOCUS]
    assert out[0].payload["bundle_id"] == "com.apple.Safari"


async def test_dedupes_consecutive_same_app() -> None:
    src = WorkspaceSource()
    rb = RingBuffer()
    await src._handle_app({"bundle_id": "com.apple.Safari", "name": "Safari"}, rb)
    await src._handle_app({"bundle_id": "com.apple.Safari", "name": "Safari"}, rb)
    out = await rb.drain()
    assert len(out) == 1
