# Plan C — Onboarding Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the one-time first-run scanner that crawls 10 macOS data sources, normalizes raw rows into typed Facts, clusters Facts into Entities (people, projects, routines, apps), and writes seed notes into the markdown vault built in Plan B.

**Architecture:** Four-stage pipeline (`scan/runner.py` orchestrates). Stage 1 — collectors run in parallel (asyncio.gather), each writes raw JSON to `~/Library/Caches/Yuki/scan/raw/<name>.json`. Stage 2 — normalizer reads those and emits unified `Fact` tuples. Stage 3 — rule-based pattern detector groups Facts into typed `Entity` bundles. Stage 4 — Jinja templates render Entities to markdown notes (LLM polish path opt-in). Each collector handles missing permissions / missing data gracefully by returning an empty list — no permission is required.

**Tech Stack:** stdlib `asyncio` + `subprocess`, `sqlite3` for native macOS DBs (Knowledge, AddressBook, Mail Envelope Index, browser histories), `EventKit`-via-`pyobjc` for calendar, `jinja2` for templates, `anthropic` (already a Plan A dep) for optional Haiku polish, `pytest` + `pytest-mock` for tests.

**Spec reference:** `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` §5 (whole onboarding section), §4.2 (note schemas — all entity output must validate against these), §11.2 (LLM privacy — optional Haiku batch only sees facts, never raw rows).

**Prerequisite:** Plan B complete — `Vault.write()` exists, schemas validated, `memory_write` tool present.

---

## Resolved open questions

1. **Parallelism** — `asyncio.gather` with a 60-second per-collector timeout. Slow / hanging collectors return empty rather than block the scan.
2. **Cache location** — `~/Library/Caches/Yuki/scan/raw/<collector>.json` per spec §5.2. Path overridable via `YUKI_SCAN_CACHE` env for tests.
3. **LLM polish opt-in** — `runner.run(polish=False)` is the default. UI sets `polish=True` if user opted in on the consent screen. Polish runs as a single batched Haiku call over all entities flagged "rich-but-ambiguous".
4. **Re-running the scan** — guard with `~/YukiVault/.scan_complete` sentinel. `runner.run(force=True)` overrides; UI never sets force.

---

## File Structure

```
Yuki/
├── pyproject.toml                          # MODIFIED — adds jinja2 (others already present)
├── yuki/
│   └── scan/
│       ├── __init__.py                     # NEW — exports run, Fact, Entity
│       ├── paths.py                        # NEW — cache dir + sentinel path
│       ├── facts.py                        # NEW — Fact dataclass + helpers
│       ├── entities.py                     # NEW — Entity dataclass + helpers
│       ├── runner.py                       # NEW — orchestrator
│       ├── collectors/
│       │   ├── __init__.py                 # NEW — registry of collectors
│       │   ├── base.py                     # NEW — Collector protocol + run_with_timeout
│       │   ├── system.py                   # NEW — sw_vers / system_profiler
│       │   ├── apps.py                     # NEW — /Applications + LaunchServices
│       │   ├── screen_time.py              # NEW — knowledgeC.db (best-effort)
│       │   ├── calendar.py                 # NEW — EventKit, last 90 days
│       │   ├── contacts.py                 # NEW — AddressBook SQLite
│       │   ├── mail.py                     # NEW — Mail Envelope Index (sender freq only)
│       │   ├── files.py                    # NEW — mdfind grouped by directory
│       │   ├── git.py                      # NEW — walk ~/code, git log per repo
│       │   ├── browser.py                  # NEW — Safari/Chrome history top domains
│       │   └── shell.py                    # NEW — zsh/bash history command frequency
│       ├── normalizer.py                   # NEW — raw rows → Fact tuples
│       ├── patterns.py                     # NEW — Fact[] → Entity[] (rule-based)
│       ├── notewriter.py                   # NEW — Entity → markdown via Jinja
│       ├── polish.py                       # NEW — opt-in Haiku batch summarizer
│       └── templates/
│           ├── person.md.j2                # NEW
│           ├── project.md.j2               # NEW
│           ├── routine.md.j2               # NEW
│           ├── app.md.j2                   # NEW
│           └── identity.md.j2              # NEW
└── tests/
    └── scan/
        ├── __init__.py
        ├── conftest.py                     # NEW — tmp cache, fake $HOME, fixture vault
        ├── test_facts.py                   # NEW
        ├── test_entities.py                # NEW
        ├── test_collectors_base.py         # NEW — timeout, error swallowing
        ├── test_collector_system.py        # NEW
        ├── test_collector_apps.py          # NEW
        ├── test_collector_calendar.py      # NEW (mocked EventKit)
        ├── test_collector_contacts.py      # NEW (synthetic SQLite)
        ├── test_collector_mail.py          # NEW (synthetic SQLite)
        ├── test_collector_files.py         # NEW (mocked mdfind)
        ├── test_collector_git.py           # NEW (real git in tmp)
        ├── test_collector_browser.py       # NEW (synthetic SQLite)
        ├── test_collector_shell.py         # NEW (tmp histfile)
        ├── test_collector_screen_time.py   # NEW (synthetic SQLite)
        ├── test_normalizer.py              # NEW
        ├── test_patterns.py                # NEW
        ├── test_notewriter.py              # NEW — Jinja → vault
        ├── test_polish.py                  # NEW — anthropic mocked
        └── test_runner.py                  # NEW — full pipeline E2E with fakes
```

---

## Task structure note

This is a wide plan (10 collectors + 4 pipeline stages + runner). I'm splitting it into **18 tasks**. Tasks 1–3 set up the foundation (deps, paths, Fact/Entity). Tasks 4–13 implement collectors one at a time. Tasks 14–17 build pipeline stages. Task 18 wires the runner end-to-end.

Each collector task is identically shaped: write its test, write its module, run the test, commit. The first collector (system) has the most detailed scaffolding; later ones reference its shape.

---

## Task 1 — Add scanner deps and paths

**Files:**
- Modify: `pyproject.toml`
- Create: `yuki/scan/__init__.py`
- Create: `yuki/scan/paths.py`
- Create: `tests/scan/__init__.py`
- Create: `tests/scan/test_paths.py`

- [ ] **Step 1: Add `jinja2` to `pyproject.toml`**

In `[project] dependencies` add `"jinja2>=3.1.4"`. (Anthropic, sqlite3 stdlib, asyncio stdlib already present.)

- [ ] **Step 2: Sync env**

Run: `cd /Users/mafex/code/personal/Yuki && uv sync`
Expected: lockfile updated, no errors.

- [ ] **Step 3: Write the failing test**

Create `tests/scan/__init__.py` (empty) and `tests/scan/test_paths.py`:

```python
from pathlib import Path

from yuki.scan import paths


def test_default_cache_dir(monkeypatch):
    monkeypatch.delenv("YUKI_SCAN_CACHE", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    assert paths.cache_dir() == Path("/tmp/fakehome/Library/Caches/Yuki/scan")


def test_cache_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("YUKI_SCAN_CACHE", str(tmp_path))
    assert paths.cache_dir() == tmp_path


def test_raw_path(monkeypatch, tmp_path):
    monkeypatch.setenv("YUKI_SCAN_CACHE", str(tmp_path))
    assert paths.raw_path("apps") == tmp_path / "raw" / "apps.json"


def test_sentinel_path(monkeypatch):
    monkeypatch.setenv("YUKI_VAULT_DIR", "/tmp/v")
    assert paths.sentinel_path() == Path("/tmp/v/.scan_complete")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_paths.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 5: Implement `yuki/scan/__init__.py`**

```python
"""Onboarding scanner: builds the seed vault on first run."""
```

- [ ] **Step 6: Implement `yuki/scan/paths.py`**

```python
"""Scanner paths — cache dir for raw collector output, sentinel for completion."""
from __future__ import annotations

import os
from pathlib import Path

from yuki.memory import paths as vault_paths


def cache_dir() -> Path:
    override = os.environ.get("YUKI_SCAN_CACHE")
    if override:
        return Path(override)
    return Path(os.environ["HOME"]) / "Library" / "Caches" / "Yuki" / "scan"


def raw_path(collector: str) -> Path:
    return cache_dir() / "raw" / f"{collector}.json"


def sentinel_path() -> Path:
    return vault_paths.vault_dir() / ".scan_complete"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_paths.py -v`
Expected: 4 PASS.

- [ ] **Step 8: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add pyproject.toml uv.lock yuki/scan/__init__.py yuki/scan/paths.py tests/scan/__init__.py tests/scan/test_paths.py
git commit -m "feat(scan): add scanner package skeleton and paths module"
```

---

## Task 2 — Fact dataclass + helpers

**Files:**
- Create: `yuki/scan/facts.py`
- Create: `tests/scan/test_facts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_facts.py`:

```python
from datetime import datetime, timezone

from yuki.scan.facts import Fact, dedupe, merge_evidence


def _f(subject="Sarah Chen", predicate="meets_with_recurring", object_="user",
       confidence=0.8, sources=("calendar",), evidence=None):
    return Fact(
        subject=subject, predicate=predicate, object=object_,
        confidence=confidence, sources=list(sources),
        evidence=list(evidence or [{"event": "1:1"}]),
        first_seen=datetime(2026, 5, 1, tzinfo=timezone.utc),
        last_seen=datetime(2026, 5, 22, tzinfo=timezone.utc),
    )


def test_fact_round_trip_dict():
    f = _f()
    d = f.to_dict()
    f2 = Fact.from_dict(d)
    assert f2 == f


def test_dedupe_merges_same_triple():
    f1 = _f(sources=("calendar",), evidence=[{"a": 1}])
    f2 = _f(sources=("contacts",), evidence=[{"b": 2}])
    out = dedupe([f1, f2])
    assert len(out) == 1
    merged = out[0]
    assert set(merged.sources) == {"calendar", "contacts"}
    assert len(merged.evidence) == 2


def test_dedupe_keeps_distinct_triples():
    f1 = _f(predicate="meets_with_recurring")
    f2 = _f(predicate="emailed_user")
    assert len(dedupe([f1, f2])) == 2


def test_merge_evidence_caps_at_50():
    f1 = _f(evidence=[{"i": i} for i in range(40)])
    f2 = _f(evidence=[{"i": i} for i in range(40, 80)])
    merged = merge_evidence(f1, f2)
    assert len(merged.evidence) <= 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_facts.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/facts.py`**

