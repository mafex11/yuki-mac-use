# Plan E — Episodist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the daily episode builder + weekly compactor that turns observer events (Plan D) into narrative markdown in `60-Episodes/` and proposes vault diffs for routines/people/apps every Sunday.

**Architecture:** Two scheduled jobs. (1) `builder.py` runs at 3am (or first wake after), reads yesterday's `events` rows, segments into sessions (gap >5min = new session), labels each session via heuristics, writes `60-Episodes/YYYY-MM-DD.md`. (2) `compactor.py` runs Sunday morning, reads last 7-30 episodes, calls Claude Haiku with a tight prompt, parses a JSON diff, applies high-confidence (>0.85) entries directly to vault notes, queues lower-confidence entries to `90-Inbox/`. Both are pure functions over inputs (events DB + vault) and produce deterministic output paths — no daemon, just on-demand entry points called by `com.yuki.scheduler.plist`.

**Tech Stack:** stdlib `sqlite3`, `jinja2` (already a Plan C dep), `anthropic` (already a Plan A dep), Pydantic (already a Plan B dep), `pytest-asyncio`, `pytest-mock`.

**Spec reference:** §6.3 (daily episode), §6.4 (weekly compaction), §4.2 (routine schema), §11.2 (LLM only sees structured event log, not raw rows).

**Prerequisite:** Plans B (vault) and D (events table) complete.

---

## File Structure

```
Yuki/
├── yuki/
│   └── episodist/
│       ├── __init__.py                 # NEW — exports build_today, compact_last_week
│       ├── reader.py                   # NEW — pull events from SQLite for a date range
│       ├── sessions.py                 # NEW — segment events into sessions
│       ├── labeler.py                  # NEW — heuristic session labels
│       ├── builder.py                  # NEW — events → markdown episode
│       ├── compactor.py                # NEW — episodes → vault diff via Haiku
│       ├── diff.py                     # NEW — VaultDiff + apply()
│       └── templates/
│           └── episode.md.j2           # NEW
└── tests/
    └── episodist/
        ├── __init__.py
        ├── conftest.py                 # NEW — seed events table fixture
        ├── test_reader.py
        ├── test_sessions.py
        ├── test_labeler.py
        ├── test_builder.py
        ├── test_diff.py
        └── test_compactor.py           # mocks anthropic
```

---

## Task 1 — Reader (events → typed rows)

**Files:**
- Create: `yuki/episodist/__init__.py`
- Create: `yuki/episodist/reader.py`
- Create: `tests/episodist/__init__.py`
- Create: `tests/episodist/conftest.py`
- Create: `tests/episodist/test_reader.py`

- [ ] **Step 1: Add fixtures**

Create `tests/episodist/__init__.py` (empty) and `tests/episodist/conftest.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.observer.events import Event, EventKind
from yuki.observer.persistence import Persister


@pytest.fixture
def seeded_events_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    p = Persister()
    p.open()
    base = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    events = [
        Event(ts=base, kind=EventKind.APP_FOCUS,
              payload={"bundle_id": "com.apple.Safari", "name": "Safari"}),
        Event(ts=base.replace(minute=2), kind=EventKind.URL_CHANGE,
              payload={"url": "https://github.com/x", "browser": "Safari"}),
        Event(ts=base.replace(hour=10), kind=EventKind.APP_FOCUS,
              payload={"bundle_id": "com.tinyspeck.slackmacgap", "name": "Slack"}),
        Event(ts=base.replace(hour=12), kind=EventKind.IDLE_START,
              payload={"seconds": 60}),
    ]
    p.flush(events)
    p.close()
    return tmp_path / "index.db"
```

- [ ] **Step 2: Write the failing test**

Create `tests/episodist/test_reader.py`:

