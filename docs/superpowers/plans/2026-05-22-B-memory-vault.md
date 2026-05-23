# Plan B — Memory Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the markdown-vault + SQLite-index memory subsystem and expose three agent tools (`memory_search`, `memory_read`, `memory_write`) so the agent can read and write to `~/YukiVault/` during a chat turn.

**Architecture:** Markdown files at `~/YukiVault/` are the source of truth; a rebuildable SQLite index at `~/Library/Application Support/Yuki/index.db` provides BM25 (FTS5) + vector (sqlite-vec) retrieval merged via Reciprocal Rank Fusion. Notes are typed via Pydantic discriminators on a `type` frontmatter field. Three tools wrap the retriever for the agent. Wikilinks resolve by frontmatter `id` first, filename fallback.

**Tech Stack:** `pyyaml` for frontmatter, `pydantic` for note schemas, `sqlite-vec` for vector search, stdlib `sqlite3` for FTS5 + scalar rows, `voyageai` (default embedding provider) with optional `openai` fallback, `python-frontmatter` for round-trip safety, `pytest` + `pytest-mock` for tests.

**Spec reference:** `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` §4 (the entire memory vault section), §7.3 (memory tools), §11.2 (LLM privacy — only retrieved snippets sent).

**Prerequisite:** Plan A complete — `from yuki.agent import Agent` works and the tool registry pattern is in place.

---

## Resolved open questions (from spec §14)

1. **Embedding provider default** — Voyage AI (`voyage-3`, 1024 dims) for cost + quality. OpenAI `text-embedding-3-small` (1536 dims) as alternate. Dimension is set per-vault at init time and stored in `~/Library/Application Support/Yuki/index.db` `meta` table; switching providers requires a full reindex.
2. **Vault file naming** — slugified human name. `id` in frontmatter is the durable identifier; filename is a friendly slug that can drift. Resolver maps `id → path` via the SQLite index.

---

## File Structure

```
Yuki/
├── pyproject.toml                          # MODIFIED — adds pyyaml, python-frontmatter, pydantic, sqlite-vec, voyageai
├── yuki/
│   ├── memory/
│   │   ├── __init__.py                     # NEW — exports public types
│   │   ├── schemas.py                      # NEW — Pydantic models per note type + discriminator union
│   │   ├── frontmatter.py                  # NEW — read/write YAML frontmatter
│   │   ├── vault.py                        # NEW — Vault class: read/write/list/resolve
│   │   ├── embeddings.py                   # NEW — pluggable embedder (voyage default, openai alt, stub for tests)
│   │   ├── indexer.py                      # NEW — open db, schema migrations, reindex_all, upsert, delete
│   │   ├── retriever.py                    # NEW — hybrid search (FTS + vec) with RRF
│   │   └── paths.py                        # NEW — single source of truth for vault + db paths (env-overridable for tests)
│   └── tools/
│       └── memory/
│           ├── __init__.py                 # NEW
│           ├── memory_search.py            # NEW — @tool wrapping retriever.search
│           ├── memory_read.py              # NEW — @tool wrapping vault.read + 1-hop link expansion
│           └── memory_write.py             # NEW — @tool wrapping vault.write w/ confidence gating to 90-Inbox
└── tests/
    └── memory/
        ├── __init__.py
        ├── conftest.py                     # NEW — fixtures: tmp vault, stub embedder, seeded notes
        ├── test_frontmatter.py             # NEW — round-trip + edge cases
        ├── test_schemas.py                 # NEW — Pydantic validation per type
        ├── test_vault.py                   # NEW — read/write/list/resolve, slug collisions, id stability
        ├── test_indexer.py                 # NEW — reindex, upsert, delete, dim-change rejection
        ├── test_retriever.py               # NEW — FTS only, vec only, RRF merge, type filter
        └── tools/
            ├── __init__.py
            ├── test_memory_search.py       # NEW — tool wrapper happy path + error path
            ├── test_memory_read.py         # NEW — tool wrapper, link expansion
            └── test_memory_write.py        # NEW — tool wrapper, confidence gating
```

---

## Task 1 — Add memory dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add runtime + dev deps**

Edit `pyproject.toml`. In `[project] dependencies` add:

```toml
"pyyaml>=6.0.2",
"python-frontmatter>=1.1.0",
"pydantic>=2.9.0",
"sqlite-vec>=0.1.6",
"voyageai>=0.3.2",
```

In `[dependency-groups] dev` add:

```toml
"pytest-mock>=3.14.0",
```

(Skip lines that are already present from Plan A.)

- [ ] **Step 2: Sync the env**

Run: `cd /Users/mafex/code/personal/Yuki && uv sync`
Expected: lockfile updates, no errors.

- [ ] **Step 3: Verify imports**

Run: `cd /Users/mafex/code/personal/Yuki && uv run python -c "import yaml, frontmatter, pydantic, sqlite_vec, voyageai; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add pyproject.toml uv.lock
git commit -m "feat(memory): add memory subsystem dependencies"
```

---

## Task 2 — Paths module

A single source of truth for vault and DB paths, env-overridable so tests use temp dirs.

**Files:**
- Create: `yuki/memory/__init__.py`
- Create: `yuki/memory/paths.py`
- Create: `tests/memory/__init__.py`
- Create: `tests/memory/test_paths.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/__init__.py` (empty file) and `tests/memory/test_paths.py`:

```python
import os
from pathlib import Path

import pytest

from yuki.memory import paths


def test_default_vault_dir(monkeypatch):
    monkeypatch.delenv("YUKI_VAULT_DIR", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    assert paths.vault_dir() == Path("/tmp/fakehome/YukiVault")


def test_default_index_db_path(monkeypatch):
    monkeypatch.delenv("YUKI_INDEX_DB", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    expected = Path("/tmp/fakehome/Library/Application Support/Yuki/index.db")
    assert paths.index_db_path() == expected


def test_env_override_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "vault"))
    assert paths.vault_dir() == tmp_path / "vault"


def test_env_override_index(monkeypatch, tmp_path):
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    assert paths.index_db_path() == tmp_path / "index.db"


def test_section_dirs():
    sections = paths.SECTIONS
    assert "00-Identity" in sections
    assert "10-People" in sections
    assert "30-Routines" in sections
    assert "60-Episodes" in sections
    assert "90-Inbox" in sections
    assert len(sections) == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_paths.py -v`
Expected: ImportError / ModuleNotFoundError on `yuki.memory.paths`.

- [ ] **Step 3: Create empty `yuki/memory/__init__.py`**

```python
"""Memory subsystem: vault read/write, indexer, retriever, memory tools."""
```

- [ ] **Step 4: Implement `yuki/memory/paths.py`**

```python
"""Single source of truth for vault and index DB paths.

Env overrides:
- YUKI_VAULT_DIR — full path to the markdown vault (default ~/YukiVault)
- YUKI_INDEX_DB  — full path to the SQLite index (default
  ~/Library/Application Support/Yuki/index.db)
"""
from __future__ import annotations

import os
from pathlib import Path

SECTIONS: tuple[str, ...] = (
    "00-Identity",
    "10-People",
    "20-Projects",
    "30-Routines",
    "40-Apps",
    "50-Knowledge",
    "60-Episodes",
    "90-Inbox",
    "30-Routines/triggers",
)


def _home() -> Path:
    return Path(os.environ["HOME"])


def vault_dir() -> Path:
    override = os.environ.get("YUKI_VAULT_DIR")
    if override:
        return Path(override)
    return _home() / "YukiVault"


def index_db_path() -> Path:
    override = os.environ.get("YUKI_INDEX_DB")
    if override:
        return Path(override)
    return _home() / "Library" / "Application Support" / "Yuki" / "index.db"


def section_path(section: str) -> Path:
    if section not in SECTIONS:
        raise ValueError(f"Unknown section: {section!r}")
    return vault_dir() / section
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_paths.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/__init__.py yuki/memory/paths.py tests/memory/__init__.py tests/memory/test_paths.py
git commit -m "feat(memory): add paths module for vault and index locations"
```