```python
"""Fact: the unified intermediate representation between collectors and patterns."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

_EVIDENCE_CAP = 50


@dataclass
class Fact:
    subject: str
    predicate: str
    object: str
    confidence: float
    sources: list[str]
    evidence: list[dict[str, Any]]
    first_seen: datetime
    last_seen: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d["first_seen"] = self.first_seen.isoformat()
        d["last_seen"] = self.last_seen.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        return cls(
            subject=d["subject"], predicate=d["predicate"], object=d["object"],
            confidence=d["confidence"], sources=list(d["sources"]),
            evidence=list(d["evidence"]),
            first_seen=datetime.fromisoformat(d["first_seen"]),
            last_seen=datetime.fromisoformat(d["last_seen"]),
        )

    @property
    def triple(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


def merge_evidence(a: Fact, b: Fact) -> Fact:
    sources = sorted(set(a.sources) | set(b.sources))
    evidence = (a.evidence + b.evidence)[:_EVIDENCE_CAP]
    return Fact(
        subject=a.subject, predicate=a.predicate, object=a.object,
        confidence=max(a.confidence, b.confidence),
        sources=sources, evidence=evidence,
        first_seen=min(a.first_seen, b.first_seen),
        last_seen=max(a.last_seen, b.last_seen),
    )


def dedupe(facts: list[Fact]) -> list[Fact]:
    by_triple: dict[tuple[str, str, str], Fact] = {}
    for f in facts:
        if f.triple in by_triple:
            by_triple[f.triple] = merge_evidence(by_triple[f.triple], f)
        else:
            by_triple[f.triple] = f
    return list(by_triple.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_facts.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/facts.py tests/scan/test_facts.py
git commit -m "feat(scan): add Fact dataclass with dedupe + evidence merge"
```

---

## Task 3 — Entity dataclass

`Entity` is what the pattern detector emits. The notewriter consumes it.

**Files:**
- Create: `yuki/scan/entities.py`
- Create: `tests/scan/test_entities.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_entities.py`:

```python
from yuki.scan.entities import Entity


def test_entity_minimal():
    e = Entity(kind="person", id="person-sarah-chen", name="Sarah Chen",
               confidence=0.9, attributes={"role": "manager"}, fact_ids=[])
    assert e.kind == "person"
    assert e.attributes["role"] == "manager"


def test_entity_to_dict_round_trip():
    e = Entity(kind="project", id="project-yuki", name="Yuki",
               confidence=0.85, attributes={"status": "active"}, fact_ids=["t1", "t2"])
    d = e.to_dict()
    assert d["kind"] == "project"
    assert d["fact_ids"] == ["t1", "t2"]
    assert Entity.from_dict(d) == e
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_entities.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/entities.py`**

```python
"""Entity: the typed bundle emitted by the pattern detector."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EntityKind = Literal["person", "project", "routine", "app", "identity"]


@dataclass
class Entity:
    kind: EntityKind
    id: str
    name: str
    confidence: float
    attributes: dict[str, Any]
    fact_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Entity":
        return cls(
            kind=d["kind"], id=d["id"], name=d["name"],
            confidence=d["confidence"], attributes=dict(d["attributes"]),
            fact_ids=list(d.get("fact_ids", [])),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_entities.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/entities.py tests/scan/test_entities.py
git commit -m "feat(scan): add Entity dataclass"
```

---

## Task 4 — Collector base + timeout/error swallowing

The contract every collector implements. `run_collector(coro, timeout=60)` swallows exceptions and timeouts into an empty list — this is intentional silent degradation per the Architecture note.

**Files:**
- Create: `yuki/scan/collectors/__init__.py`
- Create: `yuki/scan/collectors/base.py`
- Create: `tests/scan/conftest.py`
- Create: `tests/scan/test_collectors_base.py`

- [ ] **Step 1: Add shared fixtures**

Create `tests/scan/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def tmp_scan_cache(tmp_path: Path, monkeypatch) -> Path:
    cache = tmp_path / "scan-cache"
    monkeypatch.setenv("YUKI_SCAN_CACHE", str(cache))
    return cache


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home
```

- [ ] **Step 2: Write the failing test**

Create `tests/scan/test_collectors_base.py`:

```python
import asyncio
import json
from pathlib import Path

import pytest

from yuki.scan.collectors.base import Collector, run_collector


class _OkCollector(Collector):
    name = "ok"
    async def collect(self):
        return [{"x": 1}, {"x": 2}]


class _BoomCollector(Collector):
    name = "boom"
    async def collect(self):
        raise RuntimeError("kaboom")


class _SlowCollector(Collector):
    name = "slow"
    async def collect(self):
        await asyncio.sleep(2.0)
        return [{"never": True}]


@pytest.mark.asyncio
async def test_run_collector_writes_json(tmp_scan_cache: Path):
    rows = await run_collector(_OkCollector(), timeout=5.0)
    assert rows == [{"x": 1}, {"x": 2}]
    out = tmp_scan_cache / "raw" / "ok.json"
    assert json.loads(out.read_text()) == [{"x": 1}, {"x": 2}]


@pytest.mark.asyncio
async def test_run_collector_swallows_errors(tmp_scan_cache: Path):
    rows = await run_collector(_BoomCollector(), timeout=5.0)
    assert rows == []
    out = tmp_scan_cache / "raw" / "boom.json"
    assert json.loads(out.read_text()) == []


@pytest.mark.asyncio
async def test_run_collector_timeout(tmp_scan_cache: Path):
    rows = await run_collector(_SlowCollector(), timeout=0.05)
    assert rows == []
```

- [ ] **Step 3: Add `pytest-asyncio` to dev deps**

In `pyproject.toml` `[dependency-groups] dev`, add `"pytest-asyncio>=0.24.0"`. Add to `[tool.pytest.ini_options]`:

```toml
asyncio_mode = "auto"
```

Run: `cd /Users/mafex/code/personal/Yuki && uv sync`

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collectors_base.py -v`
Expected: ModuleNotFoundError on `yuki.scan.collectors.base`.

- [ ] **Step 5: Implement collector base**

Create `yuki/scan/collectors/__init__.py`:

```python
"""Collectors: each maps one macOS data source to raw JSON rows."""
```

Create `yuki/scan/collectors/base.py`:

```python
"""Collector protocol + run wrapper that swallows errors and writes JSON cache."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

from yuki.scan import paths

log = logging.getLogger(__name__)


class Collector(Protocol):
    name: str
    async def collect(self) -> list[dict[str, Any]]: ...


async def run_collector(collector: Collector, timeout: float = 60.0) -> list[dict]:
    """Run a collector with timeout + error swallowing. Always writes raw cache."""
    rows: list[dict] = []
    try:
        rows = await asyncio.wait_for(collector.collect(), timeout=timeout)
    except asyncio.TimeoutError:
        log.warning("collector %s timed out after %.1fs", collector.name, timeout)
    except Exception as e:
        log.warning("collector %s failed: %s", collector.name, e)

    out = paths.raw_path(collector.name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, default=str), encoding="utf-8")
    return rows
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collectors_base.py -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add pyproject.toml uv.lock yuki/scan/collectors/__init__.py yuki/scan/collectors/base.py tests/scan/conftest.py tests/scan/test_collectors_base.py
git commit -m "feat(scan): add Collector protocol with timeout + error swallowing"
```

---

## Task 5 — `system` collector

Reads `sw_vers` and `defaults read NSGlobalDomain AppleLocale`. One row out: `{macos_version, build, locale, hostname}`.

**Files:**
- Create: `yuki/scan/collectors/system.py`
- Create: `tests/scan/test_collector_system.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_system.py`:

```python
import pytest
from unittest.mock import patch

from yuki.scan.collectors.system import SystemCollector


@pytest.mark.asyncio
async def test_collects_system_facts():
    fake_outputs = {
        ("sw_vers", "-productVersion"): "14.4.1\n",
        ("sw_vers", "-buildVersion"): "23E224\n",
        ("hostname",): "my-mac.local\n",
        ("defaults", "read", "-g", "AppleLocale"): "en_US\n",
    }

    async def fake_run(*args):
        return fake_outputs.get(args, "")

    with patch("yuki.scan.collectors.system._run", side_effect=fake_run):
        rows = await SystemCollector().collect()

    assert len(rows) == 1
    assert rows[0]["macos_version"] == "14.4.1"
    assert rows[0]["locale"] == "en_US"
    assert rows[0]["hostname"] == "my-mac.local"


@pytest.mark.asyncio
async def test_handles_missing_outputs():
    async def fake_run(*args):
        return ""
    with patch("yuki.scan.collectors.system._run", side_effect=fake_run):
        rows = await SystemCollector().collect()
    assert len(rows) == 1
    assert rows[0]["macos_version"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_system.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/system.py`**

Use `asyncio.create_subprocess_exec` with an argument list (NOT shell=True; no string interpolation). All inputs are static command names — no user input touches the subprocess.

```python
"""System collector — macOS version, build, locale, hostname."""
from __future__ import annotations

import asyncio


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace").strip()


class SystemCollector:
    name = "system"

    async def collect(self) -> list[dict]:
        version = await _run("sw_vers", "-productVersion")
        build = await _run("sw_vers", "-buildVersion")
        host = await _run("hostname")
        locale = await _run("defaults", "read", "-g", "AppleLocale")
        return [{
            "macos_version": version,
            "build": build,
            "hostname": host,
            "locale": locale,
        }]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_system.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/system.py tests/scan/test_collector_system.py
git commit -m "feat(scan): add system collector"
```

---

## Task 6 — `apps` collector

Walks `/Applications` and `~/Applications`, reads `Info.plist` per app for bundle id + display name. Best-effort; malformed plists skipped.

**Files:**
- Create: `yuki/scan/collectors/apps.py`
- Create: `tests/scan/test_collector_apps.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_apps.py`:

```python
from pathlib import Path

import pytest

from yuki.scan.collectors.apps import AppsCollector


def _make_app(root: Path, name: str, bundle_id: str) -> None:
    contents = root / f"{name}.app" / "Contents"
    contents.mkdir(parents=True)
    plist = contents / "Info.plist"
    plist.write_text(
        f"""<?xml version="1.0"?>
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>{bundle_id}</string>
  <key>CFBundleName</key><string>{name}</string>
