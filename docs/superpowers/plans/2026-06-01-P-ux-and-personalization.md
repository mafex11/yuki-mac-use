# Command-bar UX + Personalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the command bar a real chat UI (input pinned bottom, click-outside dismiss, inline loader, task results in-thread, persistent focus) and expose/activate the dormant personalization system (memory facts API + UI, daily learner, conversational capture).

**Architecture:** Python gains a fact-oriented memory layer over the existing typed-note `Vault` and new REST endpoints under a fresh `/facts` prefix (the `/memory` prefix is already taken by search/read/write). The dormant daily learner is switched on via an app-managed LaunchAgent. The Swift command bar flips to chat-style and streams control tasks into the conversation instead of the corner HUD; a new Settings "Memory" tab plus `/remember` `/forget` `/memory` slash commands and an inline "remember this?" affordance feed one store.

**Tech Stack:** FastAPI over UDS, Pydantic note schemas, the existing `Vault`/`load_hot_context`/`learner` modules, `launchctl`-managed LaunchAgent, SwiftUI/AppKit (NSPanel, @FocusState, NSEvent monitor), bundled python-build-standalone interpreter.

---

## Key constraints discovered during exploration (read before starting)

1. **`/memory` prefix is already used** by `yuki/backend/routers/memory.py` (search/read/write tools). New fact-CRUD endpoints use prefix **`/facts`** to avoid collision.
2. **Notes are strongly-typed Pydantic models** (`yuki/memory/schemas.py`). `PersonNote` requires `name`, `ProjectNote` requires `status`, `AppNote` requires `bundle_id`. Free-text facts can only safely become **`IdentityNote`** (fields: `id`, `type`, `name`, `body`, `confidence`, `source`, `created_at`, `updated_at`). So `add_fact` writes IdentityNotes; `list_facts` *reads* all four personalization sections for display.
3. **`Vault.write` / `memory_write`** build notes from a frontmatter dict via `parse_note`. `IdentityNote.id` must be a lowercase kebab-case slug (`_SLUG_RE = ^[a-z0-9][a-z0-9-]*$`).
4. **Backend test harness:** `tests/backend/conftest.py` provides a `client` fixture (TestClient, auth header set, tmp vault via `YUKI_VAULT_DIR`). Use it for endpoint tests.
5. **`get_runtime()`** exposes `.vault` (Vault) and `.indexer` (Indexer). Endpoints fetch via `get_runtime()`.
6. **Commits: NO Claude attribution, no Co-Authored-By** (repo convention).
7. Run Python tests with `uv run pytest <path> -q -p no:unraisableexception` (the `no:unraisableexception` suppresses benign socket/loop teardown warnings seen in this repo).
8. Swift is verified with `( cd app && swift build -c release )` — SourceKit "cannot find X in scope" diagnostics for same-module symbols are stale-index false positives; the build is the source of truth.

---

## File Structure

**Python — new:**
- `yuki/memory/fact_store.py` — fact view over `Vault`: `list_facts()`, `add_identity_fact()`, `delete_fact()`.
- `yuki/backend/routers/facts.py` — `/facts` CRUD + `/facts/settings` toggles.
- `tests/memory/test_fact_store.py`, `tests/backend/test_router_facts.py`.

**Python — modified:**
- `yuki/backend/appstate.py` — add `learner_enabled`, `ask_before_remember` defaults.
- `yuki/backend/server.py` — register `facts.router`.
- `yuki/backend/routers/chat.py` — `/chat` reply emits optional `capture_suggestion`.

**Swift — new:**
- `app/Yuki/LaunchAgentManager.swift` — install/remove the learner LaunchAgent.

**Swift — modified:**
- `app/Yuki/Backend.swift` — fact + settings calls, in-bar control streaming.
- `app/Yuki/CommandBar.swift` — chat-style layout, click-outside, inline loader, slash commands, capture affordance, persistent focus.
- `app/Yuki/Settings.swift` — new Memory tab.

---

## PHASE 1 — Python backend (memory facts, settings, capture)

### Task 1: appstate toggles

**Files:**
- Modify: `yuki/backend/appstate.py:20-27` (the `_DEFAULTS` dict)
- Test: `tests/backend/test_appstate_toggles.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_appstate_toggles.py
"""appstate gains learner_enabled + ask_before_remember defaults."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.backend import appstate


def test_new_toggle_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    cfg = appstate.load()
    assert cfg["learner_enabled"] is True
    assert cfg["ask_before_remember"] is True


def test_toggles_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    cfg = appstate.load()
    cfg["learner_enabled"] = False
    appstate.save(cfg)
    assert appstate.load()["learner_enabled"] is False
    # untouched toggle keeps its default
    assert appstate.load()["ask_before_remember"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backend/test_appstate_toggles.py -q -p no:unraisableexception`
Expected: FAIL with `KeyError: 'learner_enabled'`

- [ ] **Step 3: Add the defaults**

In `yuki/backend/appstate.py`, change the `_DEFAULTS` dict to include the two new keys:

```python
_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "llm_provider": "google",
    "llm_model": "gemini-2.5-flash",
    "hud_corner": "top-right",
    "hotkey": "cmd+shift+a",
    "launch_at_login": False,
    "learner_enabled": True,
    "ask_before_remember": True,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backend/test_appstate_toggles.py -q -p no:unraisableexception`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/backend/appstate.py tests/backend/test_appstate_toggles.py
