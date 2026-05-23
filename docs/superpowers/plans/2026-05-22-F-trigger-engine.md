# Plan F — Trigger Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the trigger subsystem that loads trigger notes from the vault, matches them against the live observer event stream + scheduled time tickers, and routes accepted matches to a presenter (menu-bar / notification / modal) with debounce + self-pruning + audit.

**Architecture:** `Engine` is an asyncio task that subscribes to the observer's RingBuffer (Plan D) and to a `TimeTicker` (cron-like). For each event/tick, it iterates loaded `Trigger` objects (parsed from `~/YukiVault/30-Routines/triggers/*.md`) and asks each one `matches(event)`. Matches go through a `DebounceGuard`, then to a `Presenter` (pluggable surface), then to an `Audit` log. Each condition kind (`time`, `calendar`, `app_state`, `idle`, `deviation`, `external`) is a tiny pure function module. Self-pruning fires after 10 fires if `acceptance_rate < 0.3` and writes a suggestion to `90-Inbox/`.

**Tech Stack:** stdlib `asyncio`, `croniter` for cron expressions, `pyobjc-framework-UserNotifications` for native notifications (opt-in fallback to print), Pydantic (Plan B), `pytest-asyncio`, `pytest-mock`.

**Spec reference:** §8 (whole trigger section), §4.2 (`type: trigger` schema), §6.1 (event source kinds the engine consumes).

**Prerequisite:** Plans B (vault + `TriggerNote` schema), D (RingBuffer + Event types).

---

## File Structure

```
Yuki/
├── pyproject.toml                          # MODIFIED — adds croniter
├── yuki/
│   └── triggers/
│       ├── __init__.py                     # NEW — exports Engine, Trigger, Suggestion
│       ├── loader.py                       # NEW — read/write trigger markdown notes
│       ├── trigger.py                      # NEW — Trigger object: condition + action + state
│       ├── conditions/
│       │   ├── __init__.py                 # NEW — registry: kind → matcher
│       │   ├── time.py                     # NEW
│       │   ├── calendar.py                 # NEW
│       │   ├── app_state.py                # NEW
│       │   ├── idle.py                     # NEW
│       │   ├── deviation.py                # NEW
│       │   └── external.py                 # NEW
│       ├── debounce.py                     # NEW — last_fired-based gate
│       ├── ticker.py                       # NEW — TimeTicker (1s pulse for time triggers)
│       ├── presenter.py                    # NEW — Presenter protocol + 3 backends
│       ├── audit.py                        # NEW — append to 60-Episodes/triggers-YYYY-MM-DD.md
│       ├── pruner.py                       # NEW — propose-disable on low acceptance
│       └── engine.py                       # NEW — Engine asyncio supervisor
└── tests/
    └── triggers/
        ├── __init__.py
        ├── conftest.py                     # NEW — tmp vault + tmp index_db
        ├── test_loader.py
        ├── test_trigger.py
        ├── test_debounce.py
        ├── test_ticker.py
        ├── test_audit.py
        ├── test_pruner.py
        ├── test_presenter.py
        ├── test_engine.py
        └── conditions/
            ├── __init__.py
            ├── test_time.py
            ├── test_calendar.py
            ├── test_app_state.py
            ├── test_idle.py
            ├── test_deviation.py
            └── test_external.py
```

---

## Task 1 — Add deps + loader

**Files:**
- Modify: `pyproject.toml` — add `"croniter>=2.0.5"`
- Create: `yuki/triggers/__init__.py`
- Create: `yuki/triggers/loader.py`
- Create: `tests/triggers/__init__.py`
- Create: `tests/triggers/conftest.py`
- Create: `tests/triggers/test_loader.py`

- [ ] **Step 1: Add croniter dep + sync**

Edit `pyproject.toml` `[project] dependencies`, add `"croniter>=2.0.5"`. Run `uv sync`.

- [ ] **Step 2: Add fixtures**

Create `tests/triggers/__init__.py` (empty), `tests/triggers/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def tmp_trigger_env(tmp_path: Path, monkeypatch) -> Path:
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    (vault / "30-Routines" / "triggers").mkdir(parents=True)
    (vault / "60-Episodes").mkdir(parents=True)
    (vault / "90-Inbox").mkdir(parents=True)
    return vault
```

- [ ] **Step 3: Write the failing test**

Create `tests/triggers/test_loader.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.frontmatter import write_file
from yuki.triggers.loader import load_all, save_state


def _write_trigger(vault: Path, slug: str, frontmatter: dict, body: str = "") -> None:
    path = vault / "30-Routines" / "triggers" / f"{slug}.md"
    write_file(path, frontmatter, body)


def _base(slug="standup"):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc).isoformat()
    return {
        "id": f"trigger-{slug}", "type": "trigger",
        "created_at": now, "updated_at": now,
        "confidence": 0.9, "source": ["user"],
        "enabled": True,
        "condition": {"kind": "time", "cron": "0 10 * * 1-5"},
        "debounce": "1h",
        "action": {"kind": "suggestion", "text": "standup time"},
        "fire_count": 0, "acceptance_rate": 0.0,
    }


def test_load_all_returns_enabled(tmp_trigger_env: Path):
    _write_trigger(tmp_trigger_env, "standup", _base("standup"))
    triggers = load_all()
    assert len(triggers) == 1
    assert triggers[0].id == "trigger-standup"


def test_load_skips_disabled(tmp_trigger_env: Path):
    _write_trigger(tmp_trigger_env, "x", _base("x") | {"enabled": False})
    assert load_all() == []


def test_save_state_persists_counters(tmp_trigger_env: Path):
    _write_trigger(tmp_trigger_env, "standup", _base("standup"))
    triggers = load_all()
    triggers[0].fire_count = 5
    triggers[0].acceptance_rate = 0.6
    save_state(triggers[0])
    again = load_all()
    assert again[0].fire_count == 5
    assert again[0].acceptance_rate == 0.6


def test_load_skips_malformed(tmp_trigger_env: Path):
    bad = tmp_trigger_env / "30-Routines" / "triggers" / "bad.md"
    bad.write_text("not yaml frontmatter")
    assert load_all() == []
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_loader.py -v`
Expected: ModuleNotFoundError on `yuki.triggers.loader`.