</dict>
</plist>
"""
    )


@pytest.mark.asyncio
async def test_apps_collector_walks_dirs(tmp_path):
    sys_apps = tmp_path / "sys"
    user_apps = tmp_path / "user"
    sys_apps.mkdir(); user_apps.mkdir()
    _make_app(sys_apps, "Slack", "com.tinyspeck.slackmacgap")
    _make_app(user_apps, "Vim", "org.vim.MacVim")

    rows = await AppsCollector(roots=[sys_apps, user_apps]).collect()
    names = {r["name"] for r in rows}
    assert names == {"Slack", "Vim"}
    assert any(r["bundle_id"] == "com.tinyspeck.slackmacgap" for r in rows)


@pytest.mark.asyncio
async def test_apps_collector_skips_malformed(tmp_path):
    sys_apps = tmp_path / "sys"
    sys_apps.mkdir()
    bad = sys_apps / "Broken.app" / "Contents"
    bad.mkdir(parents=True)
    (bad / "Info.plist").write_text("not xml")
    _make_app(sys_apps, "Good", "com.example.good")

    rows = await AppsCollector(roots=[sys_apps]).collect()
    assert {r["name"] for r in rows} == {"Good"}


@pytest.mark.asyncio
async def test_apps_collector_missing_root(tmp_path):
    rows = await AppsCollector(roots=[tmp_path / "nope"]).collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_apps.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/apps.py`**

```python
"""Apps collector — discovers .app bundles and reads Info.plist."""
from __future__ import annotations

import plistlib
from pathlib import Path


class AppsCollector:
    name = "apps"

    def __init__(self, roots: list[Path] | None = None) -> None:
        if roots is None:
            roots = [Path("/Applications"), Path.home() / "Applications"]
        self._roots = roots

    async def collect(self) -> list[dict]:
        rows: list[dict] = []
        for root in self._roots:
            if not root.exists():
                continue
            for app in root.glob("*.app"):
                plist = app / "Contents" / "Info.plist"
                if not plist.exists():
                    continue
                try:
                    data = plistlib.loads(plist.read_bytes())
                except Exception:
                    continue
                rows.append({
                    "name": data.get("CFBundleName") or app.stem,
                    "bundle_id": data.get("CFBundleIdentifier", ""),
                    "path": str(app),
                })
        return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_apps.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/apps.py tests/scan/test_collector_apps.py
git commit -m "feat(scan): add apps collector"
```

---

## Task 7 — `shell` collector

Reads `~/.zsh_history` (or `.bash_history`), counts command frequency. Strips zsh extended-history prefix (`: 1234567:0;`).

**Files:**
- Create: `yuki/scan/collectors/shell.py`
- Create: `tests/scan/test_collector_shell.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_shell.py`:

```python
from pathlib import Path

import pytest

from yuki.scan.collectors.shell import ShellCollector


@pytest.mark.asyncio
async def test_zsh_extended_history(tmp_home: Path):
    hist = tmp_home / ".zsh_history"
    hist.write_text(
        ": 1700000000:0;git status\n"
        ": 1700000001:0;git status\n"
        ": 1700000002:0;npm test\n"
        ": 1700000003:0;cd ~/code\n",
        encoding="utf-8",
    )
    rows = await ShellCollector().collect()
    by_cmd = {r["command"]: r for r in rows}
    assert by_cmd["git"]["count"] == 2
    assert by_cmd["npm"]["count"] == 1


@pytest.mark.asyncio
async def test_bash_history_fallback(tmp_home: Path):
    hist = tmp_home / ".bash_history"
    hist.write_text("ls\nls\npwd\n", encoding="utf-8")
    rows = await ShellCollector().collect()
    cmds = {r["command"]: r["count"] for r in rows}
    assert cmds == {"ls": 2, "pwd": 1}


@pytest.mark.asyncio
async def test_no_history_returns_empty(tmp_home: Path):
    rows = await ShellCollector().collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_shell.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/shell.py`**

```python
"""Shell history collector — command frequency from zsh/bash history."""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

_ZSH_PREFIX = re.compile(r"^:\s*\d+:\d+;")


class ShellCollector:
    name = "shell"

    async def collect(self) -> list[dict]:
        home = Path(os.environ["HOME"])
        for candidate in (".zsh_history", ".bash_history"):
            path = home / candidate
            if path.exists():
                return self._parse(path)
        return []

    def _parse(self, path: Path) -> list[dict]:
        counts: Counter[str] = Counter()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        for line in text.splitlines():
            line = _ZSH_PREFIX.sub("", line).strip()
            if not line:
                continue
            cmd = line.split(maxsplit=1)[0]
            counts[cmd] += 1
        return [{"command": c, "count": n} for c, n in counts.most_common()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_shell.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/shell.py tests/scan/test_collector_shell.py
git commit -m "feat(scan): add shell history collector"
```

---

## Task 8 — `contacts` collector

Reads AddressBook SQLite. Returns rows of `{first_name, last_name, emails, phones}`. Tested against a synthetic SQLite that mimics the AddressBook schema.

**Files:**
- Create: `yuki/scan/collectors/contacts.py`
- Create: `tests/scan/test_collector_contacts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_contacts.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.contacts import ContactsCollector


def _seed_addressbook(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE ZABCDRECORD (
            Z_PK INTEGER PRIMARY KEY,
            ZFIRSTNAME TEXT, ZLASTNAME TEXT
        );
        CREATE TABLE ZABCDEMAILADDRESS (
            Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZADDRESS TEXT
        );
        CREATE TABLE ZABCDPHONENUMBER (
            Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZFULLNUMBER TEXT
        );
        INSERT INTO ZABCDRECORD VALUES (1, 'Sarah', 'Chen');
        INSERT INTO ZABCDRECORD VALUES (2, 'Bob', 'Liu');
        INSERT INTO ZABCDEMAILADDRESS VALUES (10, 1, 'sarah@example.com');
        INSERT INTO ZABCDPHONENUMBER VALUES (20, 2, '555-1212');
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_contacts_collector_reads_db(tmp_path):
    db = tmp_path / "AddressBook-v22.abcddb"
    _seed_addressbook(db)
    rows = await ContactsCollector(db_path=db).collect()
    by_name = {(r["first_name"], r["last_name"]): r for r in rows}
    assert by_name[("Sarah", "Chen")]["emails"] == ["sarah@example.com"]
    assert by_name[("Bob", "Liu")]["phones"] == ["555-1212"]


@pytest.mark.asyncio
async def test_contacts_missing_db_returns_empty(tmp_path):
    rows = await ContactsCollector(db_path=tmp_path / "nope.db").collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_contacts.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/contacts.py`**

The real AddressBook lives under `~/Library/Application Support/AddressBook/Sources/<uuid>/AddressBook-v22.abcddb`. We default to scanning that pattern and pick the first hit.

```python
"""Contacts collector — reads the macOS AddressBook SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _default_db() -> Path | None:
    base = Path.home() / "Library" / "Application Support" / "AddressBook" / "Sources"
    if not base.exists():
        return None
    for src in base.iterdir():
        candidate = src / "AddressBook-v22.abcddb"
        if candidate.exists():
            return candidate
    return None


class ContactsCollector:
    name = "contacts"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path if db_path is not None else _default_db()

    async def collect(self) -> list[dict]:
        if self._db_path is None or not self._db_path.exists():
            return []
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            people = conn.execute(
                "SELECT Z_PK, ZFIRSTNAME, ZLASTNAME FROM ZABCDRECORD"
            ).fetchall()
            emails = conn.execute(
                "SELECT ZOWNER, ZADDRESS FROM ZABCDEMAILADDRESS"
            ).fetchall()
            phones = conn.execute(
                "SELECT ZOWNER, ZFULLNUMBER FROM ZABCDPHONENUMBER"
            ).fetchall()
        finally:
            conn.close()

        emails_by_owner: dict[int, list[str]] = {}
        for owner, addr in emails:
            if addr:
                emails_by_owner.setdefault(owner, []).append(addr)
        phones_by_owner: dict[int, list[str]] = {}
        for owner, num in phones:
            if num:
                phones_by_owner.setdefault(owner, []).append(num)

        rows: list[dict] = []
        for pk, first, last in people:
            rows.append({
                "first_name": first or "",
                "last_name": last or "",
                "emails": emails_by_owner.get(pk, []),
                "phones": phones_by_owner.get(pk, []),
            })
        return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_contacts.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/contacts.py tests/scan/test_collector_contacts.py