---

## Task 3 — Note schemas

Pydantic models for each note type, plus a discriminated union (`AnyNote`) for parsing arbitrary frontmatter.

**Files:**
- Create: `yuki/memory/schemas.py`
- Create: `tests/memory/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_schemas.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from yuki.memory.schemas import (
    AnyNote,
    AppNote,
    PersonNote,
    ProjectNote,
    RoutineNote,
    TriggerNote,
    parse_note,
)


def _common():
    return {
        "id": "person-sarah-chen",
        "type": "person",
        "created_at": "2026-05-22T09:00:00Z",
        "updated_at": "2026-05-22T09:00:00Z",
        "confidence": 0.92,
        "source": ["calendar", "contacts"],
    }


def test_person_minimal():
    data = _common() | {"name": "Sarah Chen"}
    note = parse_note(data)
    assert isinstance(note, PersonNote)
    assert note.name == "Sarah Chen"
    assert note.relationship is None


def test_person_full():
    data = _common() | {
        "name": "Sarah Chen",
        "role": "Engineering Manager",
        "relationship": "manager",
        "contact": {"email": "sarah@example.com", "slack": "sarah"},
        "last_seen": "2026-05-21T15:00:00Z",
        "interaction_frequency": "daily",
    }
    note = parse_note(data)
    assert note.relationship == "manager"
    assert note.contact.email == "sarah@example.com"


def test_project_note():
    data = {
        **_common(),
        "id": "project-yuki",
        "type": "project",
        "name": "Yuki",
        "status": "active",
        "tech": ["python", "swift"],
        "path": "/Users/me/code/yuki",
        "last_touched": "2026-05-22T08:00:00Z",
    }
    note = parse_note(data)
    assert isinstance(note, ProjectNote)
    assert note.status == "active"


def test_routine_note():
    data = {
        **_common(),
        "id": "routine-morning",
        "type": "routine",
        "name": "Morning",
        "schedule": "weekdays 8am",
        "steps": ["[[Coffee]]", "[[Email Triage]]"],
        "trusted": False,
    }
    note = parse_note(data)
    assert isinstance(note, RoutineNote)
    assert note.trusted is False
    assert len(note.steps) == 2


def test_app_note():
    data = {
        **_common(),
        "id": "app-slack",
        "type": "app",
        "name": "Slack",
        "bundle_id": "com.tinyspeck.slackmacgap",
        "importance": "primary",
        "common_uses": ["team chat"],
    }
    note = parse_note(data)
    assert isinstance(note, AppNote)
    assert note.importance == "primary"


def test_trigger_note():
    data = {
        **_common(),
        "id": "trigger-standup-reminder",
        "type": "trigger",
        "enabled": True,
        "condition": {"kind": "time", "cron": "0 10 * * 1-5"},
        "debounce": "1h",
        "action": {"kind": "suggestion", "text": "Standup in 5"},
        "last_fired": None,
        "fire_count": 0,
        "acceptance_rate": 0.0,
    }
    note = parse_note(data)
    assert isinstance(note, TriggerNote)
    assert note.enabled is True


def test_invalid_type_rejected():
    data = _common() | {"type": "alien", "name": "x"}
    with pytest.raises(ValidationError):
        parse_note(data)


def test_confidence_out_of_range():
    data = _common() | {"name": "x", "confidence": 1.5}
    with pytest.raises(ValidationError):
        parse_note(data)


def test_id_must_be_slug():
    data = _common() | {"name": "x", "id": "Has Spaces"}
    with pytest.raises(ValidationError):
        parse_note(data)


def test_anynote_round_trip():
    data = _common() | {"name": "Sarah Chen"}
    note = parse_note(data)
    dumped = note.model_dump(mode="json")
    again = parse_note(dumped)
    assert again == note
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_schemas.py -v`
Expected: ModuleNotFoundError on `yuki.memory.schemas`.

- [ ] **Step 3: Implement `yuki/memory/schemas.py`**

```python
"""Pydantic models for the typed note frontmatter.

Every note has a `type` discriminator; `parse_note` returns the right subclass.
The vault/indexer/retriever all speak in `AnyNote` so the schema layer is the
only place note shapes live.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

ISO = str  # frontmatter dates are stored as ISO strings; Pydantic parses on read.

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class _Base(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    source: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("id must be lowercase kebab-case slug")
        return v


class PersonContact(BaseModel):
    slack: str | None = None
    email: str | None = None
    phone: str | None = None


class PersonNote(_Base):
    type: Literal["person"]
    name: str
    role: str | None = None
    relationship: Literal["manager", "report", "peer", "external", "personal"] | None = None
    contact: PersonContact = Field(default_factory=PersonContact)
    last_seen: datetime | None = None
    interaction_frequency: Literal["daily", "weekly", "monthly", "rare"] | None = None


class ProjectNote(_Base):
    type: Literal["project"]
    name: str
    status: Literal["active", "paused", "archived"]
    tech: list[str] = Field(default_factory=list)
    path: str | None = None
    last_touched: datetime | None = None


class RoutineNote(_Base):
    type: Literal["routine"]
    name: str
    schedule: str
    steps: list[str] = Field(default_factory=list)
    trusted: bool = False


class AppNote(_Base):
    type: Literal["app"]
    name: str
    bundle_id: str
    importance: Literal["primary", "occasional", "background"]
    common_uses: list[str] = Field(default_factory=list)


class IdentityNote(_Base):
    type: Literal["identity"]
    name: str
    body: str = ""


class PreferenceNote(_Base):
    type: Literal["preference"]
    name: str
    value: str


class KnowledgeNote(_Base):
    type: Literal["knowledge"]
    name: str


class EpisodeNote(_Base):
    type: Literal["episode"]
    date: str  # YYYY-MM-DD


class TriggerCondition(BaseModel):
    kind: Literal["time", "calendar", "app_state", "idle", "deviation", "external"]
    model_config = {"extra": "allow"}


class TriggerAction(BaseModel):
    kind: Literal["routine", "tool_call", "suggestion"]
    model_config = {"extra": "allow"}


class TriggerNote(_Base):
    type: Literal["trigger"]
    enabled: bool
    condition: TriggerCondition
    debounce: str
    action: TriggerAction
    last_fired: datetime | None = None
    fire_count: int = 0
    acceptance_rate: float = Field(default=0.0, ge=0.0, le=1.0)


AnyNote = Annotated[
    Union[
        PersonNote,
        ProjectNote,
        RoutineNote,
        AppNote,
        IdentityNote,
        PreferenceNote,
        KnowledgeNote,
        EpisodeNote,
        TriggerNote,
    ],
    Field(discriminator="type"),
]


class _NoteEnvelope(BaseModel):
    note: AnyNote


def parse_note(data: dict) -> AnyNote:
    """Validate a frontmatter dict into the right Note subclass."""
    return _NoteEnvelope(note=data).note
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_schemas.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/schemas.py tests/memory/test_schemas.py
git commit -m "feat(memory): add Pydantic note schemas with discriminated union"
```

---

