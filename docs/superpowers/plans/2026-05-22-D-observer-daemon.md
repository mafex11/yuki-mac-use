# Plan D — Observer Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the always-on observer subsystem that subscribes to native macOS notifications (8 sources), keeps the last 24h in an in-memory ring buffer, and flushes events to SQLite every 60 seconds. This is what feeds the Episodist (Plan E) and Trigger Engine (Plan F).

**Architecture:** `Daemon` is an asyncio supervisor that owns N `Source` tasks. Each Source emits `Event` records to a shared `RingBuffer`. A `Persister` task pulls from the ring every 60s and bulk-inserts into the `events` table in `~/Library/Application Support/Yuki/index.db` (same DB the memory indexer uses, separate table). All 8 sources are independent — failure in one does not stop others. None polls; all hook native callbacks except idle (1s tick).

**Tech Stack:** stdlib `asyncio`, `pyobjc-framework-Cocoa` (NSWorkspace, IOKit notifications), `pyobjc-framework-ApplicationServices` (AX), `pyobjc-framework-EventKit`, `pyobjc-framework-Quartz` (CGEventSource for idle), `pyobjc-framework-CoreWLAN` (network), `sqlite3` stdlib, `pytest-asyncio` for tests.

**Spec reference:** `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` §6.1 (event sources table), §6.2 (ring buffer + SQLite), §3.3 (data flow), §11.4 (no network without reason).

**Prerequisite:** Plan B complete — `~/Library/Application Support/Yuki/index.db` exists or is creatable; `yuki/memory/paths.py` provides DB path.

---

## Resolved open questions

1. **Sample rate for idle source** — 1 second tick. Cheap; avoids notification API for idle since macOS doesn't expose one.
2. **Browser URL polling cadence** — only when browser is the focused app, every 2 seconds. Spec §6.1 calls out "AppleScript poll on browser focus only".
3. **Event retention** — 30 days, configurable via `YUKI_EVENT_RETENTION_DAYS`. Persister deletes rows older than the cutoff on each flush.
4. **Ring buffer sizing** — 100k events covers ≥24h on a heavy day (10k/day estimate × 10x headroom). Drops oldest if full.

---

## File Structure

```
Yuki/
├── yuki/
│   └── observer/
│       ├── __init__.py                 # NEW — exports Daemon, Event
│       ├── events.py                   # NEW — Event dataclass + EventKind enum
│       ├── ringbuffer.py               # NEW — bounded async ring
│       ├── persistence.py              # NEW — SQLite events table + flush
│       ├── daemon.py                   # NEW — supervisor
│       └── sources/
│           ├── __init__.py             # NEW
│           ├── base.py                 # NEW — Source protocol + run wrapper
│           ├── workspace.py            # NEW — NSWorkspace app focus
│           ├── window.py               # NEW — AX focused window
│           ├── browser.py              # NEW — Safari/Chrome URL when focused
│           ├── idle.py                 # NEW — CGEventSource 1s tick
│           ├── calendar.py             # NEW — EventKit observer
│           ├── filesystem.py           # NEW — FSEvents on watched dirs
│           ├── power.py                # NEW — IOKit lock/sleep notifications
│           └── network.py              # NEW — CoreWLAN wifi changes
└── tests/
    └── observer/
        ├── __init__.py
        ├── conftest.py                 # NEW — tmp DB, fake event stream
        ├── test_events.py
        ├── test_ringbuffer.py
        ├── test_persistence.py
        ├── test_daemon.py
        └── sources/
            ├── __init__.py
            ├── test_source_base.py
            ├── test_workspace.py
            ├── test_window.py
            ├── test_browser.py
            ├── test_idle.py
            ├── test_calendar.py
            ├── test_filesystem.py
            ├── test_power.py
            └── test_network.py
```

---

## Task 1 — Event dataclass + EventKind

**Files:**
- Create: `yuki/observer/__init__.py`
- Create: `yuki/observer/events.py`
- Create: `tests/observer/__init__.py`
- Create: `tests/observer/test_events.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/__init__.py` (empty) and `tests/observer/test_events.py`:

```python
from datetime import datetime, timezone

from yuki.observer.events import Event, EventKind


def test_event_round_trip():
    ts = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    e = Event(ts=ts, kind=EventKind.APP_FOCUS,
              payload={"bundle_id": "com.apple.Safari"})
    d = e.to_dict()
    e2 = Event.from_dict(d)
    assert e2 == e


def test_event_to_row_returns_int_ms():
    ts = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    e = Event(ts=ts, kind=EventKind.IDLE_START, payload={"seconds": 60})
    ts_ms, kind, payload_json = e.to_row()
    assert isinstance(ts_ms, int)
    assert kind == "idle_start"
    assert "seconds" in payload_json


def test_eventkind_values():
    assert EventKind.APP_FOCUS.value == "app_focus"
    assert EventKind.IDLE_END.value == "idle_end"
    assert EventKind.WIFI_CHANGED.value == "wifi_changed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/test_events.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/__init__.py`**