git commit -m "feat(scan): add contacts collector"
```

---

## Task 9 — `mail` collector

Reads Mail's `Envelope Index` SQLite. Returns sender frequency only (no body, no subjects). Per spec §5.2: "sender frequency only, no body content".

**Files:**
- Create: `yuki/scan/collectors/mail.py`
- Create: `tests/scan/test_collector_mail.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_mail.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.mail import MailCollector


def _seed_envelope(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE addresses (ROWID INTEGER PRIMARY KEY, address TEXT);
        CREATE TABLE messages (
            ROWID INTEGER PRIMARY KEY,
            sender INTEGER,
            date_received INTEGER
        );
        INSERT INTO addresses VALUES (1, 'sarah@example.com');
        INSERT INTO addresses VALUES (2, 'newsletter@spam.example');
        INSERT INTO messages VALUES (10, 1, 1700000000);
        INSERT INTO messages VALUES (11, 1, 1700100000);
        INSERT INTO messages VALUES (12, 1, 1700200000);
        INSERT INTO messages VALUES (13, 2, 1700300000);
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_mail_collector_counts_senders(tmp_path):
    db = tmp_path / "Envelope Index"
    _seed_envelope(db)
    rows = await MailCollector(db_path=db).collect()
    by_addr = {r["address"]: r for r in rows}
    assert by_addr["sarah@example.com"]["count"] == 3
    assert by_addr["newsletter@spam.example"]["count"] == 1


@pytest.mark.asyncio
async def test_mail_missing_db_returns_empty(tmp_path):
    rows = await MailCollector(db_path=tmp_path / "nope").collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_mail.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/mail.py`**

```python
"""Mail collector — reads sender frequency from Mail's Envelope Index SQLite.

Body content is never read. Per spec §5.2 + §11.2.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def _default_db() -> Path:
    return Path.home() / "Library" / "Mail" / "V10" / "MailData" / "Envelope Index"


class MailCollector:
    name = "mail"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _default_db()

    async def collect(self) -> list[dict]:
        if not self._db_path.exists():
            return []
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT a.address, COUNT(m.ROWID), MAX(m.date_received) "
                "FROM messages m JOIN addresses a ON m.sender = a.ROWID "
                "GROUP BY a.address ORDER BY COUNT(m.ROWID) DESC"
            ).fetchall()
        finally:
            conn.close()
        return [
            {"address": addr, "count": cnt, "last_seen_unix": last}
            for addr, cnt, last in rows
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_mail.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/mail.py tests/scan/test_collector_mail.py
git commit -m "feat(scan): add mail collector (sender frequency only, no body)"
```

---

## Task 10 — `browser` collector

Reads Safari + Chrome history SQLite, returns top domains by visit count. Tested against synthetic DBs that mimic the schemas.

**Files:**
- Create: `yuki/scan/collectors/browser.py`
- Create: `tests/scan/test_collector_browser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_browser.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.browser import BrowserCollector


def _seed_safari(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE history_items (id INTEGER PRIMARY KEY, url TEXT, visit_count INTEGER);
        INSERT INTO history_items VALUES (1, 'https://github.com/x', 30);
        INSERT INTO history_items VALUES (2, 'https://github.com/y', 12);
        INSERT INTO history_items VALUES (3, 'https://news.ycombinator.com/', 8);
        """
    )
    conn.commit(); conn.close()


def _seed_chrome(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, visit_count INTEGER);
        INSERT INTO urls VALUES (1, 'https://docs.python.org/x', 50);
        INSERT INTO urls VALUES (2, 'https://github.com/z', 5);
        """
    )
    conn.commit(); conn.close()


@pytest.mark.asyncio
async def test_browser_collector_aggregates(tmp_path):
    safari = tmp_path / "History.db"
    chrome = tmp_path / "History"
    _seed_safari(safari)
    _seed_chrome(chrome)
    rows = await BrowserCollector(safari_db=safari, chrome_db=chrome).collect()
    by_domain = {r["domain"]: r["visits"] for r in rows}
    assert by_domain["github.com"] == 30 + 12 + 5
    assert by_domain["docs.python.org"] == 50


@pytest.mark.asyncio
async def test_browser_collector_missing_dbs(tmp_path):
    rows = await BrowserCollector(
        safari_db=tmp_path / "x", chrome_db=tmp_path / "y"
    ).collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_browser.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/browser.py`**

```python
"""Browser history collector — top domains by visit count."""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


def _safari_default() -> Path:
    return Path.home() / "Library" / "Safari" / "History.db"


def _chrome_default() -> Path:
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "History"


def _read_safari(db: Path) -> list[tuple[str, int]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT url, visit_count FROM history_items").fetchall()
    finally:
        conn.close()


def _read_chrome(db: Path) -> list[tuple[str, int]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT url, visit_count FROM urls").fetchall()
    finally:
        conn.close()


class BrowserCollector:
    name = "browser"

    def __init__(self, safari_db: Path | None = None, chrome_db: Path | None = None) -> None:
        self._safari = safari_db or _safari_default()
        self._chrome = chrome_db or _chrome_default()

    async def collect(self) -> list[dict]:
        counts: Counter[str] = Counter()
        for db, reader in ((self._safari, _read_safari), (self._chrome, _read_chrome)):
            if not db.exists():
                continue
            try:
                for url, visits in reader(db):
                    if not url:
                        continue
                    domain = urlparse(url).netloc
                    if domain:
                        counts[domain] += int(visits or 0)
            except sqlite3.Error:
                continue
        return [{"domain": d, "visits": n} for d, n in counts.most_common()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_browser.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/browser.py tests/scan/test_collector_browser.py
git commit -m "feat(scan): add browser history collector"
```

---

## Task 11 — `screen_time` collector

Best-effort reader for `~/Library/Application Support/Knowledge/knowledgeC.db`. The schema is undocumented; we read the well-known `ZOBJECT` table for `/app/usage` rows. Returns app bundle ids with total focus seconds. If the DB is absent (Full Disk Access not granted), returns empty.

**Files:**
- Create: `yuki/scan/collectors/screen_time.py`
- Create: `tests/scan/test_collector_screen_time.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_screen_time.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.screen_time import ScreenTimeCollector


def _seed(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE ZOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            ZSTREAMNAME TEXT,
            ZVALUESTRING TEXT,
            ZSTARTDATE REAL,
            ZENDDATE REAL
        );
        INSERT INTO ZOBJECT VALUES (1, '/app/usage', 'com.apple.Safari', 100.0, 460.0);
        INSERT INTO ZOBJECT VALUES (2, '/app/usage', 'com.apple.Safari', 500.0, 800.0);
        INSERT INTO ZOBJECT VALUES (3, '/app/usage', 'com.tinyspeck.slackmacgap', 0.0, 60.0);
        INSERT INTO ZOBJECT VALUES (4, '/notification', 'irrelevant', 0.0, 1.0);
        """
    )
    conn.commit(); conn.close()


@pytest.mark.asyncio
async def test_screen_time_aggregates(tmp_path):
    db = tmp_path / "knowledgeC.db"
    _seed(db)
    rows = await ScreenTimeCollector(db_path=db).collect()
    by_id = {r["bundle_id"]: r["seconds"] for r in rows}
    assert by_id["com.apple.Safari"] == 360 + 300
    assert by_id["com.tinyspeck.slackmacgap"] == 60
    assert "irrelevant" not in by_id