git commit -m "feat(appstate): add learner_enabled + ask_before_remember toggles"
```

---

### Task 2: fact_store — list facts

**Files:**
- Create: `yuki/memory/fact_store.py`
- Test: `tests/memory/test_fact_store.py` (create)

Background: `Vault.list_section(section)` returns `list[tuple[AnyNote, str]]` (note, body). The `tmp_vault` fixture (in `tests/conftest.py`) sets `YUKI_VAULT_DIR` to a temp dir and is auto-applied by being named as a test arg.

- [ ] **Step 1: Write the failing test**

```python
# tests/memory/test_fact_store.py
"""fact_store: flat fact view over the vault's personalization sections."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.memory import fact_store
from yuki.memory.schemas import IdentityNote, PersonNote
from yuki.memory.vault import Vault


def _identity(id_: str, name: str, body: str) -> IdentityNote:
    now = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    return IdentityNote(
        id=id_, type="identity", created_at=now, updated_at=now,
        confidence=0.9, source=["user"], name=name, body=body,
    )


def _person(id_: str, name: str) -> PersonNote:
    now = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    return PersonNote(
        id=id_, type="person", created_at=now, updated_at=now,
        confidence=0.9, source=["user"], name=name,
    )


def test_list_facts_groups_by_section(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_identity("builds-mac-apps", "builds mac apps",
                      "Builds native Mac apps; prefers concise answers."), body="")
    v.write(_person("person-saran", "Saran"), body="Friend on WhatsApp.")

    facts = fact_store.list_facts(v)

    ids = {f["id"] for f in facts}
    assert "builds-mac-apps" in ids
    assert "person-saran" in ids
    identity = next(f for f in facts if f["id"] == "builds-mac-apps")
    assert identity["section"] == "identity"
    person = next(f for f in facts if f["id"] == "person-saran")
    assert person["section"] == "people"
    # each fact has display text
    assert identity["text"]
    assert person["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/memory/test_fact_store.py -q -p no:unraisableexception`
Expected: FAIL with `ModuleNotFoundError: No module named 'yuki.memory.fact_store'`

- [ ] **Step 3: Create fact_store with list_facts**

```python
# yuki/memory/fact_store.py
"""Fact-oriented view over the vault's personalization sections.

The vault stores strongly-typed notes; this module flattens the four
user-facing personalization sections into simple {id, section, title, text}
"facts" for the Memory UI and slash commands. Writing is limited to free-text
IdentityNotes (see add_identity_fact) because the other note types have
required structured fields the UI doesn't collect.
"""

from __future__ import annotations

from typing import Any, TypedDict

from yuki.memory.schemas import AnyNote
from yuki.memory.vault import Vault

# vault section dir -> stable UI key
_SECTION_KEYS: dict[str, str] = {
    "00-Identity": "identity",
    "10-People": "people",
    "20-Projects": "projects",
    "40-Apps": "apps",
}


class Fact(TypedDict):
    id: str
    section: str
    title: str
    text: str


def _display_text(note: AnyNote, body: str) -> str:
    """Human-readable one-liner for a note."""
    body = (body or "").strip()
    if body:
        return body
    # Fall back to a structured summary when there's no body.
    name = getattr(note, "name", note.id)
    extra = getattr(note, "value", None) or getattr(note, "role", None) or ""
    return f"{name} — {extra}".strip(" —") or name


def list_facts(vault: Vault) -> list[Fact]:
    """All personalization facts across Identity/People/Projects/Apps."""
    out: list[Fact] = []
    for section, key in _SECTION_KEYS.items():
        for note, body in vault.list_section(section):
            title = getattr(note, "name", note.id)
            out.append(
                Fact(id=note.id, section=key, title=title,
                     text=_display_text(note, body))
            )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/memory/test_fact_store.py -q -p no:unraisableexception`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/memory/fact_store.py tests/memory/test_fact_store.py
git commit -m "feat(memory): fact_store.list_facts over personalization sections"
```

---

### Task 3: fact_store — add + delete

**Files:**
- Modify: `yuki/memory/fact_store.py`
- Test: `tests/memory/test_fact_store.py` (add cases)

Background: `IdentityNote.id` must match `^[a-z0-9][a-z0-9-]*$`. Build the id from the text via `vault.slugify` then lowercase + fallback. `Vault.write` returns the path; we don't need the indexer here (list reads the filesystem).

- [ ] **Step 1: Write the failing tests (append to the file)**

```python
def test_add_identity_fact_then_listed(tmp_vault: Path) -> None:
    v = Vault()
    fact = fact_store.add_identity_fact(v, "I prefer dark mode everywhere")
    assert fact["section"] == "identity"
    assert fact["text"] == "I prefer dark mode everywhere"
    listed = fact_store.list_facts(v)
    assert any(f["id"] == fact["id"] for f in listed)


def test_add_identity_fact_slug_is_valid(tmp_vault: Path) -> None:
    v = Vault()
    fact = fact_store.add_identity_fact(v, "Uses Linear for tickets!!!")
    # id is a lowercase kebab slug
    assert fact["id"]
    assert fact["id"] == fact["id"].lower()
    assert " " not in fact["id"]


def test_add_two_identical_texts_no_collision(tmp_vault: Path) -> None:
    v = Vault()
    a = fact_store.add_identity_fact(v, "Same text")
    b = fact_store.add_identity_fact(v, "Same text")
    assert a["id"] != b["id"]
    assert len(fact_store.list_facts(v)) == 2


def test_delete_fact_removes_it(tmp_vault: Path) -> None:
    v = Vault()
    fact = fact_store.add_identity_fact(v, "Delete me")
    assert fact_store.delete_fact(v, fact["id"]) is True
    assert all(f["id"] != fact["id"] for f in fact_store.list_facts(v))


def test_delete_missing_fact_returns_false(tmp_vault: Path) -> None:
    v = Vault()
    assert fact_store.delete_fact(v, "does-not-exist") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/memory/test_fact_store.py -q -p no:unraisableexception`
Expected: FAIL with `AttributeError: module 'yuki.memory.fact_store' has no attribute 'add_identity_fact'`

- [ ] **Step 3: Implement add + delete**

Add these imports and functions to `yuki/memory/fact_store.py`:

```python
# add to imports at top
from datetime import UTC, datetime

from yuki.memory.schemas import IdentityNote
from yuki.memory.vault import slugify
```

```python
# append to the module

def _unique_id(vault: Vault, base: str) -> str:
    """A valid, collision-free kebab-case id derived from base text."""
    slug = slugify(base).lower() or "fact"
    slug = slug[:48].strip("-") or "fact"
    if vault.resolve_wikilink(slug) is None:
        return slug
    n = 2
    while vault.resolve_wikilink(f"{slug}-{n}") is not None:
        n += 1
    return f"{slug}-{n}"


def add_identity_fact(vault: Vault, text: str) -> Fact:
    """Write a free-text fact as an IdentityNote. Text lives in the body."""
    text = text.strip()
    now = datetime.now(UTC)
    note = IdentityNote(
        id=_unique_id(vault, text),
        type="identity",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["user"],
        name=text[:60] or "fact",
        body=text,
    )
    vault.write(note, body=text)
    return Fact(id=note.id, section="identity", title=note.name, text=text)


def delete_fact(vault: Vault, fact_id: str) -> bool:
    """Remove a fact's note by id. Returns False if not found."""
    path = vault.resolve_wikilink(fact_id)
    if path is None:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