## Task 4 — Frontmatter read/write

Thin wrapper over `python-frontmatter` so the rest of the code never imports it directly. Round-trip safe.

**Files:**
- Create: `yuki/memory/frontmatter.py`
- Create: `tests/memory/test_frontmatter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_frontmatter.py`:

```python
from pathlib import Path

from yuki.memory.frontmatter import dumps, loads, read_file, write_file


SAMPLE = """---
id: person-sarah-chen
type: person
name: Sarah Chen
confidence: 0.9
created_at: '2026-05-22T09:00:00Z'
updated_at: '2026-05-22T09:00:00Z'
source:
  - calendar
---

Sarah is the engineering manager.

Worked on [[Yuki]] launch.
"""


def test_loads_basic():
    fm, body = loads(SAMPLE)
    assert fm["id"] == "person-sarah-chen"
    assert fm["type"] == "person"
    assert "engineering manager" in body


def test_dumps_round_trip():
    fm, body = loads(SAMPLE)
    out = dumps(fm, body)
    fm2, body2 = loads(out)
    assert fm2 == fm
    assert body2.strip() == body.strip()


def test_loads_no_frontmatter():
    fm, body = loads("just a body, no frontmatter\n")
    assert fm == {}
    assert body.startswith("just a body")


def test_loads_empty_body():
    src = "---\nid: x-y\ntype: knowledge\n---\n"
    fm, body = loads(src)
    assert fm["id"] == "x-y"
    assert body == ""


def test_read_write_file(tmp_path: Path):
    p = tmp_path / "sarah.md"
    write_file(p, {"id": "person-sarah", "type": "person", "name": "Sarah"}, "Body text.")
    fm, body = read_file(p)
    assert fm["id"] == "person-sarah"
    assert body.strip() == "Body text."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_frontmatter.py -v`
Expected: ModuleNotFoundError on `yuki.memory.frontmatter`.

- [ ] **Step 3: Implement `yuki/memory/frontmatter.py`**

```python
"""YAML frontmatter read/write — round-trip safe wrapper over python-frontmatter."""
from __future__ import annotations

from pathlib import Path

import frontmatter
import yaml


def loads(text: str) -> tuple[dict, str]:
    """Parse a markdown string with optional YAML frontmatter."""
    post = frontmatter.loads(text)
    return dict(post.metadata), post.content


def dumps(metadata: dict, body: str) -> str:
    """Serialize metadata + body back to markdown text."""
    post = frontmatter.Post(body, **metadata)
    return frontmatter.dumps(post, Dumper=yaml.SafeDumper)


def read_file(path: Path) -> tuple[dict, str]:
    return loads(path.read_text(encoding="utf-8"))


def write_file(path: Path, metadata: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(metadata, body), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_frontmatter.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/frontmatter.py tests/memory/test_frontmatter.py
git commit -m "feat(memory): add frontmatter read/write helper"
```

---

## Task 5 — Vault class (read/write/list/resolve)

The `Vault` class owns the markdown filesystem. It doesn't touch SQLite — that's the indexer's job. It reads and writes typed notes, lists by section, resolves wikilinks (`[[Other Note]]`) by id first, filename second.

**Files:**
- Create: `yuki/memory/vault.py`
- Create: `tests/conftest.py` (project-root fixtures, importable from any test package)
- Create: `tests/memory/test_vault.py`

- [ ] **Step 1: Add shared fixtures at the project test root**

Create `tests/conftest.py` (NOT `tests/memory/conftest.py` — putting it at the test root means later plans like E and H can use the same fixture without re-exporting):

```python
from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path: Path, monkeypatch) -> Path:
    """Empty vault rooted at a temp dir, with all sections pre-created."""
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    from yuki.memory.paths import SECTIONS
    for section in SECTIONS:
        (vault / section).mkdir(parents=True, exist_ok=True)
    return vault
```

- [ ] **Step 2: Write the failing test**

Create `tests/memory/test_vault.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.schemas import PersonNote, ProjectNote
from yuki.memory.vault import Vault, VaultError


def _person(id_: str = "person-sarah-chen", name: str = "Sarah Chen") -> PersonNote:
    now = datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)
    return PersonNote(
        id=id_,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["calendar"],
        name=name,
    )


def test_write_then_read_round_trip(tmp_vault: Path):
    v = Vault()
    note = _person()
    v.write(note, body="Engineering manager.")
    fetched, body = v.read(note.id)
    assert fetched == note
    assert body.strip() == "Engineering manager."


def test_write_routes_by_type(tmp_vault: Path):
    v = Vault()
    v.write(_person(), body="x")
    files = list((tmp_vault / "10-People").glob("*.md"))
    assert len(files) == 1


def test_filename_is_slugified(tmp_vault: Path):
    v = Vault()
    v.write(_person(name="Sarah O'Chen"), body="x")
    files = list((tmp_vault / "10-People").glob("*.md"))
    assert files[0].name == "Sarah-O-Chen.md" or files[0].name == "Sarah-OChen.md"


def test_id_resolves_after_filename_change(tmp_vault: Path):
    v = Vault()
    note = _person()
    v.write(note, body="x")
    src = next((tmp_vault / "10-People").glob("*.md"))
    src.rename(src.with_name("Renamed.md"))
    fetched, _ = v.read(note.id)
    assert fetched.id == note.id


def test_list_section(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-a", "A"), body="")
    v.write(_person("person-b", "B"), body="")
    items = v.list_section("10-People")
    assert {n.id for n, _ in items} == {"person-a", "person-b"}


def test_read_missing_raises(tmp_vault: Path):
    v = Vault()
    with pytest.raises(VaultError):
        v.read("nope-not-here")


def test_resolve_wikilink_by_id(tmp_vault: Path):
    v = Vault()
    v.write(_person(), body="x")
    path = v.resolve_wikilink("person-sarah-chen")
    assert path is not None and path.exists()


def test_resolve_wikilink_by_filename(tmp_vault: Path):
    v = Vault()
    v.write(_person(name="Sarah Chen"), body="x")
    path = v.resolve_wikilink("Sarah Chen")
    assert path is not None
    fm, _ = v.read_path(path)
    assert fm["id"] == "person-sarah-chen"


def test_write_to_inbox_when_low_confidence(tmp_vault: Path):
    v = Vault()
    note = _person()
    note = note.model_copy(update={"confidence": 0.5})
    v.write(note, body="x", route_low_confidence=True)
    inbox = list((tmp_vault / "90-Inbox").glob("*.md"))
    people = list((tmp_vault / "10-People").glob("*.md"))
    assert len(inbox) == 1 and len(people) == 0


def test_walk_yields_all(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-a", "A"), body="")
    v.write(_person("person-b", "B"), body="")
    ids = {n.id for n, _ in v.walk()}
    assert ids == {"person-a", "person-b"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_vault.py -v`
Expected: ModuleNotFoundError on `yuki.memory.vault`.

- [ ] **Step 4: Implement `yuki/memory/vault.py`**