@pytest.mark.asyncio
async def test_screen_time_missing_db(tmp_path):
    rows = await ScreenTimeCollector(db_path=tmp_path / "no.db").collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_screen_time.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/screen_time.py`**

```python
"""Screen Time collector — reads knowledgeC.db (best-effort, often locked)."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path


def _default_db() -> Path:
    return Path.home() / "Library" / "Application Support" / "Knowledge" / "knowledgeC.db"


class ScreenTimeCollector:
    name = "screen_time"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _default_db()

    async def collect(self) -> list[dict]:
        if not self._db_path.exists():
            return []
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return []
        try:
            rows = conn.execute(
                "SELECT ZVALUESTRING, ZSTARTDATE, ZENDDATE FROM ZOBJECT "
                "WHERE ZSTREAMNAME = '/app/usage'"
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()
        totals: dict[str, float] = defaultdict(float)
        for bundle_id, start, end in rows:
            if not bundle_id or start is None or end is None:
                continue
            totals[bundle_id] += float(end) - float(start)
        return [
            {"bundle_id": b, "seconds": int(s)}
            for b, s in sorted(totals.items(), key=lambda kv: -kv[1])
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_screen_time.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/screen_time.py tests/scan/test_collector_screen_time.py
git commit -m "feat(scan): add screen time collector (knowledgeC.db, best-effort)"
```

---

## Task 12 — `files` collector

Runs `mdfind` for files modified in the last 90 days, groups by parent directory, returns top directories by file count. Uses subprocess with arg list (no shell).

**Files:**
- Create: `yuki/scan/collectors/files.py`
- Create: `tests/scan/test_collector_files.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_files.py`:

```python
import pytest
from unittest.mock import patch

from yuki.scan.collectors.files import FilesCollector


@pytest.mark.asyncio
async def test_files_collector_groups_by_dir():
    fake_stdout = (
        "/Users/me/code/yuki/main.py\n"
        "/Users/me/code/yuki/test.py\n"
        "/Users/me/code/yuki/README.md\n"
        "/Users/me/Documents/notes.txt\n"
    )

    async def fake_run(*args):
        return fake_stdout

    with patch("yuki.scan.collectors.files._run", side_effect=fake_run):
        rows = await FilesCollector().collect()

    by_dir = {r["directory"]: r["count"] for r in rows}
    assert by_dir["/Users/me/code/yuki"] == 3
    assert by_dir["/Users/me/Documents"] == 1


@pytest.mark.asyncio
async def test_files_collector_empty_output():
    async def fake_run(*args):
        return ""
    with patch("yuki.scan.collectors.files._run", side_effect=fake_run):
        rows = await FilesCollector().collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_files.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/files.py`**

```python
"""Files collector — mdfind for recently-touched files, grouped by directory."""
from __future__ import annotations

import asyncio
import os
from collections import Counter


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace")


class FilesCollector:
    name = "files"

    def __init__(self, days: int = 90) -> None:
        self._days = days

    async def collect(self) -> list[dict]:
        query = f"kMDItemLastUsedDate >= $time.now(-{self._days * 86400})"
        text = await _run("mdfind", query)
        counts: Counter[str] = Counter()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            counts[os.path.dirname(line)] += 1
        return [
            {"directory": d, "count": n}
            for d, n in counts.most_common(200)
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_files.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/files.py tests/scan/test_collector_files.py
git commit -m "feat(scan): add files collector via mdfind"
```

---

## Task 13 — `git` collector

Walks `~/code` (and other configured roots), finds git repos, runs `git log --pretty=format:%aI%x09%s -n 50` per repo. Returns one row per repo with name, path, last commit time, recent commit subjects.

**Files:**
- Create: `yuki/scan/collectors/git.py`
- Create: `tests/scan/test_collector_git.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_git.py`:

```python
import shutil
import subprocess
from pathlib import Path

import pytest

from yuki.scan.collectors.git import GitCollector


def _make_repo(root: Path, name: str, commits: int) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    for i in range(commits):
        (repo / f"f{i}").write_text(str(i))
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"commit {i}"], cwd=repo, check=True)
    return repo


@pytest.mark.asyncio
async def test_git_collector_walks_repos(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not available")
    _make_repo(tmp_path, "alpha", 3)
    _make_repo(tmp_path, "nested/beta", 1)
    rows = await GitCollector(roots=[tmp_path]).collect()
    names = {r["name"] for r in rows}
    assert names == {"alpha", "beta"}
    alpha = next(r for r in rows if r["name"] == "alpha")
    assert alpha["commit_count"] >= 3
    assert any("commit 0" in s for s in alpha["recent_subjects"])


@pytest.mark.asyncio
async def test_git_collector_skips_non_repo(tmp_path):
    (tmp_path / "not_a_repo").mkdir()
    rows = await GitCollector(roots=[tmp_path]).collect()
    assert rows == []


@pytest.mark.asyncio
async def test_git_collector_missing_root(tmp_path):
    rows = await GitCollector(roots=[tmp_path / "nope"]).collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_git.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/git.py`**

```python
"""Git collector — walks configured roots for repos, summarizes recent commits."""
from __future__ import annotations

import asyncio
from pathlib import Path


async def _run_in(cwd: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace")


class GitCollector:
    name = "git"

    def __init__(self, roots: list[Path] | None = None) -> None:
        if roots is None:
            roots = [Path.home() / "code"]
        self._roots = roots

    async def collect(self) -> list[dict]:
        rows: list[dict] = []
        for root in self._roots:
            if not root.exists():
                continue
            for path in self._find_repos(root):
                row = await self._summarize(path)
                if row is not None:
                    rows.append(row)
        return rows

    def _find_repos(self, root: Path) -> list[Path]:
        repos: list[Path] = []
        for path in root.rglob(".git"):
            if path.is_dir():
                repos.append(path.parent)
        return repos

    async def _summarize(self, repo: Path) -> dict | None:
        log = await _run_in(repo, "git", "log", "--pretty=format:%aI%x09%s", "-n", "50")
        if not log.strip():
            return None
        lines = [line.split("\t", 1) for line in log.splitlines() if "\t" in line]
        if not lines:
            return None
        last_iso = lines[0][0]
        subjects = [s for _, s in lines[:20]]
        return {
            "name": repo.name,
            "path": str(repo),
            "last_commit": last_iso,
            "commit_count": len(lines),
            "recent_subjects": subjects,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_git.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/git.py tests/scan/test_collector_git.py
git commit -m "feat(scan): add git collector"
```

---

## Task 14 — `calendar` collector (EventKit)

Uses pyobjc EventKit to read events from the last 90 days. Tested by mocking the EventKit module (real EventKit requires the user to grant Calendar permission — out of test reach).

**Files:**
- Create: `yuki/scan/collectors/calendar.py`
- Create: `tests/scan/test_collector_calendar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_collector_calendar.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import MagicMock, patch

from yuki.scan.collectors.calendar import CalendarCollector


def _fake_event(title, organizer, attendees, start, recurring=False):
    e = MagicMock()
    e.title.return_value = title
    org = MagicMock()
    org.name.return_value = organizer
    e.organizer.return_value = org
    atts = []
    for n in attendees:
        a = MagicMock()
        a.name.return_value = n
        atts.append(a)
    e.attendees.return_value = atts
    e.startDate.return_value = start
    e.hasRecurrenceRules.return_value = recurring
    return e


@pytest.mark.asyncio
async def test_calendar_emits_events_with_attendees():
    start = datetime(2026, 5, 1, 10, tzinfo=timezone.utc)
    e = _fake_event("1:1 with Sarah", "Sarah Chen", ["user", "Sarah Chen"], start, True)
    fake_store = MagicMock()
    fake_store.eventsMatchingPredicate_.return_value = [e]
    fake_store.predicateForEventsWithStartDate_endDate_calendars_.return_value = object()
    fake_store.requestAccessToEntityType_completion_.return_value = None

    with patch("yuki.scan.collectors.calendar._make_store", return_value=fake_store):
        rows = await CalendarCollector(days=30).collect()

    assert len(rows) == 1
    assert rows[0]["title"] == "1:1 with Sarah"
    assert "Sarah Chen" in rows[0]["attendees"]
    assert rows[0]["recurring"] is True


@pytest.mark.asyncio
async def test_calendar_missing_eventkit_returns_empty():
    with patch("yuki.scan.collectors.calendar._make_store", return_value=None):
        rows = await CalendarCollector().collect()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_calendar.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/collectors/calendar.py`**

```python
"""Calendar collector — reads recent events via EventKit (pyobjc)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


def _make_store():  # pragma: no cover — real macOS only
    try:
        from EventKit import EKEventStore, EKEntityTypeEvent
    except Exception:
        return None
    store = EKEventStore.alloc().init()
    granted = {"v": False}
    def cb(ok, err):
        granted["v"] = bool(ok)
    store.requestAccessToEntityType_completion_(EKEntityTypeEvent, cb)
    return store if granted["v"] else store  # access check is async; we still try


class CalendarCollector:
    name = "calendar"

    def __init__(self, days: int = 90) -> None:
        self._days = days

    async def collect(self) -> list[dict]:
        store = _make_store()
        if store is None:
            return []
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self._days)
        try:
            pred = store.predicateForEventsWithStartDate_endDate_calendars_(
                start, end, None,
            )
            events = store.eventsMatchingPredicate_(pred)
        except Exception as e:
            log.warning("EventKit query failed: %s", e)
            return []
        rows: list[dict] = []
        for e in events or []:
            try:
                organizer = e.organizer()
                organizer_name = organizer.name() if organizer else ""
                attendees = [a.name() for a in (e.attendees() or [])]
                rows.append({
                    "title": e.title() or "",
                    "organizer": organizer_name,
                    "attendees": attendees,
                    "start": str(e.startDate()),
                    "recurring": bool(e.hasRecurrenceRules()),
                })
            except Exception:
                continue
        return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_collector_calendar.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/collectors/calendar.py tests/scan/test_collector_calendar.py
git commit -m "feat(scan): add calendar collector via EventKit"
```

---

## Task 15 — Normalizer

Reads each collector's raw JSON, emits typed `Fact` tuples. Pure function over the cache files. Aliases (email → contact name) are resolved here.

**Files:**
- Create: `yuki/scan/normalizer.py`
- Create: `tests/scan/test_normalizer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_normalizer.py`:

```python
import json
from pathlib import Path

import pytest

from yuki.scan.normalizer import normalize


def _write(cache: Path, name: str, data: list) -> None:
    raw = cache / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{name}.json").write_text(json.dumps(data))


def test_apps_become_uses_app_facts(tmp_scan_cache: Path):
    _write(tmp_scan_cache, "apps", [
        {"name": "Slack", "bundle_id": "com.tinyspeck.slackmacgap", "path": "/x"},
        {"name": "Vim", "bundle_id": "org.vim.MacVim", "path": "/y"},
    ])
    facts = normalize()
    triples = {(f.subject, f.predicate, f.object) for f in facts}
    assert ("user", "uses_app", "Slack") in triples
    assert ("user", "uses_app", "Vim") in triples


def test_calendar_recurring_with_attendees_yields_meets_with(tmp_scan_cache: Path):
    _write(tmp_scan_cache, "calendar", [
        {
            "title": "1:1",
            "organizer": "Sarah Chen",
            "attendees": ["user", "Sarah Chen"],
            "start": "2026-05-01T10:00:00+00:00",
            "recurring": True,
        }
    ])
    facts = normalize()
    triples = {(f.subject, f.predicate, f.object) for f in facts}
    assert ("Sarah Chen", "meets_with_recurring", "user") in triples


def test_mail_top_senders(tmp_scan_cache: Path):
    _write(tmp_scan_cache, "mail", [
        {"address": "sarah@example.com", "count": 30, "last_seen_unix": 1700000000},
        {"address": "sarah@example.com", "count": 30, "last_seen_unix": 1700000000},
    ])
    facts = normalize()
    triples = {(f.subject, f.predicate, f.object) for f in facts}
    assert ("user", "emails_with", "sarah@example.com") in triples


