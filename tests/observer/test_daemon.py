"""Daemon: runs sources concurrently, flushes to SQLite, isolates failures."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from yuki.observer.daemon import Daemon
from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class _Tick(Source):
    name = "tick"

    def __init__(self, n: int = 3) -> None:
        super().__init__()
        self._n = n
        self._i = 0

    async def iterate(self, buffer: RingBuffer) -> None:
        self._i += 1
        await buffer.push(
            Event(
                ts=datetime.now(UTC),
                kind=EventKind.APP_FOCUS,
                payload={"i": self._i},
            )
        )
        if self._i >= self._n:
            self.stop()


class _Boom(Source):
    name = "boom"

    async def iterate(self, buffer: RingBuffer) -> None:
        raise RuntimeError("kaboom")


async def test_daemon_runs_sources_and_flushes(tmp_index_db: Path) -> None:
    daemon = Daemon(sources=[_Tick(n=3)], flush_interval=0.05)
    await daemon.start()
    await asyncio.sleep(0.3)
    await daemon.stop()
    # stop() closes the persister; reopen to inspect rows.
    daemon.persister.open()
    try:
        assert daemon.persister.row_count() >= 3
    finally:
        daemon.persister.close()


async def test_daemon_one_failing_source_does_not_kill_others(
    tmp_index_db: Path,
) -> None:
    good = _Tick(n=2)
    daemon = Daemon(sources=[good, _Boom()], flush_interval=0.05)
    await daemon.start()
    await asyncio.sleep(0.3)
    await daemon.stop()
    daemon.persister.open()
    try:
        assert daemon.persister.row_count() >= 2
    finally:
        daemon.persister.close()