```

Note: `datetime.now(UTC)` is fine in production code; only the Workflow-script sandbox forbids it. Tests pin time via fixtures, not here.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/memory/test_fact_store.py -q -p no:unraisableexception`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/memory/fact_store.py tests/memory/test_fact_store.py
git commit -m "feat(memory): fact_store add_identity_fact + delete_fact"
```

---

### Task 4: facts router — CRUD endpoints

**Files:**
- Create: `yuki/backend/routers/facts.py`
- Modify: `yuki/backend/server.py` (register router)
- Test: `tests/backend/test_router_facts.py` (create)

Background: the existing `/memory` prefix is taken; use `/facts`. Endpoints fetch the vault via `get_runtime().vault`. The `client` fixture already authenticates and points at a temp vault.

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_router_facts.py
"""/facts CRUD endpoints over fact_store."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_add_then_list_fact(client: TestClient) -> None:
    r = client.post("/facts", json={"text": "I use Linear for tickets"})
    assert r.status_code == 200
    created = r.json()
    assert created["section"] == "identity"
    fid = created["id"]

    r2 = client.get("/facts")
    assert r2.status_code == 200
    facts = r2.json()["facts"]
    assert any(f["id"] == fid for f in facts)


def test_add_empty_text_rejected(client: TestClient) -> None:
    r = client.post("/facts", json={"text": "   "})
    assert r.status_code == 400


def test_delete_fact(client: TestClient) -> None:
    fid = client.post("/facts", json={"text": "Delete me"}).json()["id"]
    r = client.delete(f"/facts/{fid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    facts = client.get("/facts").json()["facts"]
    assert all(f["id"] != fid for f in facts)


def test_delete_missing_returns_404(client: TestClient) -> None:
    r = client.delete("/facts/nope-not-here")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/backend/test_router_facts.py -q -p no:unraisableexception`
Expected: FAIL — `ImportError`/`ModuleNotFoundError` for `yuki.backend.routers.facts` (server import in conftest fails). This confirms the router doesn't exist yet.

- [ ] **Step 3: Create the router**

```python
# yuki/backend/routers/facts.py
"""/facts — flat CRUD over the vault's personalization facts (Memory UI).

Distinct from /memory (search/read/write of arbitrary typed notes). Writing a
fact creates a free-text IdentityNote; listing spans Identity/People/Projects/
Apps so the UI shows everything Yuki knows.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from yuki.backend.runtime import get_runtime
from yuki.memory import fact_store

router = APIRouter(prefix="/facts", tags=["facts"])


class AddFact(BaseModel):
    text: str


@router.get("")
def list_facts() -> dict[str, Any]:
    rt = get_runtime()
    return {"facts": fact_store.list_facts(rt.vault)}


@router.post("")
def add_fact(req: AddFact) -> dict[str, Any]:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="empty fact text")
    rt = get_runtime()
    return dict(fact_store.add_identity_fact(rt.vault, req.text))


@router.delete("/{fact_id}")
def delete_fact(fact_id: str) -> dict[str, Any]:
    rt = get_runtime()
    if not fact_store.delete_fact(rt.vault, fact_id):
        raise HTTPException(status_code=404, detail="fact not found")
    return {"ok": True}
```

- [ ] **Step 4: Register the router in server.py**

In `yuki/backend/server.py`, add `facts` to the routers import tuple and include it with auth. Change the import block:

```python
    from yuki.backend.routers import (
        chat,
        facts,
        health,
        memory,
        provider,
        route,
        safety,
        scan,
        settings,
        tools,
        triggers,
    )
```

And add the include line next to the other `require_token` includes:

```python
    app.include_router(facts.router, dependencies=[Depends(require_token)])
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/backend/test_router_facts.py -q -p no:unraisableexception`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add yuki/backend/routers/facts.py yuki/backend/server.py tests/backend/test_router_facts.py
git commit -m "feat(backend): /facts CRUD endpoints for personalization facts"
```

---

### Task 5: facts settings endpoints (toggles)

**Files:**
- Modify: `yuki/backend/routers/facts.py`
- Test: `tests/backend/test_router_facts.py` (add cases)

Background: toggles live in `app_state.json` via `appstate.load()/save()` (Task 1 added the defaults). The `client` fixture's tmp vault dir is also used for app support? No — `appstate` uses `YUKI_APP_SUPPORT`. The `client` fixture does not set it, so it would touch the real `~/Library/Application Support/Yuki`. To keep the test hermetic, the test sets `YUKI_APP_SUPPORT` via monkeypatch BEFORE the client builds. Add a dedicated fixture in the test file.

- [ ] **Step 1: Write the failing test (add to test_router_facts.py)**

```python
import pytest
from pathlib import Path
from collections.abc import Iterator