def test_git_emits_works_on_project(tmp_scan_cache: Path):
    _write(tmp_scan_cache, "git", [
        {
            "name": "yuki", "path": "/Users/me/code/yuki",
            "last_commit": "2026-05-22T08:00:00+00:00",
            "commit_count": 50, "recent_subjects": ["init"],
        }
    ])
    facts = normalize()
    assert any(f.predicate == "works_on_project" and f.object == "yuki" for f in facts)


def test_missing_cache_returns_empty(tmp_scan_cache: Path):
    assert normalize() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_normalizer.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/normalizer.py`**

```python
"""Normalizer — raw collector JSON → unified Fact tuples."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from yuki.scan import paths
from yuki.scan.facts import Fact, dedupe

_NOW = lambda: datetime.now(timezone.utc)


def _load(name: str) -> list[dict]:
    p = paths.raw_path(name)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _from_apps(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    return [
        Fact(
            subject="user", predicate="uses_app", object=r["name"],
            confidence=0.6, sources=["apps"], evidence=[r],
            first_seen=now, last_seen=now,
        )
        for r in rows if r.get("name")
    ]


def _from_calendar(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    out: list[Fact] = []
    for r in rows:
        attendees = [a for a in (r.get("attendees") or []) if a and a != "user"]
        if not attendees:
            continue
        predicate = "meets_with_recurring" if r.get("recurring") else "meets_with"
        for person in attendees:
            out.append(Fact(
                subject=person, predicate=predicate, object="user",
                confidence=0.85 if r.get("recurring") else 0.55,
                sources=["calendar"], evidence=[r],
                first_seen=now, last_seen=now,
            ))
    return out


def _from_contacts(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    out: list[Fact] = []
    for r in rows:
        full = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
        if not full:
            continue
        for email in r.get("emails", []):
            out.append(Fact(
                subject=email, predicate="aliases_for", object=full,
                confidence=0.95, sources=["contacts"], evidence=[r],
                first_seen=now, last_seen=now,
            ))
    return out


def _from_mail(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    return [
        Fact(
            subject="user", predicate="emails_with", object=r["address"],
            confidence=min(0.95, 0.4 + r.get("count", 0) / 100),
            sources=["mail"], evidence=[r],
            first_seen=now, last_seen=now,
        )
        for r in rows if r.get("address")
    ]


def _from_git(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    return [
        Fact(
            subject="user", predicate="works_on_project", object=r["name"],
            confidence=min(0.95, 0.5 + r.get("commit_count", 0) / 100),
            sources=["git"], evidence=[r],
            first_seen=now, last_seen=now,
        )
        for r in rows if r.get("name")
    ]


def _from_browser(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    return [
        Fact(
            subject="user", predicate="visits_domain", object=r["domain"],
            confidence=min(0.95, 0.4 + r.get("visits", 0) / 200),
            sources=["browser"], evidence=[r],
            first_seen=now, last_seen=now,
        )
        for r in rows if r.get("domain")
    ]


def _from_screen_time(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    return [
        Fact(
            subject="user", predicate="focuses_on_app",
            object=r["bundle_id"],
            confidence=0.8, sources=["screen_time"], evidence=[r],
            first_seen=now, last_seen=now,
        )
        for r in rows if r.get("bundle_id")
    ]


def _from_shell(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    return [
        Fact(
            subject="user", predicate="runs_command", object=r["command"],
            confidence=min(0.95, 0.3 + r.get("count", 0) / 50),
            sources=["shell"], evidence=[r],
            first_seen=now, last_seen=now,
        )
        for r in rows if r.get("command")
    ]


def _from_files(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    return [
        Fact(
            subject="user", predicate="active_in_directory", object=r["directory"],
            confidence=min(0.95, 0.3 + r.get("count", 0) / 30),
            sources=["files"], evidence=[r],
            first_seen=now, last_seen=now,
        )
        for r in rows if r.get("directory")
    ]


def _from_system(rows: list[dict]) -> list[Fact]:
    now = _NOW()
    out: list[Fact] = []
    for r in rows:
        if r.get("hostname"):
            out.append(Fact(
                subject="user", predicate="uses_machine", object=r["hostname"],
                confidence=1.0, sources=["system"], evidence=[r],
                first_seen=now, last_seen=now,
            ))
    return out


_HANDLERS = {
    "apps": _from_apps,
    "calendar": _from_calendar,
    "contacts": _from_contacts,
    "mail": _from_mail,
    "git": _from_git,
    "browser": _from_browser,
    "screen_time": _from_screen_time,
    "shell": _from_shell,
    "files": _from_files,
    "system": _from_system,
}


def normalize() -> list[Fact]:
    facts: list[Fact] = []
    for name, handler in _HANDLERS.items():
        facts.extend(handler(_load(name)))
    return dedupe(facts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_normalizer.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/normalizer.py tests/scan/test_normalizer.py
git commit -m "feat(scan): add normalizer (raw → Fact)"
```

---

## Task 16 — Pattern detector

Hand-written rules that cluster Facts into typed Entities. Per spec §5.2 stage 3.

**Files:**
- Create: `yuki/scan/patterns.py`
- Create: `tests/scan/test_patterns.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_patterns.py`:

```python
from datetime import datetime, timezone

from yuki.scan.entities import Entity
from yuki.scan.facts import Fact
from yuki.scan.patterns import detect


def _f(subject, predicate, object_, sources, confidence=0.8):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return Fact(subject=subject, predicate=predicate, object=object_,
                confidence=confidence, sources=list(sources), evidence=[{}],
                first_seen=now, last_seen=now)


def test_recurring_meeting_plus_contact_yields_person():
    facts = [
        _f("Sarah Chen", "meets_with_recurring", "user", ["calendar"]),
        _f("sarah@x.com", "aliases_for", "Sarah Chen", ["contacts"]),
    ]
    entities = detect(facts)
    persons = [e for e in entities if e.kind == "person"]
    assert len(persons) == 1
    assert persons[0].name == "Sarah Chen"
    assert persons[0].confidence > 0.85


def test_app_high_focus_yields_primary():
    facts = [
        _f("user", "uses_app", "Slack", ["apps"]),
        _f("user", "focuses_on_app", "com.tinyspeck.slackmacgap", ["screen_time"], 0.9),
    ]
    entities = detect(facts)
    apps = [e for e in entities if e.kind == "app"]
    assert any(a.name == "Slack" for a in apps)


def test_git_repo_yields_project():
    facts = [_f("user", "works_on_project", "yuki", ["git"])]
    entities = detect(facts)
    projects = [e for e in entities if e.kind == "project"]
    assert len(projects) == 1
    assert projects[0].name == "Yuki" or projects[0].name == "yuki"


def test_no_facts_yields_no_entities():
    assert detect([]) == []


def test_email_without_contact_does_not_create_person():
    facts = [_f("user", "emails_with", "newsletter@spam.test", ["mail"])]
    entities = detect(facts)
    assert all(e.kind != "person" for e in entities)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_patterns.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/patterns.py`**

```python
"""Pattern detector — Fact[] → Entity[].