```python
"""Observer daemon: passive macOS event collection."""
```

- [ ] **Step 4: Implement `yuki/observer/events.py`**

```python
"""Event types emitted by observer sources."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    APP_FOCUS = "app_focus"
    WINDOW_FOCUS = "window_focus"
    WINDOW_TITLE = "window_title"
    URL_CHANGE = "url_change"
    IDLE_START = "idle_start"
    IDLE_END = "idle_end"
    EVENT_STARTING = "event_starting"
    EVENT_ENDED = "event_ended"
    FILE_MODIFIED = "file_modified"
    LOCK = "lock"
    UNLOCK = "unlock"
    SLEEP = "sleep"
    WAKE = "wake"
    POWER_SOURCE_CHANGED = "power_source_changed"
    WIFI_CHANGED = "wifi_changed"


@dataclass
class Event:
    ts: datetime
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ts": self.ts.isoformat(),
            "kind": self.kind.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            ts=datetime.fromisoformat(d["ts"]),
            kind=EventKind(d["kind"]),
            payload=dict(d.get("payload", {})),
        )

    def to_row(self) -> tuple[int, str, str]:
        ts_ms = int(self.ts.timestamp() * 1000)
        return ts_ms, self.kind.value, json.dumps(self.payload)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/test_events.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/__init__.py yuki/observer/events.py tests/observer/__init__.py tests/observer/test_events.py
git commit -m "feat(observer): add Event dataclass and EventKind enum"
```

---

## Task 2 — Ring buffer

Bounded, async-safe FIFO. Drops oldest when full. Backed by `collections.deque(maxlen=N)` plus an `asyncio.Lock` for the drain operation.

**Files:**
- Create: `yuki/observer/ringbuffer.py`
- Create: `tests/observer/test_ringbuffer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/test_ringbuffer.py`:

```python
from datetime import datetime, timezone

import pytest

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer


def _e(secs):
    ts = datetime(2026, 5, 22, 12, 0, secs, tzinfo=timezone.utc)
    return Event(ts=ts, kind=EventKind.APP_FOCUS, payload={"i": secs})


@pytest.mark.asyncio
async def test_push_and_drain():
    rb = RingBuffer(capacity=10)
    await rb.push(_e(1))
    await rb.push(_e(2))
    out = await rb.drain()
    assert [e.payload["i"] for e in out] == [1, 2]
    assert await rb.drain() == []


@pytest.mark.asyncio
async def test_drops_oldest_when_full():
    rb = RingBuffer(capacity=3)
    for i in range(5):
        await rb.push(_e(i))
    out = await rb.drain()
    assert [e.payload["i"] for e in out] == [2, 3, 4]


@pytest.mark.asyncio
async def test_size_property():
    rb = RingBuffer(capacity=10)
    for i in range(4):
        await rb.push(_e(i))
    assert rb.size == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/test_ringbuffer.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/ringbuffer.py`**

```python
"""Bounded async ring buffer for observer events."""
from __future__ import annotations

import asyncio
from collections import deque

from yuki.observer.events import Event


class RingBuffer:
    def __init__(self, capacity: int = 100_000) -> None:
        self._buf: deque[Event] = deque(maxlen=capacity)
        self._lock = asyncio.Lock()

    async def push(self, event: Event) -> None:
        async with self._lock:
            self._buf.append(event)

    async def drain(self) -> list[Event]:
        async with self._lock:
            out = list(self._buf)
            self._buf.clear()
            return out

    @property
    def size(self) -> int:
        return len(self._buf)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/test_ringbuffer.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/ringbuffer.py tests/observer/test_ringbuffer.py
git commit -m "feat(observer): add bounded async ring buffer"
```

---

## Task 3 — Persister (events table + flush + retention)

**Files:**
- Create: `yuki/observer/persistence.py`
- Create: `tests/observer/conftest.py`
- Create: `tests/observer/test_persistence.py`

- [ ] **Step 1: Add fixtures**

Create `tests/observer/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def tmp_index_db(tmp_path: Path, monkeypatch) -> Path:
    db = tmp_path / "index.db"
    monkeypatch.setenv("YUKI_INDEX_DB", str(db))
    return db
```

- [ ] **Step 2: Write the failing test**