from yuki.backend.auth import generate_token, set_active_token
from yuki.backend.runtime import reset_runtime
from yuki.backend.server import create_app


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Like `client`, but also isolates appstate (YUKI_APP_SUPPORT)."""
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path / "appsupport"))
    reset_runtime()
    token = generate_token()
    set_active_token(token)
    c = TestClient(create_app())
    c.headers.update({"Authorization": f"Bearer {token}"})
    with c:
        yield c
    reset_runtime()


def test_get_settings_defaults(app_client: TestClient) -> None:
    r = app_client.get("/facts/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["learner_enabled"] is True
    assert body["ask_before_remember"] is True


def test_post_settings_persists(app_client: TestClient) -> None:
    r = app_client.post("/facts/settings", json={"learner_enabled": False})
    assert r.status_code == 200
    assert r.json()["learner_enabled"] is False
    # round-trips
    assert app_client.get("/facts/settings").json()["learner_enabled"] is False
    # untouched toggle unchanged
    assert app_client.get("/facts/settings").json()["ask_before_remember"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/backend/test_router_facts.py -q -p no:unraisableexception`
Expected: FAIL — 404 on `/facts/settings` (route not defined).

- [ ] **Step 3: Add settings endpoints to facts.py**

Add to `yuki/backend/routers/facts.py`:

```python
# add import
from yuki.backend import appstate
```

```python
class FactSettings(BaseModel):
    learner_enabled: bool | None = None
    ask_before_remember: bool | None = None


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    cfg = appstate.load()
    return {
        "learner_enabled": bool(cfg.get("learner_enabled", True)),
        "ask_before_remember": bool(cfg.get("ask_before_remember", True)),
    }


@router.post("/settings")
def set_settings(req: FactSettings) -> dict[str, Any]:
    cfg = appstate.load()
    if req.learner_enabled is not None:
        cfg["learner_enabled"] = req.learner_enabled
    if req.ask_before_remember is not None:
        cfg["ask_before_remember"] = req.ask_before_remember
    appstate.save(cfg)
    return {
        "learner_enabled": bool(cfg["learner_enabled"]),
        "ask_before_remember": bool(cfg["ask_before_remember"]),
    }
```

**Route-order note:** FastAPI matches `/facts/settings` against `/facts/{fact_id}` if the latter is declared first. Declare the `/settings` GET and POST **above** the `DELETE /{fact_id}` route in the file, OR rely on the fact that GET/POST vs DELETE differ by method (they do — `/settings` is GET/POST, `/{fact_id}` is DELETE, so no collision). No reorder needed; the methods disambiguate.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/backend/test_router_facts.py -q -p no:unraisableexception`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/backend/routers/facts.py tests/backend/test_router_facts.py
git commit -m "feat(backend): /facts/settings get+post for learner toggles"
```

---

### Task 6: chat reply emits capture_suggestion

**Files:**
- Modify: `yuki/backend/routers/chat.py` (the `_stream_chat` function + `_BASE_SYSTEM_PROMPT`)
- Test: `tests/backend/test_chat_capture.py` (create)

Background: the chat reply's final `done` event currently carries `content`, `ctx_badge`, `ctx_percent`. Add an optional `capture_suggestion` (string or null). To avoid a second LLM call, instruct the model to optionally append a machine-readable tag at the very end of its reply: `<remember>fact text</remember>`. The endpoint strips the tag from the user-visible `content` and surfaces the inner text as `capture_suggestion`. This is deterministic parsing, fully testable by stubbing the LLM.

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_chat_capture.py
"""/chat surfaces a capture_suggestion parsed from a <remember> tag."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yuki.backend.auth import generate_token, set_active_token
from yuki.backend.runtime import reset_runtime
from yuki.backend.server import create_app


class _FakeEvent:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    model_name = "fake"
    provider = "fake"

    async def ainvoke(self, messages, tools):  # noqa: ANN001
        return _FakeEvent("Noted! <remember>User uses Linear for tickets</remember>")


@pytest.fixture
def chat_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path / "appsupport"))
    monkeypatch.setattr("yuki.providers.factory.make_llm", lambda *a, **k: _FakeLLM())
    reset_runtime()
    token = generate_token()
    set_active_token(token)
    c = TestClient(create_app())
    c.headers.update({"Authorization": f"Bearer {token}"})
    with c:
        yield c
    reset_runtime()


def _final_done(resp_text: str) -> dict:
    done = None
    for line in resp_text.splitlines():
        if line.startswith("data:"):
            ev = json.loads(line[len("data:"):].strip())
            if ev.get("type") == "done":
                done = ev
    assert done is not None, "no done event"
    return done


def test_capture_suggestion_parsed(chat_client: TestClient) -> None:
    r = chat_client.post("/chat", json={"message": "I use Linear for tickets"})
    assert r.status_code == 200
    done = _final_done(r.text)
    assert done["capture_suggestion"] == "User uses Linear for tickets"
    # the tag is stripped from the visible reply
    assert "<remember>" not in done["content"]
    assert done["content"].strip() == "Noted!"


def test_no_tag_means_null_suggestion(chat_client: TestClient, monkeypatch) -> None:
    class _Plain(_FakeLLM):
        async def ainvoke(self, messages, tools):  # noqa: ANN001
            return _FakeEvent("Just a normal answer.")

    monkeypatch.setattr("yuki.providers.factory.make_llm", lambda *a, **k: _Plain())
    r = chat_client.post("/chat", json={"message": "what's 2+2"})
    done = _final_done(r.text)
    assert done["capture_suggestion"] is None
    assert done["content"].strip() == "Just a normal answer."
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/backend/test_chat_capture.py -q -p no:unraisableexception`
Expected: FAIL — `KeyError: 'capture_suggestion'`.

- [ ] **Step 3: Implement tag parsing in _stream_chat**

In `yuki/backend/routers/chat.py`, first extend `_BASE_SYSTEM_PROMPT` to ask for the tag:

```python
_BASE_SYSTEM_PROMPT = (
    "You are Yuki, a helpful macOS-resident assistant. "
    "Reply directly and concisely. If the user asks a factual question, "
    "answer it. If they ask you to do something on their Mac, tell them to "
    "use /chat/control instead — that surface has accessibility access. "
    "If the user states a durable personal fact about themselves, their "
    "tools, people, or projects (e.g. 'I always use Linear for tickets'), "
    "append it ONCE at the very end of your reply as "
    "<remember>the fact, rephrased concisely</remember>. Only for genuine, "
    "lasting facts — never for questions, chit-chat, or one-off requests."
)
```

Add a module-level parser near the top of the file (after imports):

```python
import re as _re

_REMEMBER_RE = _re.compile(r"<remember>(.*?)</remember>", _re.IGNORECASE | _re.DOTALL)


def _split_capture(text: str) -> tuple[str, str | None]:
    """Return (visible_text, capture_suggestion|None), stripping the tag."""
    m = _REMEMBER_RE.search(text)
    if not m:
        return text, None
    suggestion = m.group(1).strip() or None
    visible = _REMEMBER_RE.sub("", text).strip()
    return visible, suggestion
```

In `_stream_chat`, after `text = getattr(result, "content", None) or ""`, split it and use the visible text for history + the final event:

```python
    text = getattr(result, "content", None) or ""
    visible, capture = _split_capture(text)
    text = visible