Rule-based; deterministic. Each rule reads facts, produces 0..N entities.
Per spec §5.2: people, projects, routines, apps, identity.
"""
from __future__ import annotations

import re
from collections import defaultdict

from yuki.scan.entities import Entity
from yuki.scan.facts import Fact

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slug(prefix: str, name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower()).strip("-")
    return f"{prefix}-{s}" if s else prefix


def _build_alias_map(facts: list[Fact]) -> dict[str, str]:
    """email/handle → canonical name from contacts."""
    out: dict[str, str] = {}
    for f in facts:
        if f.predicate == "aliases_for":
            out[f.subject] = f.object
    return out


def _detect_people(facts: list[Fact], aliases: dict[str, str]) -> list[Entity]:
    contact_names = set(aliases.values())
    by_name: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        if f.predicate in {"meets_with", "meets_with_recurring"}:
            by_name[f.subject].append(f)
        elif f.predicate == "emails_with":
            canonical = aliases.get(f.object)
            if canonical:
                by_name[canonical].append(f)

    out: list[Entity] = []
    for name, fs in by_name.items():
        if name not in contact_names and not any(
            f.predicate == "meets_with_recurring" for f in fs
        ):
            continue
        recurring = sum(1 for f in fs if f.predicate == "meets_with_recurring")
        emails = sum(1 for f in fs if f.predicate == "emails_with")
        confidence = min(0.99, 0.6 + 0.05 * (recurring + emails))
        out.append(Entity(
            kind="person", id=_slug("person", name), name=name,
            confidence=confidence, attributes={
                "interaction_frequency": _frequency(recurring + emails),
            },
            fact_ids=[],
        ))
    return out


def _frequency(n: int) -> str:
    if n >= 10:
        return "daily"
    if n >= 4:
        return "weekly"
    if n >= 1:
        return "monthly"
    return "rare"


def _detect_projects(facts: list[Fact]) -> list[Entity]:
    out: list[Entity] = []
    for f in facts:
        if f.predicate == "works_on_project":
            out.append(Entity(
                kind="project", id=_slug("project", f.object),
                name=f.object.title() if f.object.islower() else f.object,
                confidence=f.confidence,
                attributes={"status": "active"},
                fact_ids=[],
            ))
    return out


def _detect_apps(facts: list[Fact]) -> list[Entity]:
    by_name: dict[str, dict] = {}
    bundle_to_name: dict[str, str] = {}
    for f in facts:
        if f.predicate == "uses_app":
            by_name.setdefault(f.object, {"focus": 0, "bundle_id": ""})
        if f.predicate == "focuses_on_app":
            bundle_to_name[f.object] = f.object

    for f in facts:
        if f.predicate == "focuses_on_app":
            name_guess = f.object.split(".")[-1].title()
            entry = by_name.setdefault(name_guess, {"focus": 0, "bundle_id": ""})
            entry["focus"] += 1
            entry["bundle_id"] = f.object

    out: list[Entity] = []
    for name, info in by_name.items():
        importance = "primary" if info["focus"] >= 1 else "occasional"
        out.append(Entity(
            kind="app", id=_slug("app", name), name=name,
            confidence=0.8 if info["focus"] else 0.55,
            attributes={
                "bundle_id": info["bundle_id"],
                "importance": importance,
            },
            fact_ids=[],
        ))
    return out


def _detect_identity(facts: list[Fact]) -> list[Entity]:
    out: list[Entity] = []
    for f in facts:
        if f.predicate == "uses_machine":
            out.append(Entity(
                kind="identity", id="identity-profile", name="Profile",
                confidence=1.0, attributes={"hostname": f.object},
                fact_ids=[],
            ))
    return out


def detect(facts: list[Fact]) -> list[Entity]:
    aliases = _build_alias_map(facts)
    return [
        *_detect_identity(facts),
        *_detect_people(facts, aliases),
        *_detect_projects(facts),
        *_detect_apps(facts),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_patterns.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/patterns.py tests/scan/test_patterns.py
git commit -m "feat(scan): add rule-based pattern detector (Fact → Entity)"
```

---

## Task 17 — Notewriter (Jinja → Vault)

Renders each Entity to a markdown body via a Jinja template, builds the matching Pydantic note, and writes via `Vault.write()`. Frontmatter is built from the Entity's id, name, confidence, and attributes.

**Files:**
- Create: `yuki/scan/templates/person.md.j2`
- Create: `yuki/scan/templates/project.md.j2`
- Create: `yuki/scan/templates/routine.md.j2`
- Create: `yuki/scan/templates/app.md.j2`
- Create: `yuki/scan/templates/identity.md.j2`
- Create: `yuki/scan/notewriter.py`
- Create: `tests/scan/test_notewriter.py`

- [ ] **Step 1: Write the templates**

`yuki/scan/templates/person.md.j2`:

```jinja
# {{ name }}

{% if attributes.role %}**Role:** {{ attributes.role }}{% endif %}

Inferred from {{ sources | join(", ") }}.

Last seen via calendar/mail interactions.
```

`yuki/scan/templates/project.md.j2`:

```jinja
# {{ name }}

**Status:** {{ attributes.status }}

Inferred from git activity.
```

`yuki/scan/templates/routine.md.j2`:

```jinja
# {{ name }}

**Schedule:** {{ attributes.schedule }}

Steps: {% for s in attributes.steps %}[[{{ s }}]]{% if not loop.last %}, {% endif %}{% endfor %}
```

`yuki/scan/templates/app.md.j2`:

```jinja
# {{ name }}

**Bundle ID:** {{ attributes.bundle_id }}
**Importance:** {{ attributes.importance }}
```

`yuki/scan/templates/identity.md.j2`:

```jinja
# Profile

Hostname: {{ attributes.hostname }}
```

- [ ] **Step 2: Write the failing test**

Create `tests/scan/test_notewriter.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.vault import Vault
from yuki.scan.entities import Entity
from yuki.scan.notewriter import write_entities


def test_writes_person_note(tmp_vault: Path):
    e = Entity(kind="person", id="person-sarah-chen", name="Sarah Chen",
               confidence=0.92, attributes={"role": "manager",
                                             "interaction_frequency": "weekly"},
               fact_ids=[])
    v = Vault()
    written = write_entities([e], vault=v, sources=["calendar"])
    assert len(written) == 1
    note, body = v.read("person-sarah-chen")
    assert note.name == "Sarah Chen"
    assert "Sarah Chen" in body
    assert "weekly" not in note.model_dump() or note.interaction_frequency == "weekly"


def test_writes_project_note(tmp_vault: Path):
    e = Entity(kind="project", id="project-yuki", name="Yuki",
               confidence=0.85, attributes={"status": "active",
                                             "tech": ["python"],
                                             "path": "/Users/me/code/yuki"},
               fact_ids=[])
    v = Vault()
    write_entities([e], vault=v, sources=["git"])
    note, _ = v.read("project-yuki")
    assert note.status == "active"


def test_writes_app_note(tmp_vault: Path):
    e = Entity(kind="app", id="app-slack", name="Slack",
               confidence=0.85,
               attributes={"bundle_id": "com.tinyspeck.slackmacgap",
                           "importance": "primary"},
               fact_ids=[])
    v = Vault()
    write_entities([e], vault=v, sources=["apps", "screen_time"])
    note, _ = v.read("app-slack")
    assert note.importance == "primary"


def test_writes_identity_note(tmp_vault: Path):
    e = Entity(kind="identity", id="identity-profile", name="Profile",
               confidence=1.0, attributes={"hostname": "my-mac.local"},
               fact_ids=[])
    v = Vault()
    write_entities([e], vault=v, sources=["system"])
    note, body = v.read("identity-profile")
    assert "my-mac.local" in body


def test_skips_unsupported_kind(tmp_vault: Path):
    e = Entity(kind="routine", id="routine-x", name="X",
               confidence=0.5, attributes={"schedule": "??", "steps": []},
               fact_ids=[])
    v = Vault()
    written = write_entities([e], vault=v, sources=[])
    assert written == []
```

Note: routines are out of scope for the *onboarding* scanner — the spec says routines emerge from the *compactor* (Plan E), not the scan. So the notewriter does not produce routine notes here.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_notewriter.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `yuki/scan/notewriter.py`**

```python
"""Notewriter — Entity[] → markdown notes in the vault."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from yuki.memory.schemas import (
    AppNote,
    IdentityNote,
    PersonNote,
    PersonContact,
    ProjectNote,
    parse_note,
)
from yuki.memory.vault import Vault
from yuki.scan.entities import Entity

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=("md.j2",)),
    trim_blocks=True, lstrip_blocks=True,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_person(e: Entity, sources: list[str]) -> PersonNote:
    now = _now()
    return PersonNote(
        id=e.id, type="person", created_at=now, updated_at=now,
        confidence=e.confidence, source=sources, name=e.name,
        role=e.attributes.get("role"),
        relationship=e.attributes.get("relationship"),
        contact=PersonContact(),
        interaction_frequency=e.attributes.get("interaction_frequency"),
    )


def _build_project(e: Entity, sources: list[str]) -> ProjectNote:
    now = _now()
    return ProjectNote(
        id=e.id, type="project", created_at=now, updated_at=now,
        confidence=e.confidence, source=sources, name=e.name,
        status=e.attributes.get("status", "active"),
        tech=e.attributes.get("tech", []),
        path=e.attributes.get("path"),
    )


def _build_app(e: Entity, sources: list[str]) -> AppNote:
    now = _now()
    return AppNote(
        id=e.id, type="app", created_at=now, updated_at=now,
        confidence=e.confidence, source=sources, name=e.name,
        bundle_id=e.attributes.get("bundle_id", ""),
        importance=e.attributes.get("importance", "occasional"),
        common_uses=e.attributes.get("common_uses", []),
    )


def _build_identity(e: Entity, sources: list[str]) -> IdentityNote:
    now = _now()
    body_holder = ""  # body lives in template; schema body is summary
    return IdentityNote(
        id=e.id, type="identity", created_at=now, updated_at=now,
        confidence=e.confidence, source=sources, name=e.name,
        body=body_holder,
    )


_BUILDERS = {
    "person": _build_person,
    "project": _build_project,
    "app": _build_app,
    "identity": _build_identity,
}


def write_entities(
    entities: list[Entity],
    *,
    vault: Vault,
    sources: list[str],
) -> list[Path]:
    written: list[Path] = []
    for e in entities:
        builder = _BUILDERS.get(e.kind)
        if builder is None:
            continue
        note = builder(e, sources)
        template = _env.get_template(f"{e.kind}.md.j2")
        body = template.render(name=e.name, attributes=e.attributes, sources=sources)
        path = vault.write(note, body)
        written.append(path)
    return written
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_notewriter.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/templates/ yuki/scan/notewriter.py tests/scan/test_notewriter.py
git commit -m "feat(scan): add notewriter with Jinja templates"
```

---

## Task 18 — Polish (opt-in Haiku batch)

For entities flagged "rich-but-ambiguous", a single Haiku call rewrites their body into narrative form. Off by default. Per spec §5.2 stage 4.

A note is "rich-but-ambiguous" if `confidence >= 0.7` AND it has more than 3 evidence pieces in its facts. We don't pass raw facts to the LLM — only the entity name + attributes + a short evidence summary.

**Files:**
- Create: `yuki/scan/polish.py`
- Create: `tests/scan/test_polish.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_polish.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from yuki.scan.entities import Entity
from yuki.scan.polish import polish, should_polish


def test_should_polish_high_confidence_rich():
    e = Entity(kind="person", id="p", name="Sarah", confidence=0.85,
               attributes={"interaction_frequency": "daily"},
               fact_ids=["f1", "f2", "f3", "f4"])
    assert should_polish(e) is True


def test_should_not_polish_low_confidence():
    e = Entity(kind="person", id="p", name="Sarah", confidence=0.5,
               attributes={}, fact_ids=["f1", "f2", "f3", "f4"])
    assert should_polish(e) is False


def test_should_not_polish_thin_evidence():
    e = Entity(kind="person", id="p", name="Sarah", confidence=0.9,
               attributes={}, fact_ids=["f1"])
    assert should_polish(e) is False