```python
from datetime import date
from pathlib import Path

from yuki.episodist.reader import read_events_for_date


def test_reads_events_for_date(seeded_events_db: Path):
    rows = read_events_for_date(date(2026, 5, 21))
    assert len(rows) == 4
    assert rows[0].kind.value == "app_focus"


def test_no_events_returns_empty(seeded_events_db: Path):
    rows = read_events_for_date(date(2026, 5, 1))
    assert rows == []


def test_rows_are_chronological(seeded_events_db: Path):
    rows = read_events_for_date(date(2026, 5, 21))
    times = [e.ts for e in rows]
    assert times == sorted(times)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_reader.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `yuki/episodist/__init__.py`**

```python
"""Episodist: daily episodes + weekly compaction over observer events."""
```

- [ ] **Step 5: Implement `yuki/episodist/reader.py`**

```python
"""Reader — pulls observer events out of SQLite for a given date or date range."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone

from yuki.memory import paths
from yuki.observer.events import Event, EventKind


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(paths.index_db_path())


def read_events_between(start: datetime, end: datetime) -> list[Event]:
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT ts, kind, payload FROM events "
            "WHERE ts >= ? AND ts < ? ORDER BY ts ASC",
            (start_ms, end_ms),
        ).fetchall()
    finally:
        conn.close()
    out: list[Event] = []
    for ts_ms, kind, payload in rows:
        out.append(Event(
            ts=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            kind=EventKind(kind),
            payload=json.loads(payload) if payload else {},
        ))
    return out


def read_events_for_date(d: date) -> list[Event]:
    start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    return read_events_between(start, start + timedelta(days=1))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_reader.py -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/episodist/__init__.py yuki/episodist/reader.py tests/episodist/__init__.py tests/episodist/conftest.py tests/episodist/test_reader.py
git commit -m "feat(episodist): add events reader"
```

---

## Task 2 — Sessions (segment events on >5min gap)

**Files:**
- Create: `yuki/episodist/sessions.py`
- Create: `tests/episodist/test_sessions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/episodist/test_sessions.py`:

```python
from datetime import datetime, timedelta, timezone

from yuki.episodist.sessions import Session, segment
from yuki.observer.events import Event, EventKind


def _e(min_offset, kind=EventKind.APP_FOCUS, payload=None):
    base = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    return Event(ts=base + timedelta(minutes=min_offset), kind=kind,
                 payload=payload or {})


def test_single_session_when_close_in_time():
    events = [_e(0), _e(1), _e(3), _e(4)]
    sessions = segment(events, gap_minutes=5)
    assert len(sessions) == 1
    assert sessions[0].duration_minutes() >= 4


def test_split_on_gap():
    events = [_e(0), _e(1), _e(20), _e(21)]
    sessions = segment(events, gap_minutes=5)
    assert len(sessions) == 2


def test_empty_events_returns_no_sessions():
    assert segment([], gap_minutes=5) == []


def test_one_event_creates_one_session():
    sessions = segment([_e(0)], gap_minutes=5)
    assert len(sessions) == 1
    assert sessions[0].duration_minutes() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_sessions.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/episodist/sessions.py`**

```python
"""Session segmentation — groups events into contiguous time blocks."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from yuki.observer.events import Event


@dataclass
class Session:
    start: datetime
    end: datetime
    events: list[Event] = field(default_factory=list)

    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


def segment(events: list[Event], gap_minutes: int = 5) -> list[Session]:
    if not events:
        return []
    gap = timedelta(minutes=gap_minutes)
    sessions: list[Session] = []
    current = Session(start=events[0].ts, end=events[0].ts, events=[events[0]])
    for ev in events[1:]:
        if ev.ts - current.end > gap:
            sessions.append(current)
            current = Session(start=ev.ts, end=ev.ts, events=[ev])
        else:
            current.end = ev.ts
            current.events.append(ev)
    sessions.append(current)
    return sessions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_sessions.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/episodist/sessions.py tests/episodist/test_sessions.py
git commit -m "feat(episodist): add session segmentation"
```

---

## Task 3 — Labeler (heuristic session labels)

Each session gets a short label based on its dominant app + URLs + calendar events overlapping it. Pure function, deterministic.

**Files:**
- Create: `yuki/episodist/labeler.py`
- Create: `tests/episodist/test_labeler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/episodist/test_labeler.py`:

```python
from datetime import datetime, timedelta, timezone