```

Then add the field to the `final` dict:

```python
    final = {
        "type": "done",
        "content": text,
        "ctx_badge": tracker.badge(),
        "ctx_percent": int(tracker.percent_used),
        "capture_suggestion": capture,
    }
```

(Note: `append_history` should persist the visible `text`, which it already does since we reassigned `text` before the append. Verify the append uses `text`.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/backend/test_chat_capture.py -q -p no:unraisableexception`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the chat regression suite**

Run: `uv run pytest tests/backend/ -q -p no:unraisableexception -k "chat or facts or appstate"`
Expected: PASS (all selected)

- [ ] **Step 6: Commit**

```bash
git add yuki/backend/routers/chat.py tests/backend/test_chat_capture.py
git commit -m "feat(chat): emit capture_suggestion via <remember> tag parsing"
```

---

## PHASE 2 — Swift app

Swift UI has no unit-test harness in this project; verification is `swift build -c release` (compiles) plus manual QA on the live app (the project's established workflow). Each Swift task's "test" step is a build + a specific manual-QA checklist.

### Task 7: LaunchAgentManager (turn on the daily learner)

**Files:**
- Create: `app/Yuki/LaunchAgentManager.swift`

Background: the learner runs `python3 -m yuki.feedback.cli` with the bundled interpreter + `PYTHONPATH` (mirrors `BackendController.swift`). The plist must be generated at runtime because the bundle path is install-location dependent. Label `com.yuki.feedback.learner` (already in the cask `zap` list). Runs daily at 03:00 via `StartCalendarInterval`.

- [ ] **Step 1: Create the manager**

```swift
// app/Yuki/LaunchAgentManager.swift
import Foundation

/// Installs/removes the daily-learner LaunchAgent. The learner distills
/// recorded task episodes into reusable app-notes; it's gated by the
/// "Daily learning" toggle in Settings.
enum LaunchAgentManager {
    static let label = "com.yuki.feedback.learner"

    private static var plistURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/\(label).plist")
    }

    /// Bundled interpreter + site-packages, matching BackendController.
    private static func pythonAndEnv() -> (python: String, pythonPath: String)? {
        guard let res = Bundle.main.resourceURL else { return nil }
        let python = res.appendingPathComponent("python/bin/python3").path
        guard FileManager.default.fileExists(atPath: python) else { return nil }
        let site = res
            .appendingPathComponent("python/lib/python3.12/site-packages").path
        return (python, site)
    }

    static func enable() {
        guard let (python, site) = pythonAndEnv() else {
            NSLog("learner: no bundled python; skipping LaunchAgent install")
            return
        }
        let plist: [String: Any] = [
            "Label": label,
            "ProgramArguments": [python, "-m", "yuki.feedback.cli"],
            "EnvironmentVariables": ["PYTHONPATH": site],
            "StartCalendarInterval": ["Hour": 3, "Minute": 0],
            "RunAtLoad": false,
            "StandardErrorPath": FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/Yuki/learner.log").path,
        ]
        do {
            try FileManager.default.createDirectory(
                at: plistURL.deletingLastPathComponent(),
                withIntermediateDirectories: true)
            let data = try PropertyListSerialization.data(
                fromPropertyList: plist, format: .xml, options: 0)
            try data.write(to: plistURL)
            run(["launchctl", "unload", plistURL.path])  // idempotent
            run(["launchctl", "load", plistURL.path])
        } catch {
            NSLog("learner: failed to install LaunchAgent: \(error)")
        }
    }

    static func disable() {
        run(["launchctl", "unload", plistURL.path])
        try? FileManager.default.removeItem(at: plistURL)
    }

    /// Reconcile install state with the desired toggle at launch.
    static func reconcile(enabled: Bool) {
        if enabled { enable() } else { disable() }
    }

    @discardableResult
    private static func run(_ args: [String]) -> Int32 {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = ["-c", args.map { "'\($0)'" }.joined(separator: " ")]
        do { try p.run(); p.waitUntilExit(); return p.terminationStatus }
        catch { return -1 }
    }
}
```

- [ ] **Step 2: Build**

Run: `( cd app && swift build -c release ) 2>&1 | tail -5`
Expected: `Build complete!`

- [ ] **Step 3: Commit**

```bash
git add app/Yuki/LaunchAgentManager.swift
git commit -m "feat(app): LaunchAgentManager for the daily learner"
```

---

### Task 8: Backend.swift — fact + settings methods + in-bar control stream

**Files:**
- Modify: `app/Yuki/Backend.swift`

Background: reuse the existing `client` (UDSClient). JSON via `JSONSerialization`. The control stream method mirrors `runControl` but forwards events to a caller-supplied closure AND keeps HUD updates.

- [ ] **Step 1: Add the methods**

Add to the `Backend` class in `app/Yuki/Backend.swift`:

```swift
    // MARK: - memory facts

    struct Fact: Identifiable { let id: String; let section: String; let title: String; let text: String }

    func facts() async -> [Fact] {
        guard let data = try? await client.getJSON(path: "/facts"),
              let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arr = o["facts"] as? [[String: Any]] else { return [] }
        return arr.compactMap { d in
            guard let id = d["id"] as? String else { return nil }
            return Fact(id: id,
                        section: d["section"] as? String ?? "",
                        title: d["title"] as? String ?? "",
                        text: d["text"] as? String ?? "")
        }
    }

    @discardableResult
    func addFact(_ text: String) async -> Bool {
        guard let body = try? JSONSerialization.data(withJSONObject: ["text": text])
        else { return false }
        return (try? await client.postJSON(path: "/facts", body: body)) != nil
    }

    @discardableResult
    func forgetFact(id: String) async -> Bool {
        // UDSClient has no DELETE helper; use a raw request via postJSON path?
        // Add a deleteJSON helper instead (see Step 2).
        return (try? await client.deleteJSON(path: "/facts/\(id)")) != nil
    }

    func memorySettings() async -> (learner: Bool, ask: Bool) {
        guard let data = try? await client.getJSON(path: "/facts/settings"),
              let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return (true, true) }
        return (o["learner_enabled"] as? Bool ?? true,
                o["ask_before_remember"] as? Bool ?? true)
    }

    func setMemorySettings(learner: Bool? = nil, ask: Bool? = nil) async {
        var payload: [String: Any] = [:]
        if let learner = learner { payload["learner_enabled"] = learner }
        if let ask = ask { payload["ask_before_remember"] = ask }
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return }
        _ = try? await client.postJSON(path: "/facts/settings", body: body)
    }

    // MARK: - control streamed into the command bar

    /// Run a control task, forwarding every SSE event to `onEvent` (for the
    /// bar's inline activity) while the HUD also reflects status. Resolves
    /// when the task completes.
    func runControlInBar(_ msg: String,
                         onEvent: @escaping ([String: Any]) -> Void) async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            guard let body = try? JSONSerialization.data(
                    withJSONObject: ["message": msg]) else { cont.resume(); return }
            client.streamSSE(path: "/chat/control", body: body, onEvent: { line in
                guard let d = line.data(using: .utf8),
                      let o = try? JSONSerialization.jsonObject(with: d)
                        as? [String: Any] else { return }
                Task { @MainActor in
                    HUD.shared.handle(event: o)
                    onEvent(o)
                }
            }, onDone: { cont.resume() })
        }
    }
```

- [ ] **Step 2: Add a `deleteJSON` helper to UDSClient**

In `app/Yuki/UDSClient.swift`, next to `getJSON`:

```swift
    /// Buffered DELETE returning the full response body as Data.
    func deleteJSON(path: String) async throws -> Data {
        try await sendBuffered(method: "DELETE", path: path, body: Data())
    }
```

- [ ] **Step 3: Build**

Run: `( cd app && swift build -c release ) 2>&1 | tail -5`
Expected: `Build complete!`

- [ ] **Step 4: Commit**

```bash
git add app/Yuki/Backend.swift app/Yuki/UDSClient.swift
git commit -m "feat(app): Backend fact/settings methods + in-bar control stream + DELETE helper"
```

---

### Task 9: Settings → Memory tab

**Files:**
- Modify: `app/Yuki/Settings.swift`

- [ ] **Step 1: Add the tab to SettingsView**

In `SettingsView.body`, add between Permissions and About:

```swift
            MemorySettings().tabItem { Label("Memory", systemImage: "brain.head.profile") }
```

- [ ] **Step 2: Add the MemorySettings view**

Append to `app/Yuki/Settings.swift`:

```swift
struct MemorySettings: View {
    @State private var facts: [Backend.Fact] = []
    @State private var newFact = ""
    @State private var learner = true
    @State private var ask = true
    @State private var loaded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("What Yuki knows about you").font(.headline)

            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(facts) { fact in
                        HStack(alignment: .top) {
                            Text(fact.section.uppercased())
                                .font(.caption2).foregroundStyle(.secondary)
                                .frame(width: 64, alignment: .leading)
                            Text(fact.text).font(.callout)
                            Spacer()
                            Button(role: .destructive) {
                                Task { await Backend.shared.forgetFact(id: fact.id); await reload() }
                            } label: { Image(systemName: "minus.circle") }
                                .buttonStyle(.borderless)
                        }
                    }
                    if facts.isEmpty {
                        Text("Nothing yet. Add a fact below, or just tell Yuki about yourself in chat.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .frame(maxHeight: 160)

            HStack {
                TextField("Add a fact (e.g. I use Linear for tickets)", text: $newFact)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { addFact() }
                Button("Add") { addFact() }.disabled(newFact.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            Divider()
            Toggle("Daily learning (distill tasks into reusable notes)", isOn: $learner)
                .onChange(of: learner) { on in
                    Task { await Backend.shared.setMemorySettings(learner: on) }
                    LaunchAgentManager.reconcile(enabled: on)
                }
            Toggle("Ask before remembering things from chat", isOn: $ask)
                .onChange(of: ask) { on in
                    Task { await Backend.shared.setMemorySettings(ask: on) }
                }
        }
        .padding()
        .onAppear {
            guard !loaded else { return }
            loaded = true
            Task {
                let s = await Backend.shared.memorySettings()
                learner = s.learner; ask = s.ask
                await reload()
            }
        }
    }

    private func addFact() {
        let text = newFact.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        newFact = ""
        Task { await Backend.shared.addFact(text); await reload() }
    }

    private func reload() async { facts = await Backend.shared.facts() }
}
```

- [ ] **Step 3: Build**

Run: `( cd app && swift build -c release ) 2>&1 | tail -5`
Expected: `Build complete!`

- [ ] **Step 4: Manual QA (after a release build + install, or `swift run`)**

- Open Settings → Memory: shows empty-state text.
- Add "I use Linear for tickets" → appears in the list with section IDENTITY.
- Click the minus → it disappears.
- Toggle "Daily learning" off → `~/Library/LaunchAgents/com.yuki.feedback.learner.plist` is removed (`ls` it); on → it reappears.

- [ ] **Step 5: Commit**

```bash
git add app/Yuki/Settings.swift
git commit -m "feat(app): Settings Memory tab — facts list, add, delete, toggles"
```

---

### Task 10: CommandBar — chat-style layout + bug fixes

**Files:**
- Modify: `app/Yuki/CommandBar.swift`

This task rewrites `CommandBarView` and adds click-outside dismissal to the panel. It does NOT yet add slash commands or capture (Task 11). It implements: bottom-pinned input, conversation on top, inline live-activity line, control tasks streaming into the conversation, persistent focus, click-outside dismiss.

- [ ] **Step 1: Add click-outside dismissal to CommandBar**

In `app/Yuki/CommandBar.swift`, add a click monitor to the `CommandBar` class. Add a stored property and install/remove it in `toggle()`/`close()`:

```swift
    private var clickMonitor: Any?

    private func installClickMonitor() {
        guard clickMonitor == nil else { return }
        clickMonitor = NSEvent.addGlobalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            // A click landed in ANOTHER app → dismiss.
            self?.close()
        }
    }

    private func removeClickMonitor() {
        if let m = clickMonitor { NSEvent.removeMonitor(m); clickMonitor = nil }
    }
```

In `toggle()`, after `panel?.makeKeyAndOrderFront(nil)` (the show branch), call `installClickMonitor()`. In the hide branch (`p.orderOut(nil)`) and in `close()`, call `removeClickMonitor()`.

Note: a global monitor fires only for clicks in *other* apps; clicks inside Yuki's own panel don't trigger it. That's exactly the desired behavior (click outside → close; click inside → stay). Esc still closes via `KeyablePanel.cancelOperation`.

- [ ] **Step 2: Rewrite CommandBarView**

Replace the entire `struct CommandBarView` with:

```swift
struct CommandBarView: View {
    @State private var input = ""
    @State private var history: [Turn] = []
    @State private var liveActivity: String? = nil   // transient "working on it" line
    @State private var ctxBadge = ""
    @State private var busy = false
    @FocusState private var inputFocused: Bool

    struct Turn: Identifiable {
        let id = UUID()
        let role: String   // "human" | "ai" | "error"
        let text: String
    }

    private static let verbMap: [String: String] = [
        "app_tool": "Switching app", "click_tool": "Clicking",
        "type_tool": "Typing", "shortcut_tool": "Pressing keys",
        "shell_tool": "Running", "scroll_tool": "Scrolling",
        "scrape_tool": "Reading screen", "wait_tool": "Waiting",
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Conversation on top, scrolls, newest at bottom.
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(history) { turn in
                            Text(turn.role == "human" ? "❯ \(turn.text)" : turn.text)
                                .font(.callout)
                                .textSelection(.enabled)
                                .foregroundStyle(color(for: turn.role))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id(turn.id)
                        }
                        if let activity = liveActivity {
                            HStack(spacing: 8) {
                                ProgressView().controlSize(.small)
                                Text(activity).font(.callout).foregroundStyle(.blue)
                            }
                            .id("live")
                        }
                    }
                    .padding(16)
                }
                .onChange(of: history.count) { _ in scrollToEnd(proxy) }
                .onChange(of: liveActivity) { _ in scrollToEnd(proxy) }
            }

            Divider()

            // Input pinned at the bottom.
            HStack(spacing: 8) {
                Text("❯").foregroundStyle(.blue).font(.title3)
                TextField("Ask Yuki…", text: $input)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .disabled(busy)
                    .focused($inputFocused)
                    .onSubmit { submit() }
                Text(ctxBadge).font(.caption2).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.regularMaterial)
        }
        .frame(width: 720, height: 420)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .onAppear { loadStatus(); inputFocused = true }
        .onReceive(NotificationCenter.default.publisher(
            for: CommandBar.focusRequest)) { _ in inputFocused = true }
    }

    private func color(for role: String) -> Color {
        switch role {
        case "human": return .secondary
        case "error": return .red
        default: return .primary
        }
    }

    private func scrollToEnd(_ proxy: ScrollViewProxy) {
        withAnimation {
            if liveActivity != nil { proxy.scrollTo("live", anchor: .bottom) }
            else if let last = history.last { proxy.scrollTo(last.id, anchor: .bottom) }
        }
    }

    private func submit() {
        let msg = input.trimmingCharacters(in: .whitespaces)
        guard !msg.isEmpty, !busy else { return }
        input = ""
        if msg == "/clear" { runClear(); return }
        if msg == "/compact" { runCompact(); return }
        history.append(Turn(role: "human", text: msg))
        Task { await route(msg) }
    }

    private func route(_ msg: String) async {
        busy = true
        let decision = await Backend.shared.route(msg)
        if decision == "control" {
            liveActivity = "Working on it…"
            await Backend.shared.runControlInBar(msg) { ev in
                let type = ev["type"] as? String
                if type == "tool_call" {
                    let tool = ev["tool_name"] as? String ?? ""
                    liveActivity = "Working on it — \(Self.verbMap[tool] ?? tool)…"
                } else if type == "done" {
                    let content = ev["content"] as? String ?? "Done."
                    history.append(Turn(role: "ai", text: content))
                    liveActivity = nil
                } else if type == "error" {
                    let content = ev["content"] as? String ?? "Failed."
                    history.append(Turn(role: "error", text: content))
                    liveActivity = nil
                }
            }
            liveActivity = nil
        } else {
            liveActivity = "Thinking…"
            let (reply, badge) = await Backend.shared.chat(msg)
            history.append(Turn(role: "ai", text: reply))
            ctxBadge = badge
            liveActivity = nil
        }
        busy = false
        inputFocused = true   // persistent focus after every response
    }

    private func loadStatus() {
        Task { ctxBadge = await Backend.shared.status().badge }
    }

    private func runClear() {
        Task {
            _ = await Backend.shared.clear()
            history = []
            ctxBadge = await Backend.shared.status().badge
            inputFocused = true
        }
    }

    private func runCompact() {
        Task { ctxBadge = await Backend.shared.compact(); inputFocused = true }
    }
}
```

- [ ] **Step 3: Build**

Run: `( cd app && swift build -c release ) 2>&1 | tail -5`
Expected: `Build complete!`

- [ ] **Step 4: Manual QA**

- ⌘⇧A opens; input is focused immediately (type without clicking).
- Ask a question → "Thinking…" shows in-thread, reply appears, input stays focused (no re-click).
- Give a control task ("open notes") → bar STAYS OPEN, "Working on it — Switching app…" updates in place, final result lands in the conversation.
- Click another app → bar dismisses. Esc also dismisses.

- [ ] **Step 5: Commit**

```bash
git add app/Yuki/CommandBar.swift
git commit -m "feat(app): chat-style command bar — bottom input, in-thread results, click-outside, persistent focus"
```

---

### Task 11: Slash commands + conversational capture affordance

**Files:**
- Modify: `app/Yuki/CommandBar.swift`

Background: `chat()` currently returns `(reply, badge)`. To surface `capture_suggestion`, extend `Backend.chat` to also return it, then render an inline "Remember this?" affordance gated by the ask toggle.

- [ ] **Step 1: Extend Backend.chat to return capture_suggestion**

In `app/Yuki/Backend.swift`, change `chat(_:)` to also capture the suggestion. Update the return tuple and the `done` parsing:

```swift
    func chat(_ msg: String) async -> (reply: String, badge: String, capture: String?) {
        var reply = ""
        var badge = ""
        var capture: String? = nil
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            guard let body = try? JSONSerialization.data(
                    withJSONObject: ["message": msg]) else { cont.resume(); return }
            client.streamSSE(path: "/chat", body: body, onEvent: { line in
                guard let d = line.data(using: .utf8),
                      let o = try? JSONSerialization.jsonObject(with: d)
                        as? [String: Any] else { return }
                let type = o["type"] as? String
                if type == "done" {
                    reply = o["content"] as? String ?? ""
                    badge = o["ctx_badge"] as? String ?? ""
                    capture = o["capture_suggestion"] as? String
                } else if type == "error" {
                    reply = "[error] " + (o["content"] as? String ?? "")
                }
            }, onDone: { cont.resume() })
        }
        return (reply, badge, capture)
    }
```

(Any other caller of `chat` — search the app — must be updated to the 3-tuple. As of this plan only `CommandBarView.route` calls it.)

- [ ] **Step 2: Add capture state + affordance to CommandBarView**

Add state: `@State private var pendingCapture: String? = nil` and `@State private var askBeforeRemember = true`.

Load the toggle in `onAppear` (extend `loadStatus` or add a call):

```swift
        .onAppear {
            loadStatus(); inputFocused = true
            Task { askBeforeRemember = await Backend.shared.memorySettings().ask }
        }
```

Update the chat branch in `route` to capture the suggestion:

```swift
            let (reply, badge, capture) = await Backend.shared.chat(msg)
            history.append(Turn(role: "ai", text: reply))
            ctxBadge = badge
            liveActivity = nil
            if askBeforeRemember, let capture = capture, !capture.isEmpty {
                pendingCapture = capture
            }
```

Render the affordance above the Divider (after the conversation `ScrollViewReader`'s closing brace, before `Divider()`):

```swift
            if let capture = pendingCapture {
                HStack(spacing: 8) {
                    Text("Remember: \(capture)").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button("Yes") {
                        Task { await Backend.shared.addFact(capture); pendingCapture = nil }
                    }.controlSize(.small)
                    Button("No") { pendingCapture = nil }.controlSize(.small)
                }
                .padding(.horizontal, 16).padding(.bottom, 8)
            }
```

- [ ] **Step 3: Add /memory, /remember, /forget to submit()**

In `submit()`, after the `/compact` line, add:

```swift
        if msg == "/memory" { runMemoryList(); return }
        if msg.hasPrefix("/remember ") {
            let fact = String(msg.dropFirst("/remember ".count))
            history.append(Turn(role: "human", text: msg))
            Task { await Backend.shared.addFact(fact)
                   history.append(Turn(role: "ai", text: "Got it — I'll remember that."))
                   inputFocused = true }
            return
        }
        if msg == "/forget" { runMemoryList(forForget: true); return }
        if msg.hasPrefix("/forget ") {
            let id = String(msg.dropFirst("/forget ".count)).trimmingCharacters(in: .whitespaces)
            Task { _ = await Backend.shared.forgetFact(id: id)
                   history.append(Turn(role: "ai", text: "Forgotten."))
                   inputFocused = true }
            return
        }
```

Add the helper:

```swift
    private func runMemoryList(forForget: Bool = false) {
        Task {
            let facts = await Backend.shared.facts()
            if facts.isEmpty {
                history.append(Turn(role: "ai", text: "I don't know anything about you yet. Tell me, or use /remember <fact>."))
            } else {
                let lines = facts.map { f in
                    forForget ? "• [\(f.id)] \(f.text)" : "• \(f.text) (\(f.section))"
                }.joined(separator: "\n")
                let hint = forForget ? "\n\nRemove one with: /forget <id>" : ""
                history.append(Turn(role: "ai", text: "What I know:\n\(lines)\(hint)"))
            }
            inputFocused = true
        }
    }
```

- [ ] **Step 4: Build**

Run: `( cd app && swift build -c release ) 2>&1 | tail -5`
Expected: `Build complete!`

- [ ] **Step 5: Manual QA**

- `/memory` → lists facts (or empty hint).
- `/remember I use Arc browser` → "Got it"; then `/memory` shows it.
- `/forget` → lists with ids; `/forget <id>` → "Forgotten"; `/memory` confirms gone.
- Say "I always use Linear for tickets" in chat → reply appears + "Remember: …? [Yes][No]". Yes → `/memory` shows it. (Toggle off "ask before remembering" in Settings → the prompt no longer appears.)

- [ ] **Step 6: Commit**

```bash
git add app/Yuki/CommandBar.swift app/Yuki/Backend.swift
git commit -m "feat(app): slash commands (/memory /remember /forget) + remember-this affordance"
```

---

### Task 12: Wire learner reconcile at launch + final full-suite run

**Files:**
- Modify: `app/Yuki/YukiApp.swift`

- [ ] **Step 1: Reconcile the learner on launch**

In `app/Yuki/YukiApp.swift`, inside `applicationDidFinishLaunching`, after `backend.start()` succeeds (in the existing `Task`), reconcile the LaunchAgent from the backend's saved toggle:

```swift
                let settings = await Backend.shared.memorySettings()
                LaunchAgentManager.reconcile(enabled: settings.learner)
```

Place it right after the `pushKey` calls already there.

- [ ] **Step 2: Build**

Run: `( cd app && swift build -c release ) 2>&1 | tail -5`
Expected: `Build complete!`

- [ ] **Step 3: Full Python suite (regression gate)**

Run: `uv run pytest tests/ -q -p no:unraisableexception`
Expected: all pass except the 2 known pre-existing `test_factory.py` failures (real Google key in login Keychain — documented, unrelated). If any OTHER test fails, fix before committing.

- [ ] **Step 4: Commit**

```bash
git add app/Yuki/YukiApp.swift
git commit -m "feat(app): reconcile daily-learner LaunchAgent from saved toggle at launch"
```

---

## Final verification (after all tasks)

- [ ] `( cd app && swift build -c release )` → Build complete.
- [ ] `uv run pytest tests/ -q -p no:unraisableexception` → only the 2 known factory failures.
- [ ] `./release.sh 0.1.1` → build a fresh signed bundle (bump version so `brew upgrade` picks it up; the signing + tccutil steps are already in release.sh/cask from Plan-prior work).
- [ ] Manual end-to-end on the installed app: command-bar chat + control + memory tab + slash commands + capture + learner toggle flips the plist.
- [ ] Ship: `gh release upload`/`create`, update cask sha256, push tap (rebase onto origin first).

## Out of scope (deferred)

- Mac-observation daemon (its own spec).
- Notarization.
- Expandable step-log in the conversation (option B).