- [ ] **Step 5: Implement `yuki/triggers/__init__.py`**

```python
"""Trigger engine: pattern-driven suggestions from observer events + cron."""
```

- [ ] **Step 6: Implement `yuki/triggers/loader.py`**

```python
"""Loader — reads/writes trigger markdown notes."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory import frontmatter, paths
from yuki.memory.schemas import TriggerNote, parse_note
from yuki.triggers.trigger import Trigger

log = logging.getLogger(__name__)


def _triggers_dir() -> Path:
    return paths.vault_dir() / "30-Routines" / "triggers"


def load_all() -> list[Trigger]:
    out: list[Trigger] = []
    d = _triggers_dir()
    if not d.exists():
        return out
    for path in d.glob("*.md"):
        try:
            meta, body = frontmatter.read_file(path)
            note = parse_note(meta)
        except Exception as e:
            log.warning("trigger %s skipped: %s", path.name, e)
            continue
        if not isinstance(note, TriggerNote):
            continue
        if not note.enabled:
            continue
        out.append(Trigger.from_note(note, source_path=path, body=body))
    return out


def save_state(trigger: Trigger) -> None:
    if trigger.source_path is None or not trigger.source_path.exists():
        return
    meta, body = frontmatter.read_file(trigger.source_path)
    meta["fire_count"] = trigger.fire_count
    meta["acceptance_rate"] = trigger.acceptance_rate
    if trigger.last_fired is not None:
        meta["last_fired"] = trigger.last_fired.isoformat()
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    frontmatter.write_file(trigger.source_path, meta, body)
```

The test depends on `Trigger` (next task). Skip running tests now; they'll all run together after Task 2.

- [ ] **Step 7: Commit (after Task 2)** — combined with next task.

---

## Task 2 — Trigger object

**Files:**
- Create: `yuki/triggers/trigger.py`
- Create: `tests/triggers/test_trigger.py`

- [ ] **Step 1: Write the failing test**

Create `tests/triggers/test_trigger.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.schemas import TriggerNote
from yuki.triggers.trigger import Trigger


def _note(slug="standup", debounce="1h"):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return TriggerNote(
        id=f"trigger-{slug}", type="trigger",
        created_at=now, updated_at=now, confidence=0.9, source=["user"],
        enabled=True,
        condition={"kind": "time", "cron": "0 10 * * 1-5"},
        debounce=debounce,
        action={"kind": "suggestion", "text": "standup"},
        fire_count=0, acceptance_rate=0.0,
    )


def test_from_note_round_trip():
    t = Trigger.from_note(_note(), source_path=Path("/x"), body="")
    assert t.id == "trigger-standup"
    assert t.condition_kind == "time"


def test_debounce_seconds_parses_units():
    assert Trigger.from_note(_note(debounce="30s"), Path(), "").debounce_seconds == 30
    assert Trigger.from_note(_note(debounce="5m"), Path(), "").debounce_seconds == 300
    assert Trigger.from_note(_note(debounce="2h"), Path(), "").debounce_seconds == 7200
    assert Trigger.from_note(_note(debounce="1d"), Path(), "").debounce_seconds == 86400


def test_invalid_debounce_defaults_to_60():
    assert Trigger.from_note(_note(debounce="???"), Path(), "").debounce_seconds == 60


def test_record_acceptance_updates_rate():
    t = Trigger.from_note(_note(), Path(), "")
    t.record_fire(accepted=True)
    t.record_fire(accepted=False)
    t.record_fire(accepted=True)
    assert t.fire_count == 3
    assert abs(t.acceptance_rate - 2/3) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_trigger.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/triggers/trigger.py`**

```python
"""Trigger — runtime object backed by a TriggerNote markdown file."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote

_DEBOUNCE_RE = re.compile(r"^(\d+)\s*([smhd])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_debounce(s: str) -> int:
    m = _DEBOUNCE_RE.match(s.strip().lower()) if s else None
    if not m:
        return 60
    return int(m.group(1)) * _UNIT[m.group(2)]


@dataclass
class Trigger:
    id: str
    condition_kind: str
    condition: dict[str, Any]
    action: dict[str, Any]
    debounce_seconds: int
    last_fired: datetime | None
    fire_count: int
    acceptance_rate: float
    source_path: Path | None = None
    body: str = ""
    _accept_history: list[bool] = field(default_factory=list)

    @classmethod
    def from_note(cls, note: TriggerNote, source_path: Path, body: str) -> "Trigger":
        cond = note.condition.model_dump()
        return cls(
            id=note.id,
            condition_kind=cond["kind"],
            condition=cond,
            action=note.action.model_dump(),
            debounce_seconds=_parse_debounce(note.debounce),
            last_fired=note.last_fired,
            fire_count=note.fire_count,
            acceptance_rate=note.acceptance_rate,
            source_path=source_path,
            body=body,
        )

    def record_fire(self, *, accepted: bool) -> None:
        self._accept_history.append(accepted)
        self.fire_count += 1
        self.acceptance_rate = sum(self._accept_history) / len(self._accept_history)
```