from yuki.episodist.labeler import label
from yuki.episodist.sessions import Session
from yuki.observer.events import Event, EventKind


def _session(events, start_minute=0):
    base = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    return Session(
        start=base + timedelta(minutes=start_minute),
        end=base + timedelta(minutes=start_minute + 30),
        events=events,
    )


def _ev(kind, payload, minute=0):
    base = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)
    return Event(ts=base + timedelta(minutes=minute), kind=kind, payload=payload)


def test_label_uses_dominant_app():
    events = [
        _ev(EventKind.APP_FOCUS, {"name": "Slack", "bundle_id": "x"}),
        _ev(EventKind.WINDOW_TITLE, {"title": "general", "app": "Slack"}, 5),
        _ev(EventKind.WINDOW_TITLE, {"title": "design", "app": "Slack"}, 10),
    ]
    out = label(_session(events))
    assert "Slack" in out


def test_label_falls_back_to_browser_domain():
    events = [
        _ev(EventKind.APP_FOCUS, {"name": "Safari", "bundle_id": "x"}),
        _ev(EventKind.URL_CHANGE,
             {"url": "https://github.com/me/yuki/pull/3", "browser": "Safari"}, 2),
    ]
    out = label(_session(events))
    assert "github.com" in out


def test_label_idle_session():
    events = [_ev(EventKind.IDLE_START, {"seconds": 60})]
    assert "idle" in label(_session(events)).lower()


def test_empty_session_label():
    s = Session(
        start=datetime(2026, 5, 21, tzinfo=timezone.utc),
        end=datetime(2026, 5, 21, tzinfo=timezone.utc), events=[],
    )
    assert label(s) == "Unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_labeler.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/episodist/labeler.py`**

```python
"""Labeler — produces a short human label for a session."""
from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from yuki.episodist.sessions import Session
from yuki.observer.events import EventKind


def label(session: Session) -> str:
    if not session.events:
        return "Unknown"

    # Idle?
    if any(e.kind == EventKind.IDLE_START for e in session.events) and \
       not any(e.kind in {EventKind.APP_FOCUS, EventKind.URL_CHANGE}
               for e in session.events):
        return "Idle"

    # Dominant app
    apps = Counter()
    for e in session.events:
        if e.kind == EventKind.APP_FOCUS:
            name = e.payload.get("name") or ""
            if name:
                apps[name] += 1
    if apps:
        top, _ = apps.most_common(1)[0]
        return f"{top} session"

    # Fall back to dominant browser domain
    domains = Counter()
    for e in session.events:
        if e.kind == EventKind.URL_CHANGE:
            url = e.payload.get("url") or ""
            netloc = urlparse(url).netloc
            if netloc:
                domains[netloc] += 1
    if domains:
        top, _ = domains.most_common(1)[0]
        return f"{top}"

    return "Unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_labeler.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/episodist/labeler.py tests/episodist/test_labeler.py
git commit -m "feat(episodist): add session labeler"
```

---

## Task 4 — Builder (events → episode markdown)

`build_for_date(d)` reads events, segments, labels, renders via Jinja, writes to `~/YukiVault/60-Episodes/YYYY-MM-DD.md`.

**Files:**
- Create: `yuki/episodist/templates/episode.md.j2`
- Create: `yuki/episodist/builder.py`
- Create: `tests/episodist/test_builder.py`

- [ ] **Step 1: Write the template**

`yuki/episodist/templates/episode.md.j2`:

```jinja
---
type: episode
id: episode-{{ date }}
date: {{ date }}
created_at: {{ now }}
updated_at: {{ now }}
confidence: 1.0
source: [observer]
---

# {{ date }}

{% for s in sessions %}
## {{ s.start_h }}:{{ "%02d" | format(s.start_m) }}–{{ s.end_h }}:{{ "%02d" | format(s.end_m) }} — {{ s.label }}

{% if s.bullets %}{% for b in s.bullets %}- {{ b }}
{% endfor %}{% endif %}

{% endfor %}
```