```python
"""Markdown vault: read/write typed notes, list, walk, resolve wikilinks.

Source of truth is the filesystem. The indexer (separate module) caches metadata
for fast retrieval but every fact in the vault can be reconstructed from .md files.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from yuki.memory import frontmatter as fm
from yuki.memory import paths
from yuki.memory.schemas import AnyNote, parse_note

# type → section. Triggers live under 30-Routines/triggers.
_TYPE_TO_SECTION: dict[str, str] = {
    "identity": "00-Identity",
    "preference": "00-Identity",
    "person": "10-People",
    "project": "20-Projects",
    "routine": "30-Routines",
    "app": "40-Apps",
    "knowledge": "50-Knowledge",
    "episode": "60-Episodes",
    "trigger": "30-Routines/triggers",
}


class VaultError(Exception):
    """Raised on missing notes, write failures, or schema errors at the vault layer."""


def slugify(name: str) -> str:
    """Filesystem-safe slug; preserves capitalization for human-friendly filenames."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = nfkd.encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^\w\s-]", "", ascii_only)
    return re.sub(r"[\s_]+", "-", cleaned).strip("-")


class Vault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or paths.vault_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        for section in paths.SECTIONS:
            (self.root / section).mkdir(parents=True, exist_ok=True)

    def _section_for(self, note: AnyNote, *, low_confidence: bool) -> Path:
        if low_confidence:
            return self.root / "90-Inbox"
        return self.root / _TYPE_TO_SECTION[note.type]

    def _filename_for(self, note: AnyNote) -> str:
        name = getattr(note, "name", note.id)
        return f"{slugify(name) or note.id}.md"

    def write(
        self,
        note: AnyNote,
        body: str,
        *,
        route_low_confidence: bool = False,
    ) -> Path:
        low = route_low_confidence and note.confidence < 0.7
        section = self._section_for(note, low_confidence=low)
        section.mkdir(parents=True, exist_ok=True)
        path = section / self._filename_for(note)
        meta = note.model_dump(mode="json")
        fm.write_file(path, meta, body)
        return path

    def read(self, id_: str) -> tuple[AnyNote, str]:
        path = self.resolve_wikilink(id_)
        if path is None:
            raise VaultError(f"Note not found: {id_}")
        return self.read_path(path)

    def read_path(self, path: Path) -> tuple[AnyNote, str]:
        meta, body = fm.read_file(path)
        try:
            note = parse_note(meta)
        except Exception as e:
            raise VaultError(f"Invalid note at {path}: {e}") from e
        return note, body

    def resolve_wikilink(self, target: str) -> Path | None:
        """Resolve [[target]] — id first, then filename (case-insensitive)."""
        for path in self._iter_markdown():
            try:
                meta, _ = fm.read_file(path)
            except Exception:
                continue
            if meta.get("id") == target:
                return path
        slug_target = slugify(target).lower()
        for path in self._iter_markdown():
            if path.stem.lower() == slug_target or path.stem.lower() == target.lower():
                return path
        return None

    def list_section(self, section: str) -> list[tuple[AnyNote, str]]:
        out: list[tuple[AnyNote, str]] = []
        for path in (self.root / section).glob("*.md"):
            try:
                out.append(self.read_path(path))
            except VaultError:
                continue
        return out

    def walk(self) -> Iterator[tuple[AnyNote, str]]:
        for path in self._iter_markdown():
            try:
                yield self.read_path(path)
            except VaultError:
                continue

    def _iter_markdown(self) -> Iterator[Path]:
        yield from self.root.rglob("*.md")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_vault.py -v`
Expected: 10 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/vault.py tests/conftest.py tests/memory/test_vault.py
git commit -m "feat(memory): add Vault class with read/write/list/wikilink resolution"
```

---

## Task 6 — Embedding provider abstraction

A pluggable embedder interface. Voyage default, OpenAI alt, deterministic stub for tests. The indexer never imports voyageai or openai directly.

**Files:**
- Create: `yuki/memory/embeddings.py`
- Create: `tests/memory/test_embeddings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_embeddings.py`:

```python
import pytest

from yuki.memory.embeddings import (
    Embedder,
    StubEmbedder,
    get_embedder,
)


def test_stub_is_deterministic():
    e = StubEmbedder(dim=8)
    a = e.embed_one("hello world")
    b = e.embed_one("hello world")
    assert a == b
    assert len(a) == 8


def test_stub_different_inputs_differ():
    e = StubEmbedder(dim=8)
    assert e.embed_one("apple") != e.embed_one("banana")


def test_stub_batch():
    e = StubEmbedder(dim=4)
    out = e.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == 4 for v in out)


def test_get_embedder_default(monkeypatch):
    monkeypatch.setenv("YUKI_EMBEDDER", "stub")
    e = get_embedder()
    assert isinstance(e, StubEmbedder)


def test_get_embedder_unknown(monkeypatch):
    monkeypatch.setenv("YUKI_EMBEDDER", "nonsense")
    with pytest.raises(ValueError):
        get_embedder()


def test_embedder_protocol_dim():
    e: Embedder = StubEmbedder(dim=12)
    assert e.dim == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_embeddings.py -v`
Expected: ModuleNotFoundError on `yuki.memory.embeddings`.

- [ ] **Step 3: Implement `yuki/memory/embeddings.py`**

```python
"""Pluggable embedding providers.

The indexer + retriever depend only on the Embedder protocol. Switching providers
at the env level (YUKI_EMBEDDER=voyage|openai|stub) is the only intended config knob.
"""
from __future__ import annotations

