"""FilesystemSource: emits FILE_MODIFIED, dedupes within 1s."""

from __future__ import annotations

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.filesystem import FilesystemSource


async def test_emits_for_each_path() -> None:
    src = FilesystemSource(watched_dirs=["/tmp"])
    rb = RingBuffer()
    src.post_change("/tmp/foo.txt")
    src.post_change("/tmp/bar.py")
    for _ in range(2):
        await src.iterate(rb)
    out = await rb.drain()
    assert all(e.kind == EventKind.FILE_MODIFIED for e in out)
    assert {e.payload["path"] for e in out} == {"/tmp/foo.txt", "/tmp/bar.py"}


async def test_dedupes_within_one_second() -> None:
    src = FilesystemSource(watched_dirs=["/tmp"])
    rb = RingBuffer()
    src.post_change("/tmp/x")
    src.post_change("/tmp/x")
    for _ in range(2):
        await src.iterate(rb)
    out = await rb.drain()
    assert len(out) == 1