- [ ] **Step 2: Write the failing test**

Create `tests/episodist/test_builder.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from yuki.episodist.builder import build_for_date


@pytest.fixture
def vault_and_events(tmp_path: Path, monkeypatch, seeded_events_db):
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    return vault


def test_build_writes_episode(vault_and_events: Path):
    out = build_for_date(date(2026, 5, 21))
    assert out.exists()
    text = out.read_text()
    assert "2026-05-21" in text
    assert "type: episode" in text


def test_build_no_events_creates_empty_episode(vault_and_events: Path):
    out = build_for_date(date(2026, 5, 1))
    assert out.exists()
    assert "2026-05-01" in out.read_text()


def test_idempotent_overwrites(vault_and_events: Path):
    a = build_for_date(date(2026, 5, 21))
    b = build_for_date(date(2026, 5, 21))
    assert a == b
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_builder.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `yuki/episodist/builder.py`**

```python
"""Builder — events → daily episode markdown in 60-Episodes/."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from yuki.episodist.labeler import label
from yuki.episodist.reader import read_events_for_date
from yuki.episodist.sessions import segment
from yuki.memory import paths

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(disabled_extensions=("md.j2",)),
    trim_blocks=True, lstrip_blocks=True,
)


def _bullets(events) -> list[str]:
    out: list[str] = []
    titles_seen: set[str] = set()
    for e in events:
        if e.kind.value == "window_title":
            t = e.payload.get("title", "").strip()
            if t and t not in titles_seen:
                titles_seen.add(t)
                out.append(t)
    return out[:5]


def build_for_date(d: date) -> Path:
    events = read_events_for_date(d)
    sessions = segment(events, gap_minutes=5)
    rows = []
    for s in sessions:
        rows.append({
            "start_h": s.start.hour, "start_m": s.start.minute,
            "end_h": s.end.hour, "end_m": s.end.minute,
            "label": label(s),
            "bullets": _bullets(s.events),
        })
    template = _env.get_template("episode.md.j2")
    text = template.render(
        date=d.isoformat(),
        now=datetime.now(timezone.utc).isoformat(),
        sessions=rows,
    )
    out_dir = paths.vault_dir() / "60-Episodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{d.isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    return path
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_builder.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/episodist/templates/ yuki/episodist/builder.py tests/episodist/test_builder.py
git commit -m "feat(episodist): add daily episode builder"
```

---

## Task 5 — VaultDiff + apply

`VaultDiff` is the structured output of compaction. Each entry says "create/update note X with these fields, confidence Y". `apply()` writes high-confidence entries directly, queues lower ones to `90-Inbox/`.

**Files:**
- Create: `yuki/episodist/diff.py`
- Create: `tests/episodist/test_diff.py`

- [ ] **Step 1: Write the failing test**

Create `tests/episodist/test_diff.py`:

```python
from pathlib import Path

import pytest

from yuki.episodist.diff import DiffEntry, VaultDiff
from yuki.memory.vault import Vault


def _entry(id_, confidence, **kw):
    base = {
        "id": id_, "type": "routine", "name": "Morning",
        "schedule": "weekdays 8am", "steps": [], "trusted": False,
    }
    base.update(kw)
    return DiffEntry(action="create", note=base, confidence=confidence)


def test_high_confidence_writes_to_section(tmp_vault: Path):
    diff = VaultDiff(entries=[_entry("routine-morning", 0.9)])
    v = Vault()
    diff.apply(vault=v)
    note, _ = v.read("routine-morning")
    assert note.id == "routine-morning"


def test_low_confidence_routes_to_inbox(tmp_vault: Path):
    diff = VaultDiff(entries=[_entry("routine-x", 0.5)])
    v = Vault()
    diff.apply(vault=v)
    inbox = list((tmp_vault / "90-Inbox").glob("*.md"))
    assert len(inbox) == 1


def test_invalid_entry_skipped(tmp_vault: Path):
    diff = VaultDiff(entries=[
        DiffEntry(action="create", note={"type": "routine"}, confidence=0.9),
    ])
    v = Vault()
    applied = diff.apply(vault=v)
    assert applied == 0


def test_from_json_round_trip():
    payload = (
        '{"entries": [{"action": "create", "confidence": 0.9, '
        '"note": {"id": "routine-x", "type": "routine", "name": "X", '
        '"schedule": "?", "steps": [], "trusted": false}}]}'
    )
    diff = VaultDiff.from_json(payload)
    assert len(diff.entries) == 1
    assert diff.entries[0].confidence == 0.9
```

This test uses the `tmp_vault` fixture defined at `tests/conftest.py` (Plan B Task 5 placed it at the project test root, so it's auto-available to every test package — no re-export needed).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_diff.py -v`
Expected: ModuleNotFoundError on `yuki.episodist.diff`.

- [ ] **Step 3: Implement `yuki/episodist/diff.py`**

```python
"""VaultDiff — the structured output of compaction; can apply itself."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from yuki.memory.schemas import parse_note
from yuki.memory.vault import Vault