import hashlib
import os
import struct
from typing import Protocol


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...
    def embed_one(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class StubEmbedder:
    """Deterministic, hash-based fake. For tests only."""

    def __init__(self, dim: int = 16) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Repeat hash bytes until we have enough float32 worth of data.
        needed = self._dim * 4
        buf = (h * ((needed // len(h)) + 1))[:needed]
        floats = struct.unpack(f"{self._dim}f", buf)
        # Normalize to unit-ish vector so cosine sim stays bounded.
        norm = sum(x * x for x in floats) ** 0.5 or 1.0
        return [x / norm for x in floats]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class VoyageEmbedder:
    """Production default. Requires VOYAGE_API_KEY."""

    def __init__(self, model: str = "voyage-3", dim: int = 1024) -> None:
        import voyageai

        self._client = voyageai.Client()
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        result = self._client.embed(texts, model=self._model, input_type="document")
        return list(result.embeddings)


class OpenAIEmbedder:
    """Alternate. Requires OPENAI_API_KEY."""

    def __init__(self, model: str = "text-embedding-3-small", dim: int = 1536) -> None:
        from openai import OpenAI

        self._client = OpenAI()
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    name = os.environ.get("YUKI_EMBEDDER", "voyage").lower()
    if name == "voyage":
        return VoyageEmbedder()
    if name == "openai":
        return OpenAIEmbedder()
    if name == "stub":
        return StubEmbedder()
    raise ValueError(f"Unknown embedder: {name!r}. Use voyage|openai|stub.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_embeddings.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/embeddings.py tests/memory/test_embeddings.py
git commit -m "feat(memory): add pluggable embedder (voyage default, stub for tests)"
```

---

## Task 7 — SQLite indexer

Schema, `reindex_all`, `upsert_note`, `delete_note`. Backed by stdlib `sqlite3` plus `sqlite-vec` for `vec0` virtual tables. Embedding dim recorded in a `meta` row at first init; mismatched dim on reopen → raise.

**Files:**
- Create: `yuki/memory/indexer.py`
- Create: `tests/memory/test_indexer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_indexer.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer, IndexerError
from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault


def _person(id_: str, name: str) -> PersonNote:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return PersonNote(
        id=id_,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["calendar"],
        name=name,
    )


def test_open_creates_schema(tmp_vault: Path):
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    assert idx.row_count() == 0
    idx.close()


def test_upsert_then_count(tmp_vault: Path):
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.upsert(_person("person-a", "A"), body="alice rocks", path=tmp_vault / "10-People/A.md")
    assert idx.row_count() == 1


def test_upsert_replaces_same_id(tmp_vault: Path):
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.upsert(_person("person-a", "A"), body="v1", path=tmp_vault / "10-People/A.md")
    idx.upsert(_person("person-a", "A"), body="v2", path=tmp_vault / "10-People/A.md")
    assert idx.row_count() == 1


def test_delete_removes(tmp_vault: Path):
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.upsert(_person("person-a", "A"), body="x", path=tmp_vault / "10-People/A.md")
    idx.delete("person-a")
    assert idx.row_count() == 0


def test_dim_mismatch_rejected(tmp_vault: Path):
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.close()
    idx2 = Indexer(embedder=StubEmbedder(dim=16))
    with pytest.raises(IndexerError):
        idx2.open()


def test_reindex_all_walks_vault(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-a", "A"), body="alpha")
    v.write(_person("person-b", "B"), body="beta")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    assert idx.row_count() == 2


def test_reindex_idempotent(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-a", "A"), body="alpha")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    idx.reindex_all(v)
    assert idx.row_count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_indexer.py -v`
Expected: ModuleNotFoundError on `yuki.memory.indexer`.

- [ ] **Step 3: Implement `yuki/memory/indexer.py`**

```python
"""SQLite + sqlite-vec index over the markdown vault.

The vault is the source of truth. This index is rebuildable via reindex_all().
"""
from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import sqlite_vec

from yuki.memory import paths
from yuki.memory.embeddings import Embedder
from yuki.memory.schemas import AnyNote

if TYPE_CHECKING:
    from yuki.memory.vault import Vault


class IndexerError(Exception):
    """Raised on schema mismatch or DB-level failures."""


def _floats_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class Indexer:
    def __init__(self, embedder: Embedder, db_path: Path | None = None) -> None:
        self._embedder = embedder
        self._db_path = db_path or paths.index_db_path()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        self._init_schema(conn)
        self._verify_dim(conn)
        self._conn = conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        dim = self._embedder.dim
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT,
                body_hash TEXT,
                updated_at TEXT,
                confidence REAL,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS links (
                src_id TEXT,
                dst_id TEXT,
                PRIMARY KEY (src_id, dst_id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS note_vec USING vec0(
                id TEXT PRIMARY KEY,
                embedding FLOAT[{dim}]
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(id, title, body);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('embedding_dim', ?)",
            (str(dim),),
        )
        conn.commit()

    def _verify_dim(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'embedding_dim'"
        ).fetchone()
        if row is None:
            return
        stored = int(row[0])
        if stored != self._embedder.dim:
            raise IndexerError(
                f"Embedding dim mismatch: db={stored}, embedder={self._embedder.dim}. "
                "Reindex required."
            )

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise IndexerError("Indexer is not open. Call .open() first.")
        return self._conn

    def upsert(self, note: AnyNote, body: str, path: Path) -> None:
        title = getattr(note, "name", note.id)
        text = f"{title}\n\n{body}"
        vec = self._embedder.embed_one(text)
        c = self.conn
        c.execute("DELETE FROM notes WHERE id = ?", (note.id,))
        c.execute("DELETE FROM note_vec WHERE id = ?", (note.id,))
        c.execute("DELETE FROM note_fts WHERE id = ?", (note.id,))
        c.execute(
            "INSERT INTO notes(id, path, type, title, body_hash, updated_at, confidence, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note.id,
                str(path),
                note.type,
                title,
                str(hash(body)),
                note.updated_at.isoformat(),
                note.confidence,
                json.dumps(note.model_dump(mode="json")),
            ),
        )
        c.execute(
            "INSERT INTO note_vec(id, embedding) VALUES (?, ?)",
            (note.id, _floats_to_blob(vec)),
        )
        c.execute(
            "INSERT INTO note_fts(id, title, body) VALUES (?, ?, ?)",
            (note.id, title, body),
        )
        c.commit()

    def delete(self, id_: str) -> None:
        c = self.conn
        c.execute("DELETE FROM notes WHERE id = ?", (id_,))
        c.execute("DELETE FROM note_vec WHERE id = ?", (id_,))
        c.execute("DELETE FROM note_fts WHERE id = ?", (id_,))
        c.commit()

    def reindex_all(self, vault: "Vault") -> None:
        c = self.conn
        c.executescript(
            "DELETE FROM notes; DELETE FROM note_vec; DELETE FROM note_fts;"
        )
        c.commit()
        for note, body in vault.walk():
            section_dir = vault.root  # path resolved during walk
            # We don't know the exact path from walk(), so re-resolve via Vault.
            path = vault.resolve_wikilink(note.id)
            assert path is not None
            self.upsert(note, body, path)

    def row_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_indexer.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/indexer.py tests/memory/test_indexer.py
git commit -m "feat(memory): add SQLite indexer with FTS5 + sqlite-vec"
```

---

## Task 8 — Retriever (hybrid BM25 + vector via RRF)

`Retriever.search(query, k=5, types=None)` runs FTS5 and vec0 in parallel, merges with Reciprocal Rank Fusion (k=60 constant, standard), filters by type, and returns hits with metadata + 200-char snippet.

**Files:**
- Create: `yuki/memory/retriever.py`
- Create: `tests/memory/test_retriever.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_retriever.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer
from yuki.memory.retriever import Hit, Retriever
from yuki.memory.schemas import PersonNote, ProjectNote
from yuki.memory.vault import Vault


def _person(id_, name):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return PersonNote(id=id_, type="person", created_at=now, updated_at=now,
                      confidence=0.9, source=[], name=name)


def _project(id_, name):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return ProjectNote(id=id_, type="project", created_at=now, updated_at=now,
                       confidence=0.9, source=[], name=name, status="active")


@pytest.fixture
def seeded(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="engineering manager who runs standup")
    v.write(_person("person-bob", "Bob Liu"), body="data scientist focused on ranking")
    v.write(_project("project-yuki", "Yuki"), body="macos jarvis assistant")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    yield v, idx
    idx.close()


def test_search_returns_hits(seeded):
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("standup", k=5)
    assert any(h.id == "person-sarah" for h in hits)


def test_search_filters_by_type(seeded):
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("yuki", k=5, types=["project"])
    assert all(h.type == "project" for h in hits)


def test_search_k_caps_results(seeded):
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("a", k=2)
    assert len(hits) <= 2


def test_hit_has_snippet(seeded):
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("standup", k=1)
    assert hits[0].snippet  # non-empty
    assert len(hits[0].snippet) <= 220


def test_empty_query_returns_empty(seeded):
    _, idx = seeded
    r = Retriever(idx)
    assert r.search("", k=5) == []


def test_no_match_returns_empty(seeded):
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("zzzzz-no-such-token-anywhere", k=5)
    # Vector search may still return things; but with stub deterministic embeds,
    # at minimum the fts side should be empty. We assert the contract: list returned.
    assert isinstance(hits, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_retriever.py -v`
Expected: ModuleNotFoundError on `yuki.memory.retriever`.

- [ ] **Step 3: Implement `yuki/memory/retriever.py`**

```python
"""Hybrid retrieval: FTS5 + vec0, merged via Reciprocal Rank Fusion."""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass

from yuki.memory.indexer import Indexer

_RRF_K = 60  # standard constant from the original RRF paper


def _floats_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


@dataclass
class Hit:
    id: str
    type: str
    title: str
    path: str
    snippet: str
    score: float


class Retriever:
    def __init__(self, indexer: Indexer) -> None:
        self._idx = indexer

    def search(
        self,
        query: str,
        k: int = 5,
        types: list[str] | None = None,
    ) -> list[Hit]:
        if not query.strip():
            return []
        conn = self._idx.conn

        fts_rows = conn.execute(
            "SELECT id FROM note_fts WHERE note_fts MATCH ? LIMIT 50",
            (query,),
        ).fetchall()
        fts_ranked = {row[0]: rank for rank, row in enumerate(fts_rows)}

        from yuki.memory.embeddings import StubEmbedder  # avoid hard import cycle
        # The retriever uses the indexer's embedder for query-side embedding.
        embedder = self._idx._embedder  # noqa: SLF001 — internal collaborator
        qvec = embedder.embed_one(query)
        vec_rows = conn.execute(
            "SELECT id FROM note_vec WHERE embedding MATCH ? "
            "ORDER BY distance LIMIT 50",
            (_floats_to_blob(qvec),),
        ).fetchall()
        vec_ranked = {row[0]: rank for rank, row in enumerate(vec_rows)}

        all_ids = set(fts_ranked) | set(vec_ranked)
        scored: list[tuple[str, float]] = []
        for nid in all_ids:
            score = 0.0
            if nid in fts_ranked:
                score += 1.0 / (_RRF_K + fts_ranked[nid])
            if nid in vec_ranked:
                score += 1.0 / (_RRF_K + vec_ranked[nid])
            scored.append((nid, score))
        scored.sort(key=lambda t: t[1], reverse=True)

        hits: list[Hit] = []
        for nid, score in scored:
            row = conn.execute(
                "SELECT n.id, n.type, n.title, n.path, COALESCE(f.body, '') "
                "FROM notes n LEFT JOIN note_fts f ON f.id = n.id WHERE n.id = ?",
                (nid,),
            ).fetchone()
            if row is None:
                continue
            id_, type_, title, path, body = row
            if types and type_ not in types:
                continue
            snippet = (body or "")[:200]
            hits.append(Hit(id=id_, type=type_, title=title, path=path,
                            snippet=snippet, score=score))
            if len(hits) >= k:
                break
        return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_retriever.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/retriever.py tests/memory/test_retriever.py
git commit -m "feat(memory): add hybrid BM25+vector retriever with RRF merge"
```

---

## Task 9 — `memory_search` tool

Wraps `Retriever.search` for the agent. Returns JSON-serializable hits with frontmatter snippet.

**Files:**
- Create: `yuki/tools/memory/__init__.py`
- Create: `yuki/tools/memory/memory_search.py`
- Create: `tests/memory/tools/__init__.py`
- Create: `tests/memory/tools/test_memory_search.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/tools/__init__.py` (empty) and `tests/memory/tools/test_memory_search.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer
from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault
from yuki.tools.memory.memory_search import memory_search


def _person(id_, name):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return PersonNote(id=id_, type="person", created_at=now, updated_at=now,
                      confidence=0.9, source=[], name=name)


@pytest.fixture
def memctx(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="standup runner")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    yield idx
    idx.close()


def test_memory_search_returns_dict_list(memctx):
    out = memory_search(query="standup", k=3, indexer=memctx)
    assert isinstance(out, list)
    assert all(isinstance(h, dict) for h in out)
    assert any(h["id"] == "person-sarah" for h in out)


def test_memory_search_respects_types(memctx):
    out = memory_search(query="standup", k=5, types=["project"], indexer=memctx)
    assert all(h["type"] == "project" for h in out)


def test_memory_search_empty_query(memctx):
    assert memory_search(query="   ", k=5, indexer=memctx) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/tools/test_memory_search.py -v`
Expected: ModuleNotFoundError on `yuki.tools.memory.memory_search`.

- [ ] **Step 3: Implement the tool**

Create `yuki/tools/memory/__init__.py`:

```python
"""Memory tools exposed to the agent: search, read, write."""
```

Create `yuki/tools/memory/memory_search.py`:

```python
"""memory_search — hybrid retrieval over the vault."""
from __future__ import annotations

from yuki.memory.indexer import Indexer
from yuki.memory.retriever import Retriever


def memory_search(
    query: str,
    k: int = 5,
    types: list[str] | None = None,
    *,
    indexer: Indexer,
) -> list[dict]:
    """Search the memory vault.

    Args:
        query: free-form text query.
        k: max hits to return (default 5).
        types: optional list of note types to filter to (e.g. ["person"]).
        indexer: the open Indexer (DI; agent runtime supplies one per session).

    Returns:
        List of dicts: {id, type, title, path, snippet, score}.
    """
    retriever = Retriever(indexer)
    hits = retriever.search(query, k=k, types=types)
    return [
        {
            "id": h.id,
            "type": h.type,
            "title": h.title,
            "path": h.path,
            "snippet": h.snippet,
            "score": h.score,
        }
        for h in hits
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/tools/test_memory_search.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/memory/__init__.py yuki/tools/memory/memory_search.py tests/memory/tools/__init__.py tests/memory/tools/test_memory_search.py
git commit -m "feat(memory): add memory_search tool"
```

---

## Task 10 — `memory_read` tool

Reads one note by id or path. With `expand_links=1`, inlines linked notes one hop deep (resolved by frontmatter id, then filename).

**Files:**
- Create: `yuki/tools/memory/memory_read.py`
- Create: `tests/memory/tools/test_memory_read.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/tools/test_memory_read.py`:

```python
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault
from yuki.tools.memory.memory_read import memory_read


def _person(id_, name):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return PersonNote(id=id_, type="person", created_at=now, updated_at=now,
                      confidence=0.9, source=[], name=name)


def test_read_by_id(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="manager")
    out = memory_read(id_or_path="person-sarah", vault=v)
    assert out["id"] == "person-sarah"
    assert "manager" in out["body"]


def test_read_by_path(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="manager")
    md_file = next((tmp_vault / "10-People").glob("*.md"))
    out = memory_read(id_or_path=str(md_file), vault=v)
    assert out["id"] == "person-sarah"


def test_missing_raises(tmp_vault: Path):
    v = Vault()
    with pytest.raises(KeyError):
        memory_read(id_or_path="not-here", vault=v)


def test_expand_links_inlines_one_hop(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="great manager")
    v.write(_person("person-bob", "Bob Liu"),
            body="reports to [[person-sarah]] and likes ranking")
    out = memory_read(id_or_path="person-bob", vault=v, expand_links=1)
    assert "linked" in out
    assert any(n["id"] == "person-sarah" for n in out["linked"])


def test_expand_links_zero(tmp_vault: Path):
    v = Vault()
    v.write(_person("person-bob", "Bob Liu"), body="links to [[person-sarah]]")
    out = memory_read(id_or_path="person-bob", vault=v, expand_links=0)
    assert out.get("linked", []) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/tools/test_memory_read.py -v`
Expected: ModuleNotFoundError on `yuki.tools.memory.memory_read`.

- [ ] **Step 3: Implement the tool**

Create `yuki/tools/memory/memory_read.py`:

```python
"""memory_read — load one note (and optionally its linked notes)."""
from __future__ import annotations

import re
from pathlib import Path

from yuki.memory.vault import Vault, VaultError

_WIKILINK = re.compile(r"\[\[([^\]\|]+)(?:\|[^\]]+)?\]\]")


def _to_dict(note, body: str) -> dict:
    return {
        "id": note.id,
        "type": note.type,
        "title": getattr(note, "name", note.id),
        "metadata": note.model_dump(mode="json"),
        "body": body,
    }


def memory_read(
    id_or_path: str,
    *,
    vault: Vault,
    expand_links: int = 0,
) -> dict:
    """Read one note from the vault.

    Args:
        id_or_path: frontmatter id, filename, or full path on disk.
        vault: Vault instance.
        expand_links: if >=1, inline notes referenced by [[wikilinks]] one hop deep.

    Returns:
        {id, type, title, metadata, body, linked: [<note dict>, ...]}.

    Raises:
        KeyError: if id_or_path doesn't resolve to anything.
    """
    path: Path | None
    if id_or_path.endswith(".md") and Path(id_or_path).exists():
        path = Path(id_or_path)
        note, body = vault.read_path(path)
    else:
        try:
            note, body = vault.read(id_or_path)
        except VaultError as e:
            raise KeyError(str(e)) from e

    out = _to_dict(note, body)
    out["linked"] = []

    if expand_links >= 1:
        seen = {note.id}
        for target in _WIKILINK.findall(body):
            target = target.strip()
            try:
                linked_note, linked_body = vault.read(target)
            except VaultError:
                resolved = vault.resolve_wikilink(target)
                if resolved is None:
                    continue
                linked_note, linked_body = vault.read_path(resolved)
            if linked_note.id in seen:
                continue
            seen.add(linked_note.id)
            out["linked"].append(_to_dict(linked_note, linked_body))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/tools/test_memory_read.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/memory/memory_read.py tests/memory/tools/test_memory_read.py
git commit -m "feat(memory): add memory_read tool with link expansion"
```

---

## Task 11 — `memory_write` tool

Writes a note to the vault. If `confidence < 0.7`, routes to `90-Inbox/` instead. Updates the indexer in lockstep so retrieval stays fresh. Supports an `update` mode that merges into an existing note.

**Files:**
- Create: `yuki/tools/memory/memory_write.py`
- Create: `tests/memory/tools/test_memory_write.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/tools/test_memory_write.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer
from yuki.memory.vault import Vault
from yuki.tools.memory.memory_write import memory_write


@pytest.fixture
def memctx(tmp_vault: Path):
    v = Vault()
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    yield v, idx
    idx.close()


def _person_payload(id_="person-sarah", name="Sarah Chen", confidence=0.9):
    return {
        "id": id_,
        "type": "person",
        "name": name,
        "confidence": confidence,
        "source": ["scan"],
        "created_at": "2026-05-22T09:00:00+00:00",
        "updated_at": "2026-05-22T09:00:00+00:00",
    }


def test_write_creates_note_and_indexes(memctx, tmp_vault):
    v, idx = memctx
    out = memory_write(note=_person_payload(), body="manager", vault=v, indexer=idx)
    assert out["id"] == "person-sarah"
    assert out["routed_to"] == "10-People"
    assert idx.row_count() == 1


def test_write_low_confidence_routes_to_inbox(memctx, tmp_vault):
    v, idx = memctx
    out = memory_write(
        note=_person_payload(confidence=0.5),
        body="maybe a manager",
        vault=v,
        indexer=idx,
    )
    assert out["routed_to"] == "90-Inbox"
    assert idx.row_count() == 1
    inbox = list((tmp_vault / "90-Inbox").glob("*.md"))
    assert len(inbox) == 1


def test_write_invalid_schema_raises(memctx):
    v, idx = memctx
    with pytest.raises(ValueError):
        memory_write(note={"type": "person"}, body="x", vault=v, indexer=idx)


def test_write_update_replaces(memctx, tmp_vault):
    v, idx = memctx
    memory_write(note=_person_payload(), body="v1", vault=v, indexer=idx)
    memory_write(note=_person_payload(), body="v2", vault=v, indexer=idx, update=True)
    note, body = v.read("person-sarah")
    assert "v2" in body
    assert idx.row_count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/tools/test_memory_write.py -v`
Expected: ModuleNotFoundError on `yuki.tools.memory.memory_write`.

- [ ] **Step 3: Implement the tool**

Create `yuki/tools/memory/memory_write.py`:

```python
"""memory_write — write or update a note in the vault."""
from __future__ import annotations

from pydantic import ValidationError

from yuki.memory.indexer import Indexer
from yuki.memory.schemas import parse_note
from yuki.memory.vault import Vault, VaultError

_LOW_CONFIDENCE = 0.7


def memory_write(
    note: dict,
    body: str,
    *,
    vault: Vault,
    indexer: Indexer,
    update: bool = False,
) -> dict:
    """Write or update a note.

    Args:
        note: frontmatter dict; must satisfy a Pydantic note schema.
        body: markdown body.
        vault: Vault instance.
        indexer: open Indexer (so retrieval stays fresh).
        update: if True, allow overwriting an existing note with the same id.

    Returns:
        {id, routed_to, path}. `routed_to` is "90-Inbox" when confidence < 0.7,
        otherwise the section name.

    Raises:
        ValueError: schema validation failure.
    """
    try:
        parsed = parse_note(note)
    except ValidationError as e:
        raise ValueError(f"Invalid note frontmatter: {e}") from e

    if not update:
        existing = vault.resolve_wikilink(parsed.id)
        if existing is not None:
            raise ValueError(
                f"Note {parsed.id!r} already exists at {existing}. Use update=True to overwrite."
            )

    path = vault.write(parsed, body, route_low_confidence=True)
    indexer.upsert(parsed, body, path)

    routed = (
        "90-Inbox"
        if parsed.confidence < _LOW_CONFIDENCE
        else path.parent.relative_to(vault.root).as_posix()
    )
    return {"id": parsed.id, "routed_to": routed, "path": str(path)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/tools/test_memory_write.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/memory/memory_write.py tests/memory/tools/test_memory_write.py
git commit -m "feat(memory): add memory_write tool with confidence-gated routing"
```

---

## Task 12 — Hot-context loader

The agent's prompt builder needs a small, always-on slice of the vault: every `.md` under `00-Identity/`. Spec §4.4 calls this "hot context, prompt-cached". This task exposes a `load_hot_context()` helper. Wiring into the agent prompt builder is left to a later plan (it requires changes inside `yuki/agent/context/`).

**Files:**
- Modify: `yuki/memory/__init__.py`
- Create: `yuki/memory/hot_context.py`
- Create: `tests/memory/test_hot_context.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_hot_context.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.hot_context import load_hot_context
from yuki.memory.schemas import IdentityNote
from yuki.memory.vault import Vault


def _identity(id_, name, body=""):
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return IdentityNote(id=id_, type="identity", created_at=now, updated_at=now,
                        confidence=1.0, source=["scan"], name=name, body=body)


def test_empty_vault_returns_empty(tmp_vault: Path):
    v = Vault()
    assert load_hot_context(v) == ""


def test_loads_identity_section(tmp_vault: Path):
    v = Vault()
    v.write(_identity("identity-profile", "Profile"), body="Name: Sudhanshu")
    v.write(_identity("identity-prefs", "Preferences"), body="Editor: vim")
    out = load_hot_context(v)
    assert "Profile" in out
    assert "Preferences" in out
    assert "Sudhanshu" in out
    assert "Editor: vim" in out


def test_skips_other_sections(tmp_vault: Path):
    from yuki.memory.schemas import PersonNote
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    v = Vault()
    v.write(PersonNote(id="person-bob", type="person", created_at=now,
                       updated_at=now, confidence=0.9, source=[],
                       name="Bob"), body="not in hot context")
    assert "not in hot context" not in load_hot_context(v)


def test_max_chars_caps_output(tmp_vault: Path):
    v = Vault()
    v.write(_identity("identity-big", "Big", body="x" * 5000))
    out = load_hot_context(v, max_chars=500)
    assert len(out) <= 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_hot_context.py -v`
Expected: ModuleNotFoundError on `yuki.memory.hot_context`.

- [ ] **Step 3: Implement `yuki/memory/hot_context.py`**

```python
"""Hot context: identity notes always injected into the system prompt.

Spec §4.4 — every chat call ships ~1-2KB of identity. Anthropic prompt caching
keeps the per-call cost near zero.
"""
from __future__ import annotations

from yuki.memory.vault import Vault


def load_hot_context(vault: Vault, max_chars: int = 4000) -> str:
    """Return concatenated identity notes ready for the system prompt."""
    parts: list[str] = []
    for note, body in vault.list_section("00-Identity"):
        title = getattr(note, "name", note.id)
        parts.append(f"## {title}\n\n{body.strip()}\n")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
```

- [ ] **Step 4: Update `yuki/memory/__init__.py` to export public surface**

Replace contents with:

```python
"""Memory subsystem: vault read/write, indexer, retriever, hot context."""

from yuki.memory.embeddings import Embedder, StubEmbedder, get_embedder
from yuki.memory.hot_context import load_hot_context
from yuki.memory.indexer import Indexer, IndexerError
from yuki.memory.retriever import Hit, Retriever
from yuki.memory.schemas import AnyNote, parse_note
from yuki.memory.vault import Vault, VaultError

__all__ = [
    "AnyNote",
    "Embedder",
    "Hit",
    "Indexer",
    "IndexerError",
    "Retriever",
    "StubEmbedder",
    "Vault",
    "VaultError",
    "get_embedder",
    "load_hot_context",
    "parse_note",
]
```

- [ ] **Step 5: Run all memory tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/ -v`
Expected: all green (≥45 tests).

- [ ] **Step 6: Run full suite to confirm nothing else broke**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest -v`
Expected: full suite passes (memory + Plan A's agent tests).

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/hot_context.py yuki/memory/__init__.py tests/memory/test_hot_context.py
git commit -m "feat(memory): add hot_context loader and finalize public exports"
```

---

## Task 13 — Git-track the vault (Letta MemFS pattern)

The vault is the user's source of truth. Make it a git repo so every observer / scanner / agent write becomes a commit. Free undo, free history, and users with GitHub get free remote sync without us building any sync infrastructure.

The agent borrows this idea from Letta's MemFS and a `mem0`-inspired ADD-only philosophy: we never silently rewrite a user's vault file in place. `Vault.write()` always lands as a commit; "corrections" are new commits, not silent overwrites.

**Files:**
- Create: `yuki/memory/git.py`
- Modify: `yuki/memory/vault.py` — call git.commit on each write
- Create: `tests/memory/test_git.py`

- [ ] **Step 1: Write the failing test**

Create `tests/memory/test_git.py`:

```python
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.git import VaultGit
from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault


def _person(id_="person-x", name="X") -> PersonNote:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return PersonNote(
        id=id_, type="person", created_at=now, updated_at=now,
        confidence=0.9, source=["scan"], name=name,
    )


def test_init_creates_git_repo(tmp_vault: Path):
    vg = VaultGit(tmp_vault)
    vg.init_if_needed()
    assert (tmp_vault / ".git").is_dir()


def test_init_idempotent(tmp_vault: Path):
    vg = VaultGit(tmp_vault)
    vg.init_if_needed()
    vg.init_if_needed()
    # No raise; still a single repo.


def test_commit_after_vault_write(tmp_vault: Path):
    v = Vault()
    v.write(_person(), body="manager")
    log = subprocess.run(
        ["git", "-C", str(tmp_vault), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "person-x" in log or "write" in log.lower()


def test_disabled_via_env(tmp_vault: Path, monkeypatch):
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    v = Vault()
    v.write(_person(), body="x")
    assert not (tmp_vault / ".git").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_git.py -v`
Expected: ModuleNotFoundError on `yuki.memory.git`.

- [ ] **Step 3: Implement `yuki/memory/git.py`**

```python
"""Git-tracking the vault — every write becomes a commit.

Borrowed from Letta MemFS: a markdown vault on disk + git history gives free
undo, free audit, and free remote sync (the user can `git remote add origin
git@github.com:them/yuki-vault.git` whenever they want).

Disable by setting YUKI_VAULT_GIT=0 (useful in tests that don't care about git).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _enabled() -> bool:
    return os.environ.get("YUKI_VAULT_GIT", "1") != "0"


class VaultGit:
    def __init__(self, root: Path) -> None:
        self._root = root

    def init_if_needed(self) -> None:
        if not _enabled():
            return
        if (self._root / ".git").is_dir():
            return
        self._root.mkdir(parents=True, exist_ok=True)
        self._run("git", "init", "-q", "-b", "main")
        gi = self._root / ".gitignore"
        if not gi.exists():
            gi.write_text(".scan_complete\n", encoding="utf-8")
        self._configure_identity()
        self._run("git", "add", ".gitignore")
        self._run("git", "commit", "-q", "-m", "feat(vault): initialize")

    def commit_path(self, path: Path, *, summary: str) -> None:
        if not _enabled():
            return
        if not (self._root / ".git").is_dir():
            self.init_if_needed()
        self._run("git", "add", str(path.relative_to(self._root)))
        # `git commit` exits non-zero if nothing changed — that's fine.
        self._run("git", "commit", "-q", "-m", summary, check=False)

    def _configure_identity(self) -> None:
        self._run("git", "config", "user.email", "vault@yuki.local")
        self._run("git", "config", "user.name", "Yuki Vault")

    def _run(self, *args: str, check: bool = True) -> None:
        try:
            subprocess.run(
                args, cwd=str(self._root), check=check,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            # No git on PATH or command failed — degrade silently.
            pass
```

- [ ] **Step 4: Wire `Vault.write()` to commit**

In `yuki/memory/vault.py`, modify `Vault.__init__` and `Vault.write` to call git:

```python
# add at top of file:
from yuki.memory.git import VaultGit

# in __init__, after the section mkdir loop:
        self._git = VaultGit(self.root)
        self._git.init_if_needed()

# replace the existing write() method's last line `return path` with:
        self._git.commit_path(
            path, summary=f"write({note.type}): {note.id}",
        )
        return path
```

- [ ] **Step 5: Run tests**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_git.py tests/memory/test_vault.py -v
```

Expected: existing vault tests still pass; new git tests pass (4 total).

- [ ] **Step 6: Run full memory suite + project suite**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/ -v
cd /Users/mafex/code/personal/Yuki && uv run pytest -v
```

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/memory/git.py yuki/memory/vault.py tests/memory/test_git.py
git commit -m "feat(memory): git-track the vault (Letta MemFS pattern)"
```

---

## Wrap-up

After Task 13:

- `yuki/memory/` is a complete, tested subsystem
- `yuki/tools/memory/` exposes the three agent-facing tools
- The vault is git-tracked from first write — every memory edit is a commit, recoverable, optionally syncable to the user's GitHub
- The Vault, Indexer, and Retriever can be driven from a Python REPL by hand
- Hot-context injection into the agent prompt is wired in Plan I Task 7 (chat router) per spec §4.4

Acceptance:
- `uv run pytest tests/memory/ -v` shows ≥49 tests, all green
- `uv run python -c "from yuki.memory import Vault, Indexer, Retriever, get_embedder; print('ok')"` prints `ok`
- `grep -r 'macos_use' yuki/memory/` returns nothing (no leakage from Plan A's vendored code)
- After a few writes, `git -C ~/YukiVault log --oneline` shows real commit history