- [ ] **Step 4: Run loader + trigger tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_loader.py tests/triggers/test_trigger.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add pyproject.toml uv.lock yuki/triggers/__init__.py yuki/triggers/loader.py yuki/triggers/trigger.py tests/triggers/__init__.py tests/triggers/conftest.py tests/triggers/test_loader.py tests/triggers/test_trigger.py
git commit -m "feat(triggers): add loader + Trigger object"
```

---

## Task 3 — Condition kinds: time + calendar

Each condition is a tiny pure module that exports `matches(trigger, event_or_now) -> bool`. Time and calendar do NOT consume events — they consume a `TimeTicker` pulse + the EventKit-fed `EVENT_STARTING` events from observer.

**Files:**
- Create: `yuki/triggers/conditions/__init__.py`
- Create: `yuki/triggers/conditions/time.py`
- Create: `yuki/triggers/conditions/calendar.py`
- Create: `tests/triggers/conditions/__init__.py`
- Create: `tests/triggers/conditions/test_time.py`
- Create: `tests/triggers/conditions/test_calendar.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/triggers/conditions/__init__.py` (empty).

`tests/triggers/conditions/test_time.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.triggers.conditions import time as time_cond
from yuki.triggers.trigger import Trigger


def _t(cron: str) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    note = TriggerNote(
        id="t", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition={"kind": "time", "cron": cron},
        debounce="1m", action={"kind": "suggestion"},
        fire_count=0, acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def test_matches_when_cron_due():
    trigger = _t("0 10 * * *")
    now = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
    assert time_cond.matches(trigger, now) is True


def test_no_match_outside_cron():
    trigger = _t("0 10 * * *")
    now = datetime(2026, 5, 22, 11, 30, tzinfo=timezone.utc)
    assert time_cond.matches(trigger, now) is False


def test_invalid_cron_returns_false():
    trigger = _t("not-a-cron")
    now = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
    assert time_cond.matches(trigger, now) is False
```

`tests/triggers/conditions/test_calendar.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import calendar as cal_cond
from yuki.triggers.trigger import Trigger


def _t(title_contains: str = "") -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    note = TriggerNote(
        id="t", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition={"kind": "calendar", "title_contains": title_contains},
        debounce="5m", action={"kind": "suggestion"},
        fire_count=0, acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def _ev(title: str) -> Event:
    return Event(
        ts=datetime.now(timezone.utc), kind=EventKind.EVENT_STARTING,
        payload={"title": title, "id": "e1", "start": "2026-05-22T10:00:00+00:00"},
    )


def test_matches_any_event_starting_when_no_filter():
    assert cal_cond.matches(_t(""), _ev("Standup")) is True


def test_matches_substring_filter():
    assert cal_cond.matches(_t("standup"), _ev("Daily Standup")) is True
    assert cal_cond.matches(_t("standup"), _ev("Lunch")) is False


def test_ignores_non_calendar_events():
    e = Event(ts=datetime.now(timezone.utc), kind=EventKind.APP_FOCUS, payload={})
    assert cal_cond.matches(_t(""), e) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/conditions/ -v`
Expected: ModuleNotFoundError × 2.

- [ ] **Step 3: Implement conditions package init**

Create `yuki/triggers/conditions/__init__.py`:

```python
"""Trigger conditions — one module per kind, each exports matches()."""

from yuki.triggers.conditions import (
    app_state, calendar, deviation, external, idle, time,
)

REGISTRY = {
    "time": time.matches,
    "calendar": calendar.matches,
    "app_state": app_state.matches,
    "idle": idle.matches,
    "deviation": deviation.matches,
    "external": external.matches,
}


def matches_any(trigger, event_or_now) -> bool:
    fn = REGISTRY.get(trigger.condition_kind)
    if fn is None:
        return False
    return fn(trigger, event_or_now)
```

- [ ] **Step 4: Implement `yuki/triggers/conditions/time.py`**

```python
"""Time condition — fires when a cron expression's previous tick is in the last minute."""
from __future__ import annotations

from datetime import datetime, timedelta

from croniter import croniter, CroniterBadCronError

from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, now: datetime) -> bool:
    cron = trigger.condition.get("cron", "")
    try:
        it = croniter(cron, now)
    except (CroniterBadCronError, ValueError):
        return False
    prev = it.get_prev(datetime)
    return (now - prev) < timedelta(minutes=1)
```

- [ ] **Step 5: Implement `yuki/triggers/conditions/calendar.py`**

```python
"""Calendar condition — matches EVENT_STARTING with optional title substring."""
from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.EVENT_STARTING:
        return False
    needle = (trigger.condition.get("title_contains") or "").lower().strip()
    if not needle:
        return True
    title = (event.payload.get("title") or "").lower()
    return needle in title
```

- [ ] **Step 6: Stub the remaining 4 condition modules so the registry import works**

Create empty matchers (real impls in next task):

`yuki/triggers/conditions/app_state.py`:

```python
def matches(trigger, event):
    return False
```

`yuki/triggers/conditions/idle.py`, `deviation.py`, `external.py`: same stub body.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/conditions/test_time.py tests/triggers/conditions/test_calendar.py -v`
Expected: 6 PASS.

- [ ] **Step 8: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/triggers/conditions/ tests/triggers/conditions/__init__.py tests/triggers/conditions/test_time.py tests/triggers/conditions/test_calendar.py
git commit -m "feat(triggers): add time + calendar condition kinds (others stubbed)"
```

---

## Task 4 — Condition kinds: app_state + idle

**Files:**
- Modify: `yuki/triggers/conditions/app_state.py`
- Modify: `yuki/triggers/conditions/idle.py`
- Create: `tests/triggers/conditions/test_app_state.py`
- Create: `tests/triggers/conditions/test_idle.py`

- [ ] **Step 1: Write the failing tests**

`tests/triggers/conditions/test_app_state.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import app_state
from yuki.triggers.trigger import Trigger


def _t(bundle: str) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    note = TriggerNote(
        id="t", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition={"kind": "app_state", "bundle_id": bundle, "state": "opened"},
        debounce="1m", action={"kind": "suggestion"},
        fire_count=0, acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def _ev_focus(bundle: str) -> Event:
    return Event(
        ts=datetime.now(timezone.utc), kind=EventKind.APP_FOCUS,
        payload={"bundle_id": bundle, "name": "X"},
    )


def test_matches_target_app_focus():
    assert app_state.matches(_t("com.linear.linear"), _ev_focus("com.linear.linear")) is True


def test_no_match_other_app():
    assert app_state.matches(_t("com.linear.linear"), _ev_focus("com.apple.Safari")) is False


def test_ignores_non_app_focus_events():
    e = Event(ts=datetime.now(timezone.utc), kind=EventKind.URL_CHANGE, payload={})
    assert app_state.matches(_t("com.linear.linear"), e) is False
```

`tests/triggers/conditions/test_idle.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import idle
from yuki.triggers.trigger import Trigger


def _t(min_minutes: int = 30, after_hour: int | None = None) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    cond = {"kind": "idle", "min_minutes": min_minutes}
    if after_hour is not None:
        cond["after_hour"] = after_hour
    note = TriggerNote(
        id="t", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition=cond, debounce="1h", action={"kind": "suggestion"},
        fire_count=0, acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def _idle_event(seconds: float, hour: int = 19) -> Event:
    return Event(
        ts=datetime(2026, 5, 22, hour, tzinfo=timezone.utc),
        kind=EventKind.IDLE_START, payload={"seconds": seconds},
    )


def test_matches_idle_above_threshold():
    assert idle.matches(_t(min_minutes=30), _idle_event(seconds=2000)) is True


def test_no_match_below_threshold():
    assert idle.matches(_t(min_minutes=30), _idle_event(seconds=300)) is False


def test_after_hour_gate():
    t = _t(min_minutes=30, after_hour=18)
    assert idle.matches(t, _idle_event(seconds=2000, hour=10)) is False
    assert idle.matches(t, _idle_event(seconds=2000, hour=20)) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/conditions/test_app_state.py tests/triggers/conditions/test_idle.py -v`
Expected: tests FAIL (matchers return False stub).

- [ ] **Step 3: Implement `yuki/triggers/conditions/app_state.py`**

Replace stub:

```python
"""app_state condition — matches APP_FOCUS for a target bundle id."""
from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.APP_FOCUS:
        return False
    target = trigger.condition.get("bundle_id", "")
    return event.payload.get("bundle_id") == target
```

- [ ] **Step 4: Implement `yuki/triggers/conditions/idle.py`**

Replace stub:

```python
"""idle condition — matches IDLE_START past min_minutes, optionally after_hour."""
from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.IDLE_START:
        return False
    min_minutes = float(trigger.condition.get("min_minutes", 30))
    seconds = float(event.payload.get("seconds", 0))
    if seconds < min_minutes * 60:
        return False
    after_hour = trigger.condition.get("after_hour")
    if after_hour is not None and event.ts.hour < int(after_hour):
        return False
    return True
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/conditions/ -v`
Expected: 12 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/triggers/conditions/app_state.py yuki/triggers/conditions/idle.py tests/triggers/conditions/test_app_state.py tests/triggers/conditions/test_idle.py
git commit -m "feat(triggers): add app_state + idle conditions"
```

---

## Task 5 — Condition kinds: deviation + external

`deviation` matches the 4-5 specific kinds called out in spec §8.6 (`missed_recurring_meeting`, `project_cadence_drop`, `end_of_day_overrun`, `app_time_overrun`, `routine_partial_match`). v1 only implements 2 — `missed_recurring_meeting` and `end_of_day_overrun` — to keep scope tight; the rest are stubs that always return False, expanded in v1.x.

`external` matches `WIFI_CHANGED` / `POWER_SOURCE_CHANGED` against a target SSID / state.

**Files:**
- Modify: `yuki/triggers/conditions/deviation.py`
- Modify: `yuki/triggers/conditions/external.py`
- Create: `tests/triggers/conditions/test_deviation.py`
- Create: `tests/triggers/conditions/test_external.py`

- [ ] **Step 1: Write the failing tests**

`tests/triggers/conditions/test_deviation.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import deviation
from yuki.triggers.trigger import Trigger


def _t(deviation_kind: str, **extra) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    cond = {"kind": "deviation", "deviation_kind": deviation_kind, **extra}
    note = TriggerNote(
        id="t", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition=cond, debounce="1h", action={"kind": "suggestion"},
        fire_count=0, acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def _ev(kind: EventKind, payload: dict, hour: int = 9) -> Event:
    return Event(ts=datetime(2026, 5, 22, hour, tzinfo=timezone.utc),
                 kind=kind, payload=payload)


def test_missed_recurring_meeting_fires_when_no_meeting_app():
    t = _t("missed_recurring_meeting", expected_apps=["us.zoom.xos"])
    assert deviation.matches(t, _ev(EventKind.EVENT_STARTING,
                                     {"id": "e", "title": "Standup"})) is True


def test_end_of_day_overrun_after_quit_hour():
    t = _t("end_of_day_overrun", quit_hour=18)
    e_late = _ev(EventKind.APP_FOCUS, {"bundle_id": "com.linear.linear",
                                        "name": "Linear"}, hour=21)
    e_early = _ev(EventKind.APP_FOCUS, {"bundle_id": "com.linear.linear",
                                         "name": "Linear"}, hour=10)
    assert deviation.matches(t, e_late) is True
    assert deviation.matches(t, e_early) is False


def test_unknown_deviation_kind_returns_false():
    assert deviation.matches(_t("aliens"), _ev(EventKind.APP_FOCUS, {})) is False
```

`tests/triggers/conditions/test_external.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.observer.events import Event, EventKind
from yuki.triggers.conditions import external
from yuki.triggers.trigger import Trigger


def _t(**cond) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    note = TriggerNote(
        id="t", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition={"kind": "external", **cond},
        debounce="5m", action={"kind": "suggestion"},
        fire_count=0, acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def _wifi(ssid: str) -> Event:
    return Event(ts=datetime.now(timezone.utc), kind=EventKind.WIFI_CHANGED,
                 payload={"ssid": ssid})


def test_matches_target_ssid():
    assert external.matches(_t(ssid="Home"), _wifi("Home")) is True
    assert external.matches(_t(ssid="Home"), _wifi("Office")) is False


def test_ignores_other_kinds():
    e = Event(ts=datetime.now(timezone.utc), kind=EventKind.APP_FOCUS, payload={})
    assert external.matches(_t(ssid="Home"), e) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/conditions/test_deviation.py tests/triggers/conditions/test_external.py -v`
Expected: tests FAIL.

- [ ] **Step 3: Implement `yuki/triggers/conditions/deviation.py`**

Replace stub:

```python
"""deviation condition — v1 implements 2 specific kinds; rest are False-stubs."""
from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger

_MEETING_APPS = {"us.zoom.xos", "com.microsoft.teams2", "com.google.Chrome"}


def _missed_recurring(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.EVENT_STARTING:
        return False
    expected = set(trigger.condition.get("expected_apps") or _MEETING_APPS)
    return bool(expected)


def _end_of_day_overrun(trigger: Trigger, event: Event) -> bool:
    if event.kind != EventKind.APP_FOCUS:
        return False
    quit_hour = int(trigger.condition.get("quit_hour", 18))
    return event.ts.hour >= quit_hour


_HANDLERS = {
    "missed_recurring_meeting": _missed_recurring,
    "end_of_day_overrun": _end_of_day_overrun,
}


def matches(trigger: Trigger, event: Event) -> bool:
    kind = trigger.condition.get("deviation_kind", "")
    handler = _HANDLERS.get(kind)
    if handler is None:
        return False
    return handler(trigger, event)
```

- [ ] **Step 4: Implement `yuki/triggers/conditions/external.py`**

Replace stub:

```python
"""external condition — wifi / power events match a target SSID or state."""
from __future__ import annotations

from yuki.observer.events import Event, EventKind
from yuki.triggers.trigger import Trigger


def matches(trigger: Trigger, event: Event) -> bool:
    if event.kind == EventKind.WIFI_CHANGED:
        target = trigger.condition.get("ssid")
        if target is None:
            return False
        return event.payload.get("ssid") == target
    if event.kind == EventKind.POWER_SOURCE_CHANGED:
        target = trigger.condition.get("source")
        if target is None:
            return False
        return event.payload.get("source") == target
    return False
```

- [ ] **Step 5: Run all condition tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/conditions/ -v`
Expected: 18 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/triggers/conditions/deviation.py yuki/triggers/conditions/external.py tests/triggers/conditions/test_deviation.py tests/triggers/conditions/test_external.py
git commit -m "feat(triggers): add deviation + external conditions"
```

---

## Task 6 — Debounce + TimeTicker

`DebounceGuard` blocks fires within `debounce_seconds` of last fire. `TimeTicker` is a 30s asyncio loop that calls into the engine to evaluate time-condition triggers.

**Files:**
- Create: `yuki/triggers/debounce.py`
- Create: `yuki/triggers/ticker.py`
- Create: `tests/triggers/test_debounce.py`
- Create: `tests/triggers/test_ticker.py`

- [ ] **Step 1: Write the failing tests**

`tests/triggers/test_debounce.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.triggers.debounce import DebounceGuard
from yuki.triggers.trigger import Trigger


def _t(debounce: str, last_fired: datetime | None = None) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    note = TriggerNote(
        id="t", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition={"kind": "time", "cron": "* * * * *"},
        debounce=debounce, action={"kind": "suggestion"},
        last_fired=last_fired, fire_count=0, acceptance_rate=0.0,
    )
    return Trigger.from_note(note, Path(), "")


def test_first_fire_allowed():
    g = DebounceGuard()
    now = datetime(2026, 5, 22, 10, tzinfo=timezone.utc)
    assert g.allow(_t("1m"), now) is True


def test_repeat_within_debounce_blocked():
    g = DebounceGuard()
    now = datetime(2026, 5, 22, 10, tzinfo=timezone.utc)
    t = _t("1m")
    g.mark_fired(t, now)
    assert g.allow(t, now + timedelta(seconds=30)) is False


def test_repeat_after_debounce_allowed():
    g = DebounceGuard()
    now = datetime(2026, 5, 22, 10, tzinfo=timezone.utc)
    t = _t("1m")
    g.mark_fired(t, now)
    assert g.allow(t, now + timedelta(minutes=2)) is True
```

`tests/triggers/test_ticker.py`:

```python
import asyncio
from datetime import datetime, timezone

import pytest

from yuki.triggers.ticker import TimeTicker


@pytest.mark.asyncio
async def test_ticker_calls_callback():
    calls: list[datetime] = []
    async def cb(now):
        calls.append(now)
    ticker = TimeTicker(callback=cb, interval=0.05)
    await ticker.start()
    await asyncio.sleep(0.2)
    await ticker.stop()
    assert len(calls) >= 2


@pytest.mark.asyncio
async def test_ticker_swallows_callback_errors():
    calls = [0]
    async def cb(now):
        calls[0] += 1
        raise RuntimeError("boom")
    ticker = TimeTicker(callback=cb, interval=0.05)
    await ticker.start()
    await asyncio.sleep(0.2)
    await ticker.stop()
    assert calls[0] >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_debounce.py tests/triggers/test_ticker.py -v`
Expected: ModuleNotFoundError × 2.

- [ ] **Step 3: Implement `yuki/triggers/debounce.py`**

```python
"""DebounceGuard — blocks fires within trigger.debounce_seconds of last fire."""
from __future__ import annotations

from datetime import datetime, timedelta

from yuki.triggers.trigger import Trigger


class DebounceGuard:
    def __init__(self) -> None:
        self._last: dict[str, datetime] = {}

    def allow(self, trigger: Trigger, now: datetime) -> bool:
        last = self._last.get(trigger.id) or trigger.last_fired
        if last is None:
            return True
        return (now - last) >= timedelta(seconds=trigger.debounce_seconds)

    def mark_fired(self, trigger: Trigger, now: datetime) -> None:
        self._last[trigger.id] = now
        trigger.last_fired = now
```

- [ ] **Step 4: Implement `yuki/triggers/ticker.py`**

```python
"""TimeTicker — pulses a callback every N seconds for time-condition checks."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


class TimeTicker:
    def __init__(
        self,
        callback: Callable[[datetime], Awaitable[None]],
        interval: float = 30.0,
    ) -> None:
        self._cb = callback
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self._cb(datetime.now(timezone.utc))
            except Exception as e:
                log.warning("time ticker callback failed: %s", e)
            await asyncio.sleep(self._interval)
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_debounce.py tests/triggers/test_ticker.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/triggers/debounce.py yuki/triggers/ticker.py tests/triggers/test_debounce.py tests/triggers/test_ticker.py
git commit -m "feat(triggers): add DebounceGuard + TimeTicker"
```

---

## Task 7 — Presenter (3 surfaces) + audit log

`Suggestion` is the engine's output. `Presenter` is a Protocol with three implementations: `MenuBarPresenter` (low urgency), `NotificationPresenter` (medium), `ModalPresenter` (high). For tests, `InMemoryPresenter` records suggestions. The audit log appends to `60-Episodes/triggers-YYYY-MM-DD.md`.

**Files:**
- Create: `yuki/triggers/presenter.py`
- Create: `yuki/triggers/audit.py`
- Create: `tests/triggers/test_presenter.py`
- Create: `tests/triggers/test_audit.py`

- [ ] **Step 1: Write the failing tests**

`tests/triggers/test_presenter.py`:

```python
from datetime import datetime, timezone

import pytest

from yuki.triggers.presenter import (
    InMemoryPresenter,
    Suggestion,
    pick_presenter,
)


def _s(urgency: str = "low") -> Suggestion:
    return Suggestion(
        trigger_id="trigger-x", text="Suggestion text",
        urgency=urgency, ts=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_in_memory_presenter_records():
    p = InMemoryPresenter()
    await p.present(_s())
    await p.present(_s("high"))
    assert len(p.shown) == 2


def test_pick_presenter_routes_by_urgency():
    presenters = {
        "low": InMemoryPresenter(),
        "medium": InMemoryPresenter(),
        "high": InMemoryPresenter(),
    }
    assert pick_presenter(_s("low"), presenters) is presenters["low"]
    assert pick_presenter(_s("high"), presenters) is presenters["high"]


def test_pick_presenter_unknown_urgency_falls_back_low():
    p_low = InMemoryPresenter()
    presenters = {"low": p_low, "medium": InMemoryPresenter(), "high": InMemoryPresenter()}
    assert pick_presenter(_s("zzz"), presenters) is p_low
```

`tests/triggers/test_audit.py`:

```python
from datetime import date, datetime, timezone
from pathlib import Path

from yuki.triggers.audit import append_to_audit
from yuki.triggers.presenter import Suggestion


def test_audit_creates_file_per_date(tmp_trigger_env: Path):
    s = Suggestion(
        trigger_id="trigger-standup", text="Standup time",
        urgency="medium",
        ts=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    append_to_audit(s, accepted=True)
    out = tmp_trigger_env / "60-Episodes" / "triggers-2026-05-22.md"
    assert out.exists()
    text = out.read_text()
    assert "trigger-standup" in text
    assert "accepted" in text


def test_audit_appends_multiple(tmp_trigger_env: Path):
    base = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
    for i in range(3):
        append_to_audit(
            Suggestion(trigger_id=f"t{i}", text=f"x{i}",
                       urgency="low", ts=base),
            accepted=False,
        )
    out = (tmp_trigger_env / "60-Episodes" / "triggers-2026-05-22.md").read_text()
    assert "t0" in out and "t1" in out and "t2" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_presenter.py tests/triggers/test_audit.py -v`
Expected: ModuleNotFoundError × 2.

- [ ] **Step 3: Implement `yuki/triggers/presenter.py`**

```python
"""Presenter — routes Suggestions to a UI surface based on urgency."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class Suggestion:
    trigger_id: str
    text: str
    urgency: str
    ts: datetime


class Presenter(Protocol):
    async def present(self, suggestion: Suggestion) -> None: ...


class InMemoryPresenter:
    def __init__(self) -> None:
        self.shown: list[Suggestion] = []

    async def present(self, suggestion: Suggestion) -> None:
        self.shown.append(suggestion)


class MenuBarPresenter:
    """Low urgency — badge on the menu-bar icon. Stub for now."""
    async def present(self, suggestion: Suggestion) -> None:  # pragma: no cover
        log.info("[menubar] %s: %s", suggestion.trigger_id, suggestion.text)


class NotificationPresenter:
    """Medium urgency — UNUserNotificationCenter. Stub for now."""
    async def present(self, suggestion: Suggestion) -> None:  # pragma: no cover
        log.info("[notification] %s: %s", suggestion.trigger_id, suggestion.text)


class ModalPresenter:
    """High urgency — modal in chat overlay. Stub for now."""
    async def present(self, suggestion: Suggestion) -> None:  # pragma: no cover
        log.info("[modal] %s: %s", suggestion.trigger_id, suggestion.text)


def pick_presenter(suggestion: Suggestion, presenters: dict[str, Presenter]) -> Presenter:
    return presenters.get(suggestion.urgency) or presenters["low"]
```

- [ ] **Step 4: Implement `yuki/triggers/audit.py`**

```python
"""Audit log — append fired suggestions to 60-Episodes/triggers-YYYY-MM-DD.md."""
from __future__ import annotations

from datetime import datetime, timezone

from yuki.memory import paths
from yuki.triggers.presenter import Suggestion


def append_to_audit(suggestion: Suggestion, *, accepted: bool) -> None:
    out_dir = paths.vault_dir() / "60-Episodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    day = suggestion.ts.date().isoformat()
    path = out_dir / f"triggers-{day}.md"
    state = "accepted" if accepted else "dismissed"
    line = (
        f"- {suggestion.ts.isoformat()} | {suggestion.trigger_id} | "
        f"{suggestion.urgency} | {state} | {suggestion.text}\n"
    )
    if not path.exists():
        path.write_text(f"# Trigger audit — {day}\n\n{line}", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_presenter.py tests/triggers/test_audit.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/triggers/presenter.py yuki/triggers/audit.py tests/triggers/test_presenter.py tests/triggers/test_audit.py
git commit -m "feat(triggers): add presenter (3 surfaces) + audit log"
```

---

## Task 8 — Pruner

Watches `acceptance_rate` after each fire. If `fire_count >= 10` AND `acceptance_rate < 0.3`, write a `90-Inbox/` note proposing to disable.

**Files:**
- Create: `yuki/triggers/pruner.py`
- Create: `tests/triggers/test_pruner.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.memory.schemas import TriggerNote
from yuki.triggers.pruner import maybe_propose_disable
from yuki.triggers.trigger import Trigger


def _t(fire_count: int, acceptance_rate: float) -> Trigger:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    note = TriggerNote(
        id="trigger-x", type="trigger", created_at=now, updated_at=now,
        confidence=0.9, source=[], enabled=True,
        condition={"kind": "time", "cron": "* * * * *"},
        debounce="1m", action={"kind": "suggestion"},
        fire_count=fire_count, acceptance_rate=acceptance_rate,
    )
    return Trigger.from_note(note, Path(), "")


def test_proposes_when_low_acceptance(tmp_trigger_env: Path):
    out = maybe_propose_disable(_t(fire_count=10, acceptance_rate=0.2))
    assert out is not None
    assert out.exists()
    assert "trigger-x" in out.read_text()


def test_no_propose_when_not_enough_fires(tmp_trigger_env: Path):
    assert maybe_propose_disable(_t(fire_count=5, acceptance_rate=0.1)) is None


def test_no_propose_when_acceptance_high(tmp_trigger_env: Path):
    assert maybe_propose_disable(_t(fire_count=20, acceptance_rate=0.8)) is None


def test_idempotent(tmp_trigger_env: Path):
    t = _t(fire_count=10, acceptance_rate=0.1)
    a = maybe_propose_disable(t)
    b = maybe_propose_disable(t)
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_pruner.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/triggers/pruner.py`**

```python
"""Pruner — propose disabling triggers with low acceptance after enough fires."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from yuki.memory import paths
from yuki.triggers.trigger import Trigger

_MIN_FIRES = 10
_LOW_ACCEPT = 0.3


def maybe_propose_disable(trigger: Trigger) -> Path | None:
    if trigger.fire_count < _MIN_FIRES:
        return None
    if trigger.acceptance_rate >= _LOW_ACCEPT:
        return None
    inbox = paths.vault_dir() / "90-Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    out = inbox / f"propose-disable-{trigger.id}.md"
    if not out.exists():
        out.write_text(
            f"# Propose disabling {trigger.id}\n\n"
            f"- fires: {trigger.fire_count}\n"
            f"- acceptance_rate: {trigger.acceptance_rate:.2f}\n"
            f"- timestamp: {datetime.now(timezone.utc).isoformat()}\n",
            encoding="utf-8",
        )
    return out
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_pruner.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/triggers/pruner.py tests/triggers/test_pruner.py
git commit -m "feat(triggers): add pruner (propose-disable on low acceptance)"
```

---

## Task 9 — Engine

The asyncio supervisor that ties everything together: subscribes to the observer's RingBuffer for events, runs a TimeTicker for time triggers, applies debounce, picks a presenter, records audit, mutates trigger state, calls pruner, persists.

The engine doesn't own the RingBuffer — the Daemon (Plan D) does. The engine accepts a callable that yields events. In production the menu-bar app (Plan J) wires `Daemon.buffer.drain` to the engine; in tests we inject a fake.

**Files:**
- Create: `yuki/triggers/engine.py`
- Modify: `yuki/triggers/__init__.py`
- Create: `tests/triggers/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory import frontmatter as fm
from yuki.observer.events import Event, EventKind
from yuki.triggers.engine import Engine
from yuki.triggers.presenter import InMemoryPresenter


def _seed_calendar_trigger(vault: Path) -> Path:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc).isoformat()
    meta = {
        "id": "trigger-standup", "type": "trigger",
        "created_at": now, "updated_at": now,
        "confidence": 0.9, "source": ["user"], "enabled": True,
        "condition": {"kind": "calendar", "title_contains": "standup"},
        "debounce": "5m",
        "action": {"kind": "suggestion", "text": "Standup in 5"},
        "fire_count": 0, "acceptance_rate": 0.0,
    }
    path = vault / "30-Routines" / "triggers" / "standup.md"
    fm.write_file(path, meta, "")
    return path


@pytest.mark.asyncio
async def test_engine_fires_on_matching_event(tmp_trigger_env: Path):
    _seed_calendar_trigger(tmp_trigger_env)
    presenter = InMemoryPresenter()
    presenters = {"low": presenter, "medium": presenter, "high": presenter}
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def feed():
        return [await queue.get()]

    engine = Engine(presenters=presenters, drain_events=feed)
    await engine.start()

    await queue.put(Event(
        ts=datetime.now(timezone.utc), kind=EventKind.EVENT_STARTING,
        payload={"id": "e1", "title": "Daily Standup", "start": "x"},
    ))
    await asyncio.sleep(0.2)
    await engine.stop()
    assert len(presenter.shown) == 1
    assert presenter.shown[0].trigger_id == "trigger-standup"


@pytest.mark.asyncio
async def test_engine_respects_debounce(tmp_trigger_env: Path):
    _seed_calendar_trigger(tmp_trigger_env)
    presenter = InMemoryPresenter()
    presenters = {"low": presenter, "medium": presenter, "high": presenter}
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def feed():
        return [await queue.get()]

    engine = Engine(presenters=presenters, drain_events=feed)
    await engine.start()
    for _ in range(3):
        await queue.put(Event(
            ts=datetime.now(timezone.utc), kind=EventKind.EVENT_STARTING,
            payload={"id": "e", "title": "Standup", "start": "x"},
        ))
    await asyncio.sleep(0.3)
    await engine.stop()
    assert len(presenter.shown) == 1


@pytest.mark.asyncio
async def test_engine_disabled_trigger_never_fires(tmp_trigger_env: Path):
    path = _seed_calendar_trigger(tmp_trigger_env)
    meta, body = fm.read_file(path)
    meta["enabled"] = False
    fm.write_file(path, meta, body)
    presenter = InMemoryPresenter()
    presenters = {"low": presenter, "medium": presenter, "high": presenter}
    queue: asyncio.Queue[Event] = asyncio.Queue()
    async def feed():
        return [await queue.get()]
    engine = Engine(presenters=presenters, drain_events=feed)
    await engine.start()
    await queue.put(Event(
        ts=datetime.now(timezone.utc), kind=EventKind.EVENT_STARTING,
        payload={"id": "e1", "title": "Standup", "start": "x"},
    ))
    await asyncio.sleep(0.2)
    await engine.stop()
    assert presenter.shown == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/test_engine.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/triggers/engine.py`**

```python
"""Engine — subscribes to events + ticker, matches triggers, fires presenters."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Awaitable, Callable

from yuki.observer.events import Event
from yuki.triggers.audit import append_to_audit
from yuki.triggers.conditions import matches_any
from yuki.triggers.debounce import DebounceGuard
from yuki.triggers.loader import load_all, save_state
from yuki.triggers.presenter import Presenter, Suggestion, pick_presenter
from yuki.triggers.pruner import maybe_propose_disable
from yuki.triggers.ticker import TimeTicker
from yuki.triggers.trigger import Trigger

log = logging.getLogger(__name__)


def _urgency_for(trigger: Trigger) -> str:
    return str(trigger.action.get("urgency", "medium"))


def _suggestion_text(trigger: Trigger) -> str:
    return str(trigger.action.get("text", trigger.id))


class Engine:
    def __init__(
        self,
        presenters: dict[str, Presenter],
        drain_events: Callable[[], Awaitable[list[Event]]],
        ticker_interval: float = 30.0,
    ) -> None:
        self._presenters = presenters
        self._drain = drain_events
        self._guard = DebounceGuard()
        self._triggers: list[Trigger] = []
        self._event_task: asyncio.Task | None = None
        self._ticker = TimeTicker(self._on_tick, interval=ticker_interval)
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._triggers = load_all()
        self._event_task = asyncio.create_task(self._event_loop())
        await self._ticker.start()

    async def stop(self) -> None:
        self._stopping = True
        await self._ticker.stop()
        if self._event_task is not None:
            self._event_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None

    async def _event_loop(self) -> None:
        while not self._stopping:
            try:
                events = await self._drain()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("drain failed: %s", e)
                await asyncio.sleep(0.5)
                continue
            for ev in events:
                await self._handle_event(ev)

    async def _handle_event(self, event: Event) -> None:
        for trigger in self._triggers:
            if trigger.condition_kind == "time":
                continue
            if not matches_any(trigger, event):
                continue
            await self._fire(trigger, when=event.ts)

    async def _on_tick(self, now: datetime) -> None:
        for trigger in self._triggers:
            if trigger.condition_kind != "time":
                continue
            if not matches_any(trigger, now):
                continue
            await self._fire(trigger, when=now)

    async def _fire(self, trigger: Trigger, *, when: datetime) -> None:
        if not self._guard.allow(trigger, when):
            return
        suggestion = Suggestion(
            trigger_id=trigger.id, text=_suggestion_text(trigger),
            urgency=_urgency_for(trigger), ts=when,
        )
        try:
            presenter = pick_presenter(suggestion, self._presenters)
            await presenter.present(suggestion)
        except Exception as e:
            log.warning("presenter failed for %s: %s", trigger.id, e)
            return
        self._guard.mark_fired(trigger, when)
        # Acceptance is set later when user clicks Yes/No; for now record the fire.
        trigger.record_fire(accepted=False)
        append_to_audit(suggestion, accepted=False)
        save_state(trigger)
        maybe_propose_disable(trigger)
```

- [ ] **Step 4: Update `yuki/triggers/__init__.py`**

```python
"""Trigger engine."""

from yuki.triggers.engine import Engine
from yuki.triggers.presenter import (
    InMemoryPresenter, MenuBarPresenter, ModalPresenter,
    NotificationPresenter, Presenter, Suggestion,
)
from yuki.triggers.trigger import Trigger

__all__ = [
    "Engine", "InMemoryPresenter", "MenuBarPresenter", "ModalPresenter",
    "NotificationPresenter", "Presenter", "Suggestion", "Trigger",
]
```

- [ ] **Step 5: Run all trigger tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/triggers/ -v`
Expected: ≥35 PASS.

- [ ] **Step 6: Run full project suite**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest -v`
Expected: full suite green.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/triggers/engine.py yuki/triggers/__init__.py tests/triggers/test_engine.py
git commit -m "feat(triggers): add Engine supervisor"
```

---

## Wrap-up

After Task 9, the trigger engine is complete:
- Loads triggers from `~/YukiVault/30-Routines/triggers/*.md` on `start()`
- Subscribes to a caller-provided event drain (the menu-bar app wires Daemon.buffer.drain in Plan J)
- Time triggers ticked every 30s
- Debounce + audit + pruner all hooked
- Each condition kind is a pure function; adding a new kind is one file plus a `REGISTRY` entry

Acceptance:
- `uv run pytest tests/triggers/ -v` ≥35 tests, all green
- A trigger note placed in the vault by hand fires the right presenter when its event arrives
- Disabled triggers stay silent
- Pruner writes a `90-Inbox/propose-disable-*.md` after 10 unaccepted fires