log = logging.getLogger(__name__)
_HIGH = 0.85


@dataclass
class DiffEntry:
    action: Literal["create", "update"]
    note: dict
    confidence: float


@dataclass
class VaultDiff:
    entries: list[DiffEntry] = field(default_factory=list)

    @classmethod
    def from_json(cls, text: str) -> "VaultDiff":
        data = json.loads(text)
        return cls(entries=[
            DiffEntry(
                action=e.get("action", "create"),
                note=e["note"], confidence=float(e["confidence"]),
            )
            for e in data.get("entries", [])
        ])

    def apply(self, *, vault: Vault) -> int:
        applied = 0
        for entry in self.entries:
            try:
                note = parse_note(entry.note)
            except Exception as e:
                log.warning("invalid diff entry skipped: %s", e)
                continue
            try:
                vault.write(note, body="", route_low_confidence=(entry.confidence < _HIGH))
                applied += 1
            except Exception as e:
                log.warning("apply failed: %s", e)
        return applied
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_diff.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/episodist/diff.py tests/episodist/test_diff.py
git commit -m "feat(episodist): add VaultDiff with confidence-gated apply"
```

---

## Task 6 — Compactor (episodes → diff via Haiku)

Reads last 7 episode markdown files from `60-Episodes/`, builds a structured event log, calls Claude Haiku, parses JSON response into a `VaultDiff`. Has a hard token cap to bound LLM cost.

**Files:**
- Create: `yuki/episodist/compactor.py`
- Modify: `yuki/episodist/__init__.py`
- Create: `tests/episodist/test_compactor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/episodist/test_compactor.py`:

```python
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuki.episodist.compactor import compact_last_week


@pytest.fixture
def vault_with_episodes(tmp_path: Path, monkeypatch):
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    eps = vault / "60-Episodes"
    eps.mkdir(parents=True)
    for d in ("2026-05-15", "2026-05-16", "2026-05-17"):
        (eps / f"{d}.md").write_text(f"# {d}\n\nfocused on Slack and GitHub.\n")
    return vault


def test_calls_haiku_and_applies_diff(vault_with_episodes: Path):
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text=(
        '{"entries": [{"action":"create","confidence":0.9,'
        '"note":{"id":"routine-morning","type":"routine","name":"Morning",'
        '"schedule":"weekdays 8am","steps":[],"trusted":false}}]}'
    ))]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp

    with patch("yuki.episodist.compactor._client", return_value=fake_client):
        result = compact_last_week(today=date(2026, 5, 17))

    assert result.applied == 1
    assert (vault_with_episodes / "30-Routines" / "Morning.md").exists()