def test_polish_calls_anthropic_once():
    e1 = Entity(kind="person", id="p1", name="Sarah", confidence=0.9,
                attributes={"interaction_frequency": "daily"},
                fact_ids=["a", "b", "c", "d"])
    e2 = Entity(kind="person", id="p2", name="Bob", confidence=0.9,
                attributes={"interaction_frequency": "weekly"},
                fact_ids=["a", "b", "c", "d"])
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.content = [MagicMock(text='{"p1": "Sarah is a daily collaborator.", "p2": "Bob is a weekly peer."}')]
    fake_client.messages.create.return_value = fake_resp

    with patch("yuki.scan.polish._client", return_value=fake_client):
        out = polish([e1, e2])

    assert out["p1"].startswith("Sarah")
    assert fake_client.messages.create.call_count == 1


def test_polish_empty_input_returns_empty():
    assert polish([]) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_polish.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/polish.py`**

```python
"""Polish — opt-in Haiku batch summarizer for rich-but-ambiguous entities."""
from __future__ import annotations

import json
import logging
from typing import Iterable

from yuki.scan.entities import Entity

log = logging.getLogger(__name__)


def _client():  # pragma: no cover — real Anthropic client only
    from anthropic import Anthropic
    return Anthropic()


def should_polish(entity: Entity) -> bool:
    return entity.confidence >= 0.7 and len(entity.fact_ids) >= 3


def _payload(entities: list[Entity]) -> str:
    return json.dumps({
        e.id: {"name": e.name, "kind": e.kind, "attributes": e.attributes}
        for e in entities
    }, indent=2)


def polish(entities: Iterable[Entity]) -> dict[str, str]:
    candidates = [e for e in entities if should_polish(e)]
    if not candidates:
        return {}
    client = _client()
    prompt = (
        "Rewrite each entity's body as one short narrative paragraph. "
        "Reply with JSON: {<entity_id>: <markdown body>, ...}. "
        "Be factual; do not invent details beyond the attributes given."
    )
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=4000,
        messages=[
            {"role": "user", "content": f"{prompt}\n\n{_payload(candidates)}"},
        ],
    )
    try:
        text = resp.content[0].text
        return json.loads(text)
    except Exception as e:
        log.warning("polish parse failed: %s", e)
        return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_polish.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/polish.py tests/scan/test_polish.py
git commit -m "feat(scan): add opt-in Haiku polish for rich entities"
```

---

## Task 19 — Runner (orchestrator + sentinel)

`run(polish=False, force=False)` runs the full pipeline: collectors in parallel → normalize → detect patterns → write notes → optional polish → sentinel. Re-running is a no-op unless `force=True`.

**Files:**
- Create: `yuki/scan/runner.py`
- Modify: `yuki/scan/__init__.py` (export `run`, `Fact`, `Entity`)
- Create: `tests/scan/test_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scan/test_runner.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuki.memory.vault import Vault
from yuki.scan import paths
from yuki.scan.runner import ScanResult, run


@pytest.mark.asyncio
async def test_runner_end_to_end_with_fakes(tmp_vault: Path, tmp_scan_cache: Path, tmp_home: Path):
    # Pre-seed cache files so collectors don't need to actually run.
    raw = tmp_scan_cache / "raw"
    raw.mkdir(parents=True)
    (raw / "apps.json").write_text(json.dumps([
        {"name": "Slack", "bundle_id": "com.tinyspeck.slackmacgap", "path": "/x"},
    ]))
    (raw / "system.json").write_text(json.dumps([
        {"macos_version": "14.4", "build": "x", "hostname": "mac.local", "locale": "en_US"},
    ]))
    (raw / "git.json").write_text(json.dumps([
        {"name": "yuki", "path": "/x", "last_commit": "2026-05-22T08:00:00+00:00",
         "commit_count": 50, "recent_subjects": []},
    ]))
    for empty in ("calendar", "contacts", "mail", "browser", "shell", "files", "screen_time"):
        (raw / f"{empty}.json").write_text("[]")

    async def noop_collectors():
        return None

    with patch("yuki.scan.runner._run_collectors", side_effect=noop_collectors):
        result = await run(polish=False, force=False)

    assert isinstance(result, ScanResult)
    assert result.entity_count >= 2  # identity + slack + project
    v = Vault()
    note, _ = v.read("identity-profile")
    assert note.id == "identity-profile"
    assert paths.sentinel_path().exists()


@pytest.mark.asyncio
async def test_runner_skips_when_sentinel_exists(tmp_vault: Path, tmp_scan_cache: Path, tmp_home: Path):
    paths.sentinel_path().parent.mkdir(parents=True, exist_ok=True)
    paths.sentinel_path().write_text("done")
    async def noop():
        return None
    with patch("yuki.scan.runner._run_collectors", side_effect=noop):
        result = await run(polish=False, force=False)
    assert result.skipped is True
    assert result.entity_count == 0


@pytest.mark.asyncio
async def test_runner_force_reruns(tmp_vault: Path, tmp_scan_cache: Path, tmp_home: Path):
    paths.sentinel_path().parent.mkdir(parents=True, exist_ok=True)
    paths.sentinel_path().write_text("done")
    raw = tmp_scan_cache / "raw"
    raw.mkdir(parents=True)
    for name in ("apps", "system", "git", "calendar", "contacts", "mail",
                 "browser", "shell", "files", "screen_time"):
        (raw / f"{name}.json").write_text("[]")

    async def noop():
        return None
    with patch("yuki.scan.runner._run_collectors", side_effect=noop):
        result = await run(polish=False, force=True)
    assert result.skipped is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_runner.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/scan/runner.py`**

```python
"""Onboarding scan runner — orchestrates the four-stage pipeline."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from yuki.memory.vault import Vault
from yuki.scan import paths
from yuki.scan.collectors.apps import AppsCollector
from yuki.scan.collectors.base import run_collector
from yuki.scan.collectors.browser import BrowserCollector
from yuki.scan.collectors.calendar import CalendarCollector
from yuki.scan.collectors.contacts import ContactsCollector
from yuki.scan.collectors.files import FilesCollector
from yuki.scan.collectors.git import GitCollector
from yuki.scan.collectors.mail import MailCollector
from yuki.scan.collectors.screen_time import ScreenTimeCollector
from yuki.scan.collectors.shell import ShellCollector
from yuki.scan.collectors.system import SystemCollector
from yuki.scan.normalizer import normalize
from yuki.scan.notewriter import write_entities
from yuki.scan.patterns import detect
from yuki.scan.polish import polish

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    skipped: bool
    fact_count: int
    entity_count: int
    written_paths: list[str]


async def _run_collectors() -> None:
    collectors = [
        SystemCollector(), AppsCollector(), ScreenTimeCollector(),
        CalendarCollector(), ContactsCollector(), MailCollector(),
        FilesCollector(), GitCollector(), BrowserCollector(), ShellCollector(),
    ]
    await asyncio.gather(*[run_collector(c) for c in collectors])


async def run(*, polish: bool = False, force: bool = False) -> ScanResult:
    sentinel = paths.sentinel_path()
    if sentinel.exists() and not force:
        log.info("scan sentinel exists, skipping")
        return ScanResult(skipped=True, fact_count=0, entity_count=0, written_paths=[])

    await _run_collectors()
    facts = normalize()
    entities = detect(facts)
    sources = sorted({s for f in facts for s in f.sources})
    vault = Vault()
    paths_written = write_entities(entities, vault=vault, sources=sources)

    if polish:
        polished_bodies = _polish_safely(entities)
        for entity_id, body in polished_bodies.items():
            try:
                note, _ = vault.read(entity_id)
                vault.write(note, body)
            except Exception as e:
                log.warning("polish write failed for %s: %s", entity_id, e)

    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("done")
    return ScanResult(
        skipped=False, fact_count=len(facts), entity_count=len(entities),
        written_paths=[str(p) for p in paths_written],
    )


def _polish_safely(entities: list) -> dict[str, str]:
    try:
        return polish(entities)
    except Exception as e:
        log.warning("polish failed: %s", e)
        return {}
```

- [ ] **Step 4: Update `yuki/scan/__init__.py`**

Replace contents with:

```python
"""Onboarding scanner: builds the seed vault on first run."""

from yuki.scan.entities import Entity
from yuki.scan.facts import Fact
from yuki.scan.runner import ScanResult, run

__all__ = ["Entity", "Fact", "ScanResult", "run"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/test_runner.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Run the full scan suite**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/scan/ -v`
Expected: all green (≈45 tests across 18 files).

- [ ] **Step 7: Run the full project suite**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest -v`
Expected: full suite passes (Plan A agent + Plan B memory + Plan C scan).

- [ ] **Step 8: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/scan/runner.py yuki/scan/__init__.py tests/scan/test_runner.py
git commit -m "feat(scan): add runner orchestrator with sentinel-guarded re-run"
```

---

## Wrap-up

After Task 19:

- `await run()` produces a seed vault from a real Mac in 30–90 seconds
- Each collector degrades gracefully on missing permissions / missing data
- Re-running is a no-op unless `force=True`
- The polish pass is opt-in and bounded to one Haiku call
- A `ScanResult` is returned to the caller (the SwiftUI permission wizard / review UI in Plan I+K)

Acceptance:
- `uv run pytest tests/scan/ -v` shows ≥45 tests, all green
- On a real Mac with `uv run python -c "import asyncio; from yuki.scan import run; r = asyncio.run(run()); print(r)"`, the scan completes and `~/YukiVault/` is populated with at least an identity note
- `grep -r "macos_use" yuki/scan/` returns nothing
- `~/YukiVault/.scan_complete` exists after a successful run