Create `tests/observer/test_persistence.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from yuki.observer.events import Event, EventKind
from yuki.observer.persistence import Persister


def _e(ts):
    return Event(ts=ts, kind=EventKind.APP_FOCUS, payload={"x": 1})


@pytest.mark.asyncio
async def test_init_creates_table(tmp_index_db: Path):
    p = Persister()
    p.open()
    assert p.row_count() == 0
    p.close()


@pytest.mark.asyncio
async def test_flush_inserts_events(tmp_index_db: Path):
    p = Persister()
    p.open()
    now = datetime.now(timezone.utc)
    p.flush([_e(now), _e(now + timedelta(seconds=1))])
    assert p.row_count() == 2
    p.close()


@pytest.mark.asyncio
async def test_flush_empty_is_noop(tmp_index_db: Path):
    p = Persister()
    p.open()
    p.flush([])
    assert p.row_count() == 0
    p.close()


@pytest.mark.asyncio
async def test_retention_deletes_old(tmp_index_db: Path, monkeypatch):
    monkeypatch.setenv("YUKI_EVENT_RETENTION_DAYS", "1")
    p = Persister()
    p.open()
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=5)
    p.flush([_e(old), _e(now)])
    p.purge_old()
    assert p.row_count() == 1
    p.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/test_persistence.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `yuki/observer/persistence.py`**

```python
"""Persister — flushes ring buffer events to SQLite."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from yuki.memory import paths
from yuki.observer.events import Event


class Persister:
    def __init__(self) -> None:
        self._db_path = paths.index_db_path()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                ts INTEGER NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT
            );
            CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
            """
        )
        conn.commit()
        self._conn = conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Persister not opened")
        return self._conn

    def flush(self, events: list[Event]) -> None:
        if not events:
            return
        rows = [e.to_row() for e in events]
        self.conn.executemany(
            "INSERT INTO events(ts, kind, payload) VALUES (?, ?, ?)", rows,
        )
        self.conn.commit()

    def purge_old(self) -> int:
        days = int(os.environ.get("YUKI_EVENT_RETENTION_DAYS", "30"))
        cutoff_ms = int(
            (datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000
        )
        cur = self.conn.execute("DELETE FROM events WHERE ts < ?", (cutoff_ms,))
        self.conn.commit()
        return cur.rowcount

    def row_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/test_persistence.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/persistence.py tests/observer/conftest.py tests/observer/test_persistence.py
git commit -m "feat(observer): add SQLite Persister with retention"
```

---

## Task 4 — Source base protocol

Each Source is an asyncio task that pushes Events into the shared RingBuffer. The base provides a `run(buffer)` wrapper that catches exceptions per-iteration so a flaky source can't kill the daemon.

**Files:**
- Create: `yuki/observer/sources/__init__.py`
- Create: `yuki/observer/sources/base.py`
- Create: `tests/observer/sources/__init__.py`
- Create: `tests/observer/sources/test_source_base.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/sources/__init__.py` (empty) and `tests/observer/sources/test_source_base.py`:

```python
import asyncio
from datetime import datetime, timezone

import pytest

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class _Emitter(Source):
    name = "emitter"
    def __init__(self):
        self.iters = 0
    async def iterate(self, buffer):
        self.iters += 1
        await buffer.push(Event(
            ts=datetime.now(timezone.utc),
            kind=EventKind.APP_FOCUS, payload={"i": self.iters},
        ))
        if self.iters >= 3:
            self.stop()


class _Boom(Source):
    name = "boom"
    def __init__(self):
        self.calls = 0
    async def iterate(self, buffer):
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("oops")
        self.stop()


@pytest.mark.asyncio
async def test_source_emits_until_stopped():
    rb = RingBuffer()
    src = _Emitter()
    await src.run(rb, tick=0.0)
    out = await rb.drain()
    assert len(out) == 3


@pytest.mark.asyncio
async def test_source_swallows_iteration_errors():
    rb = RingBuffer()
    src = _Boom()
    await src.run(rb, tick=0.0)
    assert src.calls == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_source_base.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement source base**

Create `yuki/observer/sources/__init__.py`:

```python
"""Observer sources — one per macOS event stream."""
```

Create `yuki/observer/sources/base.py`:

```python
"""Source protocol with error-swallowing run loop."""
from __future__ import annotations

import asyncio
import logging

from yuki.observer.ringbuffer import RingBuffer

log = logging.getLogger(__name__)


class Source:
    name: str = "source"

    def __init__(self) -> None:
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def iterate(self, buffer: RingBuffer) -> None:
        """Override: do one unit of work, push 0..N events."""
        raise NotImplementedError

    async def run(self, buffer: RingBuffer, tick: float = 1.0) -> None:
        while not self._stopped:
            try:
                await self.iterate(buffer)
            except Exception as e:
                log.warning("source %s failed: %s", self.name, e)
            if self._stopped:
                break
            if tick > 0:
                await asyncio.sleep(tick)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_source_base.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/__init__.py yuki/observer/sources/base.py tests/observer/sources/__init__.py tests/observer/sources/test_source_base.py
git commit -m "feat(observer): add Source protocol with error-swallowing run loop"
```

---

## Task 5 — `workspace` source (NSWorkspace app focus)

Subscribes to `NSWorkspace.didActivateApplicationNotification`. Emits `APP_FOCUS` events. Real implementation uses pyobjc; tests inject a fake notification queue.

**Files:**
- Create: `yuki/observer/sources/workspace.py`
- Create: `tests/observer/sources/test_workspace.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/sources/test_workspace.py`:

```python
import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.workspace import WorkspaceSource


@pytest.mark.asyncio
async def test_emits_on_focus_change():
    src = WorkspaceSource()
    rb = RingBuffer()
    await src._handle_app({"bundle_id": "com.apple.Safari", "name": "Safari"}, rb)
    await src._handle_app({"bundle_id": "com.tinyspeck.slackmacgap", "name": "Slack"}, rb)
    out = await rb.drain()
    assert [e.kind for e in out] == [EventKind.APP_FOCUS, EventKind.APP_FOCUS]
    assert out[0].payload["bundle_id"] == "com.apple.Safari"


@pytest.mark.asyncio
async def test_dedupes_consecutive_same_app():
    src = WorkspaceSource()
    rb = RingBuffer()
    await src._handle_app({"bundle_id": "com.apple.Safari", "name": "Safari"}, rb)
    await src._handle_app({"bundle_id": "com.apple.Safari", "name": "Safari"}, rb)
    out = await rb.drain()
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_workspace.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/sources/workspace.py`**

```python
"""Workspace source — emits APP_FOCUS via NSWorkspace notifications."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class WorkspaceSource(Source):
    name = "workspace"

    def __init__(self) -> None:
        super().__init__()
        self._last_bundle: str | None = None
        self._queue: asyncio.Queue[dict] = asyncio.Queue()

    async def _handle_app(self, info: dict, buffer: RingBuffer) -> None:
        bundle = info.get("bundle_id", "")
        if bundle == self._last_bundle:
            return
        self._last_bundle = bundle
        await buffer.push(Event(
            ts=datetime.now(timezone.utc),
            kind=EventKind.APP_FOCUS,
            payload={"bundle_id": bundle, "name": info.get("name", "")},
        ))

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            info = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return
        await self._handle_app(info, buffer)

    def post_focus(self, bundle_id: str, name: str) -> None:
        self._queue.put_nowait({"bundle_id": bundle_id, "name": name})
```

Production wiring (registering with NSWorkspace's notification center to call `post_focus`) lives in the daemon's `start_native_observers()` (Task 12).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_workspace.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/workspace.py tests/observer/sources/test_workspace.py
git commit -m "feat(observer): add workspace source (app focus)"
```

---

## Task 6 — `window` source (AX focused window)

Hooks `kAXFocusedWindowChangedNotification` per app. Emits `WINDOW_FOCUS` and `WINDOW_TITLE`.

**Files:**
- Create: `yuki/observer/sources/window.py`
- Create: `tests/observer/sources/test_window.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/sources/test_window.py`:

```python
import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.window import WindowSource


@pytest.mark.asyncio
async def test_emits_window_focus_and_title():
    src = WindowSource()
    rb = RingBuffer()
    await src._handle({"app": "Safari", "title": "Inbox - Sarah"}, rb)
    out = await rb.drain()
    kinds = [e.kind for e in out]
    assert EventKind.WINDOW_FOCUS in kinds
    assert EventKind.WINDOW_TITLE in kinds


@pytest.mark.asyncio
async def test_dedupes_same_title():
    src = WindowSource()
    rb = RingBuffer()
    await src._handle({"app": "Safari", "title": "X"}, rb)
    await src._handle({"app": "Safari", "title": "X"}, rb)
    out = await rb.drain()
    titles = [e for e in out if e.kind == EventKind.WINDOW_TITLE]
    assert len(titles) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_window.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/sources/window.py`**

```python
"""Window source — emits WINDOW_FOCUS and WINDOW_TITLE via AX notifications."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class WindowSource(Source):
    name = "window"

    def __init__(self) -> None:
        super().__init__()
        self._last_title: str | None = None
        self._queue: asyncio.Queue[dict] = asyncio.Queue()

    async def _handle(self, info: dict, buffer: RingBuffer) -> None:
        ts = datetime.now(timezone.utc)
        await buffer.push(Event(ts=ts, kind=EventKind.WINDOW_FOCUS,
                                payload={"app": info.get("app", "")}))
        title = info.get("title", "")
        if title and title != self._last_title:
            self._last_title = title
            await buffer.push(Event(ts=ts, kind=EventKind.WINDOW_TITLE,
                                    payload={"app": info.get("app", ""),
                                             "title": title}))

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            info = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return
        await self._handle(info, buffer)

    def post_window(self, app: str, title: str) -> None:
        self._queue.put_nowait({"app": app, "title": title})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_window.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/window.py tests/observer/sources/test_window.py
git commit -m "feat(observer): add window source"
```

---

## Task 7 — `browser` source

When the focused app is Safari/Chrome/Firefox/Edge, polls current URL via AppleScript every 2 seconds. Emits `URL_CHANGE` only when URL differs from last seen. Tests inject a fake getter; production wiring uses `osascript` via `asyncio.create_subprocess_exec` with a static argument list (no shell).

**Files:**
- Create: `yuki/observer/sources/browser.py`
- Create: `tests/observer/sources/test_browser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/sources/test_browser.py`:

```python
import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.browser import BrowserSource


@pytest.mark.asyncio
async def test_emits_on_url_change():
    urls = iter(["https://a.com", "https://a.com", "https://b.com"])
    async def fake_get():
        return next(urls), "Safari"
    src = BrowserSource(get_url=fake_get)
    rb = RingBuffer()
    for _ in range(3):
        await src.iterate(rb)
    out = await rb.drain()
    url_events = [e for e in out if e.kind == EventKind.URL_CHANGE]
    assert len(url_events) == 2


@pytest.mark.asyncio
async def test_no_event_when_not_browser():
    async def fake_get():
        return None, None
    src = BrowserSource(get_url=fake_get)
    rb = RingBuffer()
    await src.iterate(rb)
    assert await rb.drain() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_browser.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/sources/browser.py`**

The dependency-injected `get_url` callable is the only thing tests touch. The default implementation (production) uses `asyncio.create_subprocess_exec` with `osascript` and a static argument list; no user-controlled string is interpolated.

```python
"""Browser source — emits URL_CHANGE when a browser is focused."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

_BROWSERS = {"Safari", "Google Chrome", "Firefox", "Microsoft Edge"}


async def _osa(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace").strip()


async def _default_get_url() -> tuple[str | None, str | None]:  # pragma: no cover
    app = await _osa(
        "-e",
        'tell application "System Events" to set fname to '
        'name of first process whose frontmost is true',
    )
    if app not in _BROWSERS:
        return None, None
    if app == "Safari":
        url = await _osa("-e", 'tell application "Safari" to URL of current tab of front window')
    else:
        url = await _osa("-e", f'tell application "{app}" to URL of active tab of front window')
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
        await buffer.push(Event(
            ts=datetime.now(timezone.utc),
            kind=EventKind.URL_CHANGE,
            payload={"url": url, "browser": app},
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_browser.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/browser.py tests/observer/sources/test_browser.py
git commit -m "feat(observer): add browser source"
```

---

## Task 8 — `idle` source

1s tick. Reads `CGEventSourceSecondsSinceLastEventType`. Emits `IDLE_START` when crossing 60s threshold, `IDLE_END` when activity resumes.

**Files:**
- Create: `yuki/observer/sources/idle.py`
- Create: `tests/observer/sources/test_idle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/sources/test_idle.py`:

```python
import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.idle import IdleSource


@pytest.mark.asyncio
async def test_idle_start_then_end():
    seconds = iter([10, 70, 80, 5])
    async def fake_idle():
        return next(seconds)
    src = IdleSource(get_idle=fake_idle, threshold=60)
    rb = RingBuffer()
    for _ in range(4):
        await src.iterate(rb)
    out = await rb.drain()
    kinds = [e.kind for e in out]
    assert EventKind.IDLE_START in kinds
    assert EventKind.IDLE_END in kinds
    assert kinds.index(EventKind.IDLE_START) < kinds.index(EventKind.IDLE_END)


@pytest.mark.asyncio
async def test_no_event_below_threshold():
    seconds = iter([10, 20, 30, 40])
    async def fake_idle():
        return next(seconds)
    src = IdleSource(get_idle=fake_idle, threshold=60)
    rb = RingBuffer()
    for _ in range(4):
        await src.iterate(rb)
    assert await rb.drain() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_idle.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/sources/idle.py`**

```python
"""Idle source — emits IDLE_START / IDLE_END based on system idle seconds."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


async def _default_get_idle() -> float:  # pragma: no cover
    try:
        import Quartz
        return Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateHIDSystemState,
            Quartz.kCGAnyInputEventType,
        )
    except Exception:
        return 0.0


class IdleSource(Source):
    name = "idle"

    def __init__(
        self,
        get_idle: Callable[[], Awaitable[float]] | None = None,
        threshold: float = 60.0,
    ) -> None:
        super().__init__()
        self._get_idle = get_idle or _default_get_idle
        self._threshold = threshold
        self._is_idle = False

    async def iterate(self, buffer: RingBuffer) -> None:
        seconds = await self._get_idle()
        if seconds >= self._threshold and not self._is_idle:
            self._is_idle = True
            await buffer.push(Event(
                ts=datetime.now(timezone.utc),
                kind=EventKind.IDLE_START,
                payload={"seconds": seconds},
            ))
        elif seconds < self._threshold and self._is_idle:
            self._is_idle = False
            await buffer.push(Event(
                ts=datetime.now(timezone.utc),
                kind=EventKind.IDLE_END, payload={},
            ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_idle.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/idle.py tests/observer/sources/test_idle.py
git commit -m "feat(observer): add idle source"
```

---

## Task 9 — `calendar` source

EventKit observer. Emits `EVENT_STARTING` 5 minutes before each event, `EVENT_ENDED` when end time passes. Test injects a fake event list with controllable "now".

**Files:**
- Create: `yuki/observer/sources/calendar.py`
- Create: `tests/observer/sources/test_calendar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/sources/test_calendar.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.calendar import CalendarSource


@pytest.mark.asyncio
async def test_emits_event_starting_5min_before():
    base = datetime(2026, 5, 22, 9, 55, tzinfo=timezone.utc)
    cal_event = {"id": "e1", "title": "Standup",
                 "start": base + timedelta(minutes=5),
                 "end": base + timedelta(minutes=20)}

    async def fake_events():
        return [cal_event]

    src = CalendarSource(fetch_events=fake_events, now=lambda: base)
    rb = RingBuffer()
    await src.iterate(rb)
    out = await rb.drain()
    assert any(e.kind == EventKind.EVENT_STARTING for e in out)


@pytest.mark.asyncio
async def test_emits_event_ended_after_end():
    base = datetime(2026, 5, 22, 10, 25, tzinfo=timezone.utc)
    cal_event = {"id": "e1", "title": "Standup",
                 "start": base - timedelta(minutes=25),
                 "end": base - timedelta(minutes=5)}

    async def fake_events():
        return [cal_event]

    src = CalendarSource(fetch_events=fake_events, now=lambda: base)
    rb = RingBuffer()
    await src.iterate(rb)
    out = await rb.drain()
    assert any(e.kind == EventKind.EVENT_ENDED for e in out)


@pytest.mark.asyncio
async def test_no_double_fire():
    base = datetime(2026, 5, 22, 9, 55, tzinfo=timezone.utc)
    cal_event = {"id": "e1", "title": "X",
                 "start": base + timedelta(minutes=5),
                 "end": base + timedelta(minutes=20)}

    async def fake_events():
        return [cal_event]

    src = CalendarSource(fetch_events=fake_events, now=lambda: base)
    rb = RingBuffer()
    await src.iterate(rb)
    await src.iterate(rb)
    starting = [e for e in await rb.drain() if e.kind == EventKind.EVENT_STARTING]
    assert len(starting) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_calendar.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/sources/calendar.py`**

```python
"""Calendar source — emits EVENT_STARTING and EVENT_ENDED via EventKit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

_LEAD = timedelta(minutes=5)


async def _default_fetch() -> list[dict]:  # pragma: no cover
    try:
        from EventKit import EKEventStore, EKEntityTypeEvent
    except Exception:
        return []
    store = EKEventStore.alloc().init()
    end = datetime.now(timezone.utc) + timedelta(hours=24)
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(start, end, None)
    out = []
    for ek in store.eventsMatchingPredicate_(pred) or []:
        out.append({
            "id": str(ek.eventIdentifier()),
            "title": ek.title() or "",
            "start": datetime.fromtimestamp(
                ek.startDate().timeIntervalSince1970(), tz=timezone.utc
            ),
            "end": datetime.fromtimestamp(
                ek.endDate().timeIntervalSince1970(), tz=timezone.utc
            ),
        })
    return out


class CalendarSource(Source):
    name = "calendar"

    def __init__(
        self,
        fetch_events: Callable[[], Awaitable[list[dict]]] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        self._fetch = fetch_events or _default_fetch
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._fired_starting: set[str] = set()
        self._fired_ended: set[str] = set()

    async def iterate(self, buffer: RingBuffer) -> None:
        events = await self._fetch()
        now = self._now()
        for ev in events:
            eid = ev["id"]
            start = ev["start"]
            end = ev["end"]
            if eid not in self._fired_starting and 0 <= (start - now).total_seconds() <= _LEAD.total_seconds():
                self._fired_starting.add(eid)
                await buffer.push(Event(
                    ts=now, kind=EventKind.EVENT_STARTING,
                    payload={"id": eid, "title": ev.get("title", ""),
                             "start": start.isoformat()},
                ))
            if eid not in self._fired_ended and end <= now:
                self._fired_ended.add(eid)
                await buffer.push(Event(
                    ts=now, kind=EventKind.EVENT_ENDED,
                    payload={"id": eid, "title": ev.get("title", "")},
                ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_calendar.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/calendar.py tests/observer/sources/test_calendar.py
git commit -m "feat(observer): add calendar source"
```

---

## Task 10 — `filesystem` source

FSEvents on watched dirs. Emits `FILE_MODIFIED`. The watch list comes from `~/code` plus other directories the patterns module flagged in scan (Plan C).

**Files:**
- Create: `yuki/observer/sources/filesystem.py`
- Create: `tests/observer/sources/test_filesystem.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/sources/test_filesystem.py`:

```python
import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.filesystem import FilesystemSource


@pytest.mark.asyncio
async def test_emits_for_each_path():
    src = FilesystemSource(watched_dirs=["/tmp"])
    rb = RingBuffer()
    src.post_change("/tmp/foo.txt")
    src.post_change("/tmp/bar.py")
    for _ in range(2):
        await src.iterate(rb)
    out = await rb.drain()
    assert all(e.kind == EventKind.FILE_MODIFIED for e in out)
    assert {e.payload["path"] for e in out} == {"/tmp/foo.txt", "/tmp/bar.py"}


@pytest.mark.asyncio
async def test_dedupes_within_one_second():
    src = FilesystemSource(watched_dirs=["/tmp"])
    rb = RingBuffer()
    src.post_change("/tmp/x")
    src.post_change("/tmp/x")
    for _ in range(2):
        await src.iterate(rb)
    out = await rb.drain()
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_filesystem.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/sources/filesystem.py`**

```python
"""Filesystem source — emits FILE_MODIFIED via FSEvents."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class FilesystemSource(Source):
    name = "filesystem"

    def __init__(self, watched_dirs: list[str]) -> None:
        super().__init__()
        self._watched = list(watched_dirs)
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._last_seen: dict[str, float] = {}

    def post_change(self, path: str) -> None:
        self._queue.put_nowait(path)

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            path = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return
        now = time.time()
        last = self._last_seen.get(path, 0.0)
        if now - last < 1.0:
            return
        self._last_seen[path] = now
        await buffer.push(Event(
            ts=datetime.now(timezone.utc),
            kind=EventKind.FILE_MODIFIED, payload={"path": path},
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_filesystem.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/filesystem.py tests/observer/sources/test_filesystem.py
git commit -m "feat(observer): add filesystem source"
```

---

## Task 11 — `power` and `network` sources

Combined into one task — both are small. Power emits LOCK/UNLOCK/SLEEP/WAKE/POWER_SOURCE_CHANGED via IOKit notifications. Network emits WIFI_CHANGED via CWInterface.

**Files:**
- Create: `yuki/observer/sources/power.py`
- Create: `yuki/observer/sources/network.py`
- Create: `tests/observer/sources/test_power.py`
- Create: `tests/observer/sources/test_network.py`

- [ ] **Step 1: Write the failing tests**

`tests/observer/sources/test_power.py`:

```python
import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.power import PowerSource


@pytest.mark.asyncio
async def test_emits_lock_unlock():
    src = PowerSource()
    rb = RingBuffer()
    src.post("lock")
    src.post("unlock")
    for _ in range(2):
        await src.iterate(rb)
    out = await rb.drain()
    assert [e.kind for e in out] == [EventKind.LOCK, EventKind.UNLOCK]


@pytest.mark.asyncio
async def test_unknown_event_ignored():
    src = PowerSource()
    rb = RingBuffer()
    src.post("zzz")
    await src.iterate(rb)
    assert await rb.drain() == []
```

`tests/observer/sources/test_network.py`:

```python
import pytest

from yuki.observer.events import EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.network import NetworkSource


@pytest.mark.asyncio
async def test_emits_wifi_change():
    ssids = iter(["home", "home", "office"])
    async def fake_ssid():
        return next(ssids)
    src = NetworkSource(get_ssid=fake_ssid)
    rb = RingBuffer()
    for _ in range(3):
        await src.iterate(rb)
    out = await rb.drain()
    wifi = [e for e in out if e.kind == EventKind.WIFI_CHANGED]
    assert len(wifi) == 2
    assert wifi[1].payload["ssid"] == "office"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_power.py tests/observer/sources/test_network.py -v`
Expected: ModuleNotFoundError × 2.

- [ ] **Step 3: Implement `yuki/observer/sources/power.py`**

```python
"""Power source — lock/unlock/sleep/wake via IOKit notifications."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

_KIND_MAP = {
    "lock": EventKind.LOCK,
    "unlock": EventKind.UNLOCK,
    "sleep": EventKind.SLEEP,
    "wake": EventKind.WAKE,
    "power_source_changed": EventKind.POWER_SOURCE_CHANGED,
}


class PowerSource(Source):
    name = "power"

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def post(self, name: str) -> None:
        self._queue.put_nowait(name)

    async def iterate(self, buffer: RingBuffer) -> None:
        try:
            name = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return
        kind = _KIND_MAP.get(name)
        if kind is None:
            return
        await buffer.push(Event(
            ts=datetime.now(timezone.utc), kind=kind, payload={},
        ))
```

- [ ] **Step 4: Implement `yuki/observer/sources/network.py`**

```python
"""Network source — emits WIFI_CHANGED on SSID change."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


async def _default_get_ssid() -> str | None:  # pragma: no cover
    try:
        from CoreWLAN import CWInterface
        ifc = CWInterface.interface()
        return str(ifc.ssid()) if ifc and ifc.ssid() else None
    except Exception:
        return None


class NetworkSource(Source):
    name = "network"

    def __init__(
        self,
        get_ssid: Callable[[], Awaitable[str | None]] | None = None,
    ) -> None:
        super().__init__()
        self._get_ssid = get_ssid or _default_get_ssid
        self._last_ssid: str | None = None

    async def iterate(self, buffer: RingBuffer) -> None:
        ssid = await self._get_ssid()
        if ssid == self._last_ssid:
            return
        self._last_ssid = ssid
        await buffer.push(Event(
            ts=datetime.now(timezone.utc),
            kind=EventKind.WIFI_CHANGED,
            payload={"ssid": ssid},
        ))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/sources/test_power.py tests/observer/sources/test_network.py -v`
Expected: 4 PASS total.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/sources/power.py yuki/observer/sources/network.py tests/observer/sources/test_power.py tests/observer/sources/test_network.py
git commit -m "feat(observer): add power and network sources"
```

---

## Task 12 — Daemon supervisor

Owns the ring buffer + persister + N source tasks. `start()` launches everything; `stop()` cancels gracefully and flushes remaining events.

**Files:**
- Create: `yuki/observer/daemon.py`
- Modify: `yuki/observer/__init__.py`
- Create: `tests/observer/test_daemon.py`

- [ ] **Step 1: Write the failing test**

Create `tests/observer/test_daemon.py`:

```python
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.observer.daemon import Daemon
from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


class _Tick(Source):
    name = "tick"
    def __init__(self, n=3):
        super().__init__()
        self._n = n
        self._i = 0
    async def iterate(self, buffer):
        self._i += 1
        await buffer.push(Event(
            ts=datetime.now(timezone.utc),
            kind=EventKind.APP_FOCUS, payload={"i": self._i},
        ))
        if self._i >= self._n:
            self.stop()


@pytest.mark.asyncio
async def test_daemon_runs_sources_and_flushes(tmp_index_db: Path):
    daemon = Daemon(sources=[_Tick(n=3)], flush_interval=0.05)
    await daemon.start()
    await asyncio.sleep(0.3)
    await daemon.stop()
    assert daemon.persister.row_count() >= 3


@pytest.mark.asyncio
async def test_daemon_one_failing_source_does_not_kill_others(tmp_index_db: Path):
    class _Boom(Source):
        name = "boom"
        async def iterate(self, buffer):
            raise RuntimeError("kaboom")
    good = _Tick(n=2)
    daemon = Daemon(sources=[good, _Boom()], flush_interval=0.05)
    await daemon.start()
    await asyncio.sleep(0.3)
    await daemon.stop()
    assert daemon.persister.row_count() >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/test_daemon.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/observer/daemon.py`**

```python
"""Daemon supervisor — owns ring buffer + persister + N source tasks."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from yuki.observer.persistence import Persister
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source

log = logging.getLogger(__name__)


class Daemon:
    def __init__(
        self,
        sources: list[Source],
        flush_interval: float = 60.0,
        ring_capacity: int = 100_000,
    ) -> None:
        self._sources = list(sources)
        self._flush_interval = flush_interval
        self.buffer = RingBuffer(capacity=ring_capacity)
        self.persister = Persister()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self.persister.open()
        for src in self._sources:
            self._tasks.append(asyncio.create_task(src.run(self.buffer, tick=0.0)))
        self._tasks.append(asyncio.create_task(self._flusher()))

    async def stop(self) -> None:
        for src in self._sources:
            src.stop()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with suppress(asyncio.CancelledError):
                await t
        await self._flush_once()
        self.persister.close()
        self._tasks.clear()

    async def _flusher(self) -> None:
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush_once()

    async def _flush_once(self) -> None:
        try:
            events = await self.buffer.drain()
            self.persister.flush(events)
            self.persister.purge_old()
        except Exception as e:
            log.warning("flush failed: %s", e)
```

- [ ] **Step 4: Update `yuki/observer/__init__.py`**

```python
"""Observer daemon: passive macOS event collection."""

from yuki.observer.daemon import Daemon
from yuki.observer.events import Event, EventKind
from yuki.observer.persistence import Persister
from yuki.observer.ringbuffer import RingBuffer

__all__ = ["Daemon", "Event", "EventKind", "Persister", "RingBuffer"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/observer/ -v`
Expected: all green (≈25 tests).

- [ ] **Step 6: Run full project suite**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest -v`
Expected: full suite passes.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/observer/daemon.py yuki/observer/__init__.py tests/observer/test_daemon.py
git commit -m "feat(observer): add Daemon supervisor"
```

---

## Wrap-up

After Task 12, the observer subsystem is complete:
- `Daemon([WorkspaceSource(), WindowSource(), ...])` runs all 8 sources concurrently
- Events flow through the ring buffer, flush every 60s to `events` table
- 30-day retention enforced on each flush
- One failing source cannot bring down the others
- All sources are unit-tested with injected fakes; production wiring uses pyobjc/AppleScript inside `pragma: no cover` blocks (the menubar app + integration tests cover the real wiring)

Acceptance:
- `uv run pytest tests/observer/ -v` ≥25 tests, all green
- `Daemon` can be started and stopped from a Python REPL with a stub source
- `events` table accumulates rows on a real Mac for 5 minutes when run by hand