def test_no_episodes_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "v"))
    (tmp_path / "v" / "60-Episodes").mkdir(parents=True)
    fake_client = MagicMock()
    with patch("yuki.episodist.compactor._client", return_value=fake_client):
        result = compact_last_week(today=date(2026, 5, 17))
    assert result.applied == 0
    fake_client.messages.create.assert_not_called()


def test_haiku_invalid_json_yields_zero_applied(vault_with_episodes: Path):
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text="not json")]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_resp
    with patch("yuki.episodist.compactor._client", return_value=fake_client):
        result = compact_last_week(today=date(2026, 5, 17))
    assert result.applied == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/test_compactor.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/episodist/compactor.py`**

```python
"""Compactor — last-7-days of episodes → vault diff via Claude Haiku."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from yuki.episodist.diff import VaultDiff
from yuki.memory import paths
from yuki.memory.vault import Vault

log = logging.getLogger(__name__)
_MAX_TOKENS = 4000
_DAYS = 7

_PROMPT = """You are inspecting a user's recent computer activity to identify
recurring patterns worth capturing as routines, important people, or apps.

Output ONLY a JSON object with this shape:
{
  "entries": [
    {
      "action": "create",
      "confidence": 0.0..1.0,
      "note": { ...frontmatter for one note, must include id, type, name and
                fields valid for that type per the schema... }
    }, ...
  ]
}

Be conservative. Do not invent details. Only output entries you have
strong evidence for from the episodes below."""


def _client():  # pragma: no cover — real Anthropic client only
    from anthropic import Anthropic
    return Anthropic()


@dataclass
class CompactResult:
    applied: int
    diff: VaultDiff | None


def _gather(today: date) -> list[Path]:
    eps_dir = paths.vault_dir() / "60-Episodes"
    if not eps_dir.exists():
        return []
    out: list[Path] = []
    for i in range(_DAYS):
        d = today - timedelta(days=i)
        f = eps_dir / f"{d.isoformat()}.md"
        if f.exists():
            out.append(f)
    return out


def compact_last_week(*, today: date) -> CompactResult:
    files = _gather(today)
    if not files:
        return CompactResult(applied=0, diff=None)
    body = "\n\n---\n\n".join(p.read_text() for p in files)
    client = _client()
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": f"{_PROMPT}\n\n{body}"}],
    )
    try:
        text = resp.content[0].text
        diff = VaultDiff.from_json(text)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        log.warning("compactor parse failed: %s", e)
        return CompactResult(applied=0, diff=None)
    applied = diff.apply(vault=Vault())
    return CompactResult(applied=applied, diff=diff)
```

- [ ] **Step 4: Update `yuki/episodist/__init__.py`**

```python
"""Episodist: daily episodes + weekly compaction."""

from yuki.episodist.builder import build_for_date
from yuki.episodist.compactor import CompactResult, compact_last_week
from yuki.episodist.diff import DiffEntry, VaultDiff

__all__ = [
    "CompactResult", "DiffEntry", "VaultDiff",
    "build_for_date", "compact_last_week",
]
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/episodist/ -v`
Expected: ≥18 PASS.

- [ ] **Step 6: Run full project suite**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest -v`
Expected: full suite passes.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/episodist/compactor.py yuki/episodist/__init__.py tests/episodist/test_compactor.py
git commit -m "feat(episodist): add weekly compactor via Claude Haiku"
```

---

## Wrap-up

After Task 6:
- `build_for_date(date.today())` writes a daily episode
- `compact_last_week(today=date.today())` proposes routines/people/app updates with confidence gating
- Both are pure entry points; `com.yuki.scheduler.plist` (Plan K) calls them on a schedule
- LLM cost is bounded: one Haiku call per week, max 4000 tokens

Acceptance:
- `uv run pytest tests/episodist/ -v` ≥18 tests, all green
- After running observer for a day + `build_for_date`, `~/YukiVault/60-Episodes/<today>.md` exists with sessions
- After 7 days of episodes + `compact_last_week`, the vault has at least one new note (high-confidence) or inbox entry
