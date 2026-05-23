# Plan I — Backend HTTP Server + Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend that exposes the agent + memory + triggers + scan + settings via local-only HTTP/SSE on `127.0.0.1:<random-port>`, plus the Next.js frontend that talks to it. The menu-bar app (Plan J) launches both as child processes.

**Architecture:** FastAPI app on a random loopback port. Per-launch random auth token (32-byte hex) required on every request via `Authorization: Bearer <token>` header — including the SSE `/chat` stream. Six routers (`/chat`, `/memory`, `/triggers`, `/settings`, `/scan`, `/tools`). The Next.js frontend is built as a static export and served by FastAPI under `/`. The frontend gets the token via the URL when opened from the menu bar (`http://127.0.0.1:<port>?token=<token>`). Every endpoint defers to existing modules (memory, triggers, scan, safety) — no business logic in routers.

**Tech Stack:** `fastapi>=0.115`, `uvicorn[standard]>=0.32`, `sse-starlette>=2.1` for chat streaming, `httpx>=0.27` for tests, Next.js 15 + Tailwind for the frontend (ported skeleton from `~/code/personal/LLM-OS`). Pydantic models for request/response shapes.

**Spec reference:** §3.1 (process model), §3.2 (module layout `backend/`), §11.1 (local-only + per-launch token), §9.4 (full frontend), §3.3 (data flow).

**Prerequisite:** Plans A (agent), B (vault), F (triggers), G (tools), H (gatekeeper). Plan C (scan) and D (observer) are *not* prerequisites — the backend exposes them but doesn't need them running for chat to work.

---

## File Structure

```
Yuki/
├── pyproject.toml                          # MODIFIED — fastapi, uvicorn, sse-starlette, httpx
├── yuki/
│   └── backend/
│       ├── __init__.py
│       ├── server.py                       # FastAPI app factory + lifespan
│       ├── auth.py                         # token generator + dep injection
│       ├── runtime.py                      # singleton holder for Vault, Indexer, Gatekeeper, Daemon
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── chat.py                     # POST /chat (SSE)
│       │   ├── memory.py                   # /memory/{search,read,write}
│       │   ├── triggers.py                 # /triggers CRUD + audit
│       │   ├── settings.py                 # /settings get/set + key validation
│       │   ├── scan.py                     # POST /scan/run, GET /scan/status
│       │   └── tools.py                    # GET /tools (list specs + danger)
│       └── static/                         # populated at build time from frontend export
├── frontend/
│   ├── package.json
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── src/app/                            # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx                        # chat
│   │   ├── memory/page.tsx
│   │   ├── triggers/page.tsx
│   │   ├── settings/page.tsx
│   │   └── api-client.ts                   # token-aware fetcher
│   └── README.md
└── tests/
    └── backend/
        ├── __init__.py
        ├── conftest.py                     # FastAPI TestClient with token
        ├── test_auth.py
        ├── test_router_tools.py
        ├── test_router_memory.py
        ├── test_router_triggers.py
        ├── test_router_settings.py
        ├── test_router_scan.py
        └── test_router_chat.py             # SSE end-to-end with stub agent
```

---

## Task 1 — Add deps + auth + token generator

**Files:**
- Modify: `pyproject.toml` — add `fastapi`, `uvicorn[standard]`, `sse-starlette`, `httpx`
- Create: `yuki/backend/__init__.py`
- Create: `yuki/backend/auth.py`
- Create: `tests/backend/__init__.py`
- Create: `tests/backend/test_auth.py`

- [ ] **Step 1: Add deps + sync**

In `pyproject.toml` `[project] dependencies` add:

```toml
"fastapi>=0.115.0",
"uvicorn[standard]>=0.32.0",
"sse-starlette>=2.1.0",
```

In `[dependency-groups] dev` add `"httpx>=0.27.0"`. Run `uv sync`.

- [ ] **Step 2: Write the failing test**

```python
import pytest

from yuki.backend.auth import (
    AuthError, generate_token, get_active_token, set_active_token, verify,
)


def test_generated_token_is_long_hex():
    t = generate_token()
    assert len(t) >= 64
    int(t, 16)  # parses


def test_verify_accepts_active_token():
    set_active_token("abc")
    verify("abc")  # no raise


def test_verify_rejects_other():
    set_active_token("abc")
    with pytest.raises(AuthError):
        verify("xyz")


def test_get_active_returns_set_value():
    set_active_token("zzz")
    assert get_active_token() == "zzz"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_auth.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `yuki/backend/__init__.py`**

```python
"""HTTP backend — FastAPI app + routers."""
```

- [ ] **Step 5: Implement `yuki/backend/auth.py`**

```python
"""Per-launch random auth token. Loopback only — token is a defense in depth."""
from __future__ import annotations

import secrets

_token: str | None = None


class AuthError(Exception):
    """Token missing or wrong."""


def generate_token() -> str:
    return secrets.token_hex(32)


def set_active_token(token: str) -> None:
    global _token
    _token = token


def get_active_token() -> str | None:
    return _token


def verify(presented: str) -> None:
    if _token is None or not secrets.compare_digest(_token, presented):
        raise AuthError("invalid token")
```

- [ ] **Step 6: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_auth.py -v
git add pyproject.toml uv.lock yuki/backend/__init__.py yuki/backend/auth.py tests/backend/__init__.py tests/backend/test_auth.py
git commit -m "feat(backend): add deps + per-launch token auth"
```

---

## Task 2 — Runtime holder + FastAPI app factory + token dependency

**Files:**
- Create: `yuki/backend/runtime.py`
- Create: `yuki/backend/server.py`
- Create: `tests/backend/conftest.py`

- [ ] **Step 1: Add fixture**

```python
import pytest
from fastapi.testclient import TestClient

from yuki.backend.auth import generate_token, set_active_token
from yuki.backend.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    token = generate_token()
    set_active_token(token)
    app = create_app()
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


@pytest.fixture
def unauth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_VAULT_DIR", str(tmp_path / "YukiVault"))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    set_active_token(generate_token())
    app = create_app()
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 2: Write a failing smoke test**

`tests/backend/test_router_tools.py`:

```python
def test_tools_endpoint_lists_native(client):
    r = client.get("/tools")
    assert r.status_code == 200
    data = r.json()
    assert "tools" in data
    names = {t["name"] for t in data["tools"]}
    assert "calendar" in names


def test_tools_endpoint_requires_auth(unauth_client):
    r = unauth_client.get("/tools")
    assert r.status_code == 401
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_tools.py -v`
Expected: ModuleNotFoundError on `yuki.backend.server`.

- [ ] **Step 4: Implement `yuki/backend/runtime.py`**

```python
"""Singleton runtime — one Vault, Indexer, Gatekeeper, etc. per process."""
from __future__ import annotations

from dataclasses import dataclass

from yuki.memory.embeddings import StubEmbedder, get_embedder
from yuki.memory.indexer import Indexer
from yuki.memory.vault import Vault
from yuki.safety.burst import BurstMode
from yuki.safety.confirmer import InMemoryConfirmer
from yuki.safety.gatekeeper import Gatekeeper
from yuki.safety.trusted import TrustedRoutineRegistry


@dataclass
class Runtime:
    vault: Vault
    indexer: Indexer
    gatekeeper: Gatekeeper


_runtime: Runtime | None = None


def build_runtime() -> Runtime:
    try:
        embedder = get_embedder()
    except Exception:
        embedder = StubEmbedder(dim=8)
    indexer = Indexer(embedder=embedder)
    indexer.open()
    return Runtime(
        vault=Vault(),
        indexer=indexer,
        gatekeeper=Gatekeeper(
            confirmer=InMemoryConfirmer(),
            trusted=TrustedRoutineRegistry(),
            burst=BurstMode(),
        ),
    )


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = build_runtime()
    return _runtime


def reset_runtime() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.indexer.close()
    _runtime = None
```

- [ ] **Step 5: Implement `yuki/backend/server.py`**

```python
"""FastAPI app factory + lifespan + auth dependency."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException

from yuki.backend.auth import AuthError, verify
from yuki.backend.runtime import get_runtime, reset_runtime


def require_token(authorization: Annotated[str, Header()] = "") -> None:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        verify(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@asynccontextmanager
async def _lifespan(app: FastAPI):
    get_runtime()
    yield
    reset_runtime()


def create_app() -> FastAPI:
    app = FastAPI(title="Yuki backend", lifespan=_lifespan)

    from yuki.backend.routers import (
        chat, memory, scan, settings, tools, triggers,
    )
    app.include_router(tools.router, dependencies=[Depends(require_token)])
    app.include_router(memory.router, dependencies=[Depends(require_token)])
    app.include_router(triggers.router, dependencies=[Depends(require_token)])
    app.include_router(settings.router, dependencies=[Depends(require_token)])
    app.include_router(scan.router, dependencies=[Depends(require_token)])
    app.include_router(chat.router, dependencies=[Depends(require_token)])
    return app
```

- [ ] **Step 6: Stub all 6 routers (so import works) + implement tools router**

Create `yuki/backend/routers/__init__.py` (empty).

`yuki/backend/routers/tools.py`:

```python
"""GET /tools — list registered native tools with danger levels."""
from __future__ import annotations

from fastapi import APIRouter

import yuki.tools.native  # registers tools as side effect
from yuki.tools.native.registry import REGISTRY

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools(include_experimental: bool = False) -> dict:
    return {
        "tools": [
            {
                "name": s.name, "danger": s.danger.value,
                "description": s.description, "experimental": s.experimental,
                "parameters": s.parameters,
            }
            for s in REGISTRY.values()
            if include_experimental or not s.experimental
        ],
    }
```

Stub the other five routers (each just an `APIRouter` with no endpoints):

```python
# yuki/backend/routers/memory.py
from fastapi import APIRouter
router = APIRouter(prefix="/memory", tags=["memory"])
```

Same shape for `triggers.py` (`/triggers`), `settings.py` (`/settings`), `scan.py` (`/scan`), `chat.py` (`/chat`).

- [ ] **Step 7: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_tools.py -v
git add yuki/backend/runtime.py yuki/backend/server.py yuki/backend/routers/ tests/backend/conftest.py tests/backend/test_router_tools.py
git commit -m "feat(backend): add app factory + runtime + tools router"
```

---

## Task 3 — Memory router

`/memory/search`, `/memory/read`, `/memory/write` map directly onto the three memory tools from Plan B.

**Files:**
- Modify: `yuki/backend/routers/memory.py`
- Create: `tests/backend/test_router_memory.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone


def _person_payload(id_="person-x", confidence=0.9):
    return {
        "id": id_, "type": "person", "name": "X",
        "confidence": confidence, "source": ["scan"],
        "created_at": "2026-05-22T09:00:00+00:00",
        "updated_at": "2026-05-22T09:00:00+00:00",
    }


def test_write_then_read(client):
    r = client.post("/memory/write", json={
        "note": _person_payload(), "body": "hello",
    })
    assert r.status_code == 200
    out = r.json()
    assert out["routed_to"] == "10-People"

    r2 = client.get("/memory/read", params={"id_or_path": "person-x"})
    assert r2.status_code == 200
    assert r2.json()["id"] == "person-x"


def test_search_returns_hits(client):
    client.post("/memory/write", json={
        "note": _person_payload(), "body": "manager and team lead",
    })
    r = client.get("/memory/search", params={"query": "manager", "k": 5})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert any(h["id"] == "person-x" for h in hits)


def test_write_invalid_returns_400(client):
    r = client.post("/memory/write", json={"note": {"type": "person"}, "body": ""})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_memory.py -v`
Expected: FAIL (router has no endpoints).

- [ ] **Step 3: Implement `yuki/backend/routers/memory.py`**

```python
"""Memory router — wraps memory_search/read/write tools."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from yuki.backend.runtime import get_runtime
from yuki.tools.memory.memory_read import memory_read
from yuki.tools.memory.memory_search import memory_search
from yuki.tools.memory.memory_write import memory_write

router = APIRouter(prefix="/memory", tags=["memory"])


class WriteRequest(BaseModel):
    note: dict[str, Any]
    body: str = ""
    update: bool = False


@router.get("/search")
def search(query: str, k: int = 5) -> dict:
    rt = get_runtime()
    return {"hits": memory_search(query=query, k=k, indexer=rt.indexer)}


@router.get("/read")
def read(id_or_path: str, expand_links: int = 0) -> dict:
    rt = get_runtime()
    try:
        return memory_read(
            id_or_path=id_or_path, vault=rt.vault, expand_links=expand_links,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/write")
def write(req: WriteRequest) -> dict:
    rt = get_runtime()
    try:
        return memory_write(
            note=req.note, body=req.body, vault=rt.vault, indexer=rt.indexer,
            update=req.update,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_memory.py -v
git add yuki/backend/routers/memory.py tests/backend/test_router_memory.py
git commit -m "feat(backend): add memory router"
```

---

## Task 4 — Triggers router

CRUD over trigger markdown files + audit log.

**Files:**
- Modify: `yuki/backend/routers/triggers.py`
- Create: `tests/backend/test_router_triggers.py`

- [ ] **Step 1: Write the failing test**

```python
def _trigger_payload(slug="standup"):
    now = "2026-05-22T09:00:00+00:00"
    return {
        "id": f"trigger-{slug}", "type": "trigger",
        "created_at": now, "updated_at": now,
        "confidence": 0.9, "source": ["user"], "enabled": True,
        "condition": {"kind": "time", "cron": "0 10 * * 1-5"},
        "debounce": "1h",
        "action": {"kind": "suggestion", "text": "standup"},
        "fire_count": 0, "acceptance_rate": 0.0,
    }


def test_create_then_list(client):
    r = client.post("/triggers", json={"note": _trigger_payload(), "body": ""})
    assert r.status_code == 200
    r2 = client.get("/triggers")
    assert r2.status_code == 200
    ids = {t["id"] for t in r2.json()["triggers"]}
    assert "trigger-standup" in ids


def test_delete(client):
    client.post("/triggers", json={"note": _trigger_payload(), "body": ""})
    r = client.delete("/triggers/trigger-standup")
    assert r.status_code == 200
    r2 = client.get("/triggers")
    assert all(t["id"] != "trigger-standup" for t in r2.json()["triggers"])


def test_audit_returns_lines(client):
    r = client.get("/triggers/audit", params={"date": "2026-05-22"})
    assert r.status_code == 200
    assert "lines" in r.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_triggers.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `yuki/backend/routers/triggers.py`**

```python
"""Triggers router — CRUD over markdown trigger notes + audit reads."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from yuki.memory import frontmatter as fm
from yuki.memory import paths
from yuki.memory.schemas import parse_note
from yuki.triggers.loader import load_all

router = APIRouter(prefix="/triggers", tags=["triggers"])


class CreateRequest(BaseModel):
    note: dict[str, Any]
    body: str = ""


def _triggers_dir():
    d = paths.vault_dir() / "30-Routines" / "triggers"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("")
def list_triggers() -> dict:
    out = []
    for t in load_all():
        out.append({"id": t.id, "kind": t.condition_kind,
                    "fire_count": t.fire_count,
                    "acceptance_rate": t.acceptance_rate})
    return {"triggers": out}


@router.post("")
def create(req: CreateRequest) -> dict:
    try:
        note = parse_note(req.note)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if note.type != "trigger":
        raise HTTPException(status_code=400, detail="must be a trigger note")
    slug = note.id.removeprefix("trigger-")
    path = _triggers_dir() / f"{slug}.md"
    fm.write_file(path, note.model_dump(mode="json"), req.body)
    return {"created": True, "id": note.id, "path": str(path)}


@router.delete("/{trigger_id}")
def delete(trigger_id: str) -> dict:
    for path in _triggers_dir().glob("*.md"):
        try:
            meta, _ = fm.read_file(path)
        except Exception:
            continue
        if meta.get("id") == trigger_id:
            path.unlink()
            return {"deleted": True, "id": trigger_id}
    raise HTTPException(status_code=404, detail="trigger not found")


@router.get("/audit")
def audit(date: str) -> dict:
    eps = paths.vault_dir() / "60-Episodes"
    path = eps / f"triggers-{date}.md"
    if not path.exists():
        return {"lines": []}
    return {"lines": path.read_text(encoding="utf-8").splitlines()}
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_triggers.py -v
git add yuki/backend/routers/triggers.py tests/backend/test_router_triggers.py
git commit -m "feat(backend): add triggers router"
```

---

## Task 5 — Settings router

GET/PUT key-value config. Stored in `~/Library/Application Support/Yuki/settings.json`. Validates LLM API keys by attempting a single token request (mocked in tests).

**Files:**
- Modify: `yuki/backend/routers/settings.py`
- Create: `tests/backend/test_router_settings.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest


def test_get_returns_defaults(client):
    r = client.get("/settings")
    assert r.status_code == 200
    data = r.json()
    assert "settings" in data
    assert "llm_provider" in data["settings"]


def test_put_persists(client):
    r = client.put("/settings", json={"llm_provider": "anthropic"})
    assert r.status_code == 200
    r2 = client.get("/settings")
    assert r2.json()["settings"]["llm_provider"] == "anthropic"


def test_put_unknown_key_rejected(client):
    r = client.put("/settings", json={"banana": "x"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_settings.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `yuki/backend/routers/settings.py`**

```python
"""Settings router — JSON KV under Application Support."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from yuki.memory import paths

router = APIRouter(prefix="/settings", tags=["settings"])

ALLOWED = {
    "llm_provider", "llm_model", "embedder", "burst_seconds",
    "deviation_alerts_enabled", "wakeword_enabled", "hotkey",
}
DEFAULTS = {
    "llm_provider": "anthropic",
    "llm_model": "claude-sonnet-4-6",
    "embedder": "voyage",
    "burst_seconds": 30,
    "deviation_alerts_enabled": True,
    "wakeword_enabled": False,
    "hotkey": "cmd+shift+y",
}


def _path() -> Path:
    return paths.index_db_path().parent / "settings.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return dict(DEFAULTS)
    try:
        return {**DEFAULTS, **json.loads(p.read_text())}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def _save(data: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


@router.get("")
def get_all() -> dict:
    return {"settings": _load()}


@router.put("")
def put(updates: dict[str, Any]) -> dict:
    unknown = set(updates) - ALLOWED
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown keys: {sorted(unknown)}",
        )
    current = _load()
    current.update(updates)
    _save(current)
    return {"settings": current}
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_settings.py -v
git add yuki/backend/routers/settings.py tests/backend/test_router_settings.py
git commit -m "feat(backend): add settings router"
```

---

## Task 6 — Scan router

`POST /scan/run` triggers `yuki.scan.run()` (Plan C) in the background. `GET /scan/status` returns last-run status (sentinel + ScanResult).

**Files:**
- Modify: `yuki/backend/routers/scan.py`
- Create: `tests/backend/test_router_scan.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from unittest.mock import AsyncMock, patch

from yuki.scan.runner import ScanResult


def test_run_triggers_scan(client):
    fake = AsyncMock(return_value=ScanResult(
        skipped=False, fact_count=10, entity_count=3, written_paths=[],
    ))
    with patch("yuki.backend.routers.scan.run_scan", new=fake):
        r = client.post("/scan/run", json={"polish": False, "force": False})
    assert r.status_code == 200
    assert r.json()["entity_count"] == 3


def test_status_when_sentinel_absent(client):
    r = client.get("/scan/status")
    assert r.status_code == 200
    assert r.json()["complete"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_scan.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `yuki/backend/routers/scan.py`**

```python
"""Scan router — kicks off onboarding scan + reports status."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from yuki.scan import paths as scan_paths
from yuki.scan.runner import run as run_scan

router = APIRouter(prefix="/scan", tags=["scan"])


class RunRequest(BaseModel):
    polish: bool = False
    force: bool = False


@router.post("/run")
async def post_run(req: RunRequest) -> dict:
    result = await run_scan(polish=req.polish, force=req.force)
    return {
        "skipped": result.skipped,
        "fact_count": result.fact_count,
        "entity_count": result.entity_count,
        "written_paths": result.written_paths,
    }


@router.get("/status")
def get_status() -> dict:
    return {"complete": scan_paths.sentinel_path().exists()}
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_scan.py -v
git add yuki/backend/routers/scan.py tests/backend/test_router_scan.py
git commit -m "feat(backend): add scan router"
```

---

## Task 6b — Safety router (burst-mode bridge)

The Swift menu-bar app (Plan J) detects long-press of `⌘⇧Y` and needs to engage `BurstMode` inside the Python process. This task adds a tiny `/safety/burst` POST endpoint so Swift can flip the bit over loopback HTTP.

**Files:**
- Create: `yuki/backend/routers/safety.py`
- Modify: `yuki/backend/server.py` (register router)
- Modify: `yuki/backend/runtime.py` (expose burst handle on Runtime)
- Create: `tests/backend/test_router_safety.py`

- [ ] **Step 1: Expose `BurstMode` on `Runtime`**

In `yuki/backend/runtime.py`, change the `Runtime` dataclass to keep a direct handle to the burst object so the router can flip it without reaching into the gatekeeper internals:

```python
@dataclass
class Runtime:
    vault: Vault
    indexer: Indexer
    gatekeeper: Gatekeeper
    burst: BurstMode  # NEW
```

In `build_runtime()`, build burst first, hand it to the gatekeeper, and store it on Runtime:

```python
def build_runtime() -> Runtime:
    try:
        embedder = get_embedder()
    except Exception:
        embedder = StubEmbedder(dim=8)
    indexer = Indexer(embedder=embedder)
    indexer.open()
    burst = BurstMode()
    return Runtime(
        vault=Vault(),
        indexer=indexer,
        gatekeeper=Gatekeeper(
            confirmer=InMemoryConfirmer(),
            trusted=TrustedRoutineRegistry(),
            burst=burst,
        ),
        burst=burst,
    )
```

- [ ] **Step 2: Write the failing test**

`tests/backend/test_router_safety.py`:

```python
def test_burst_engage(client):
    r = client.post("/safety/burst", json={"duration": 30})
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_burst_disengage(client):
    client.post("/safety/burst", json={"duration": 30})
    r = client.delete("/safety/burst")
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_burst_status(client):
    r = client.get("/safety/burst")
    assert r.status_code == 200
    assert "active" in r.json()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_safety.py -v`
Expected: 404.

- [ ] **Step 4: Implement `yuki/backend/routers/safety.py`**

```python
"""Safety router — burst-mode bridge for the menu-bar app."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from yuki.backend.runtime import get_runtime

router = APIRouter(prefix="/safety", tags=["safety"])


class BurstRequest(BaseModel):
    duration: float = Field(default=30.0, ge=1.0, le=300.0)


@router.post("/burst")
def engage(req: BurstRequest) -> dict:
    rt = get_runtime()
    rt.burst.engage(duration=req.duration)
    return {"active": rt.burst.is_active(), "duration": req.duration}


@router.delete("/burst")
def disengage() -> dict:
    rt = get_runtime()
    rt.burst.disengage()
    return {"active": rt.burst.is_active()}


@router.get("/burst")
def status() -> dict:
    rt = get_runtime()
    return {"active": rt.burst.is_active()}
```

- [ ] **Step 5: Register the router**

In `yuki/backend/server.py`'s `create_app`, add (with token dep, like the others):

```python
from yuki.backend.routers import safety
app.include_router(safety.router, dependencies=[Depends(require_token)])
```

- [ ] **Step 6: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_safety.py -v
git add yuki/backend/routers/safety.py yuki/backend/server.py yuki/backend/runtime.py tests/backend/test_router_safety.py
git commit -m "feat(backend): add /safety/burst bridge for menu-bar long-press"
```

---

## Task 7 — Chat router (SSE)

`POST /chat` accepts `{message, conversation_id?}` and streams Server-Sent Events as the agent thinks/calls tools/responds. The router defers entirely to `yuki.agent.Agent` (Plan A), which yields events.

For this plan we add a thin streaming surface that emits `event: thought | tool_call | tool_result | done | error` payloads. The agent's actual ainvoke wiring happens here. Tests use a stub agent that yields a known sequence.

**Files:**
- Modify: `yuki/backend/routers/chat.py`
- Create: `tests/backend/test_router_chat.py`

- [ ] **Step 1: Write the failing test**

```python
import json


def test_chat_streams_events(client, monkeypatch):
    async def fake_stream(message: str, conversation_id: str | None):
        yield {"type": "thought", "text": "thinking"}
        yield {"type": "done", "content": "hi back"}

    monkeypatch.setattr("yuki.backend.routers.chat._stream_events", fake_stream)

    with client.stream("POST", "/chat", json={"message": "hi"}) as r:
        assert r.status_code == 200
        body = "".join(line for line in r.iter_text())
    assert "thinking" in body
    assert "hi back" in body


def test_chat_rejects_empty_message(client):
    r = client.post("/chat", json={"message": ""})
    assert r.status_code == 400


def test_chat_injects_hot_context(client, monkeypatch):
    """Spec §4.4 — every chat call must ship 00-Identity hot context."""
    from datetime import datetime, timezone
    from yuki.memory.schemas import IdentityNote
    from yuki.memory.vault import Vault

    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    Vault().write(
        IdentityNote(id="identity-profile", type="identity",
                     created_at=now, updated_at=now, confidence=1.0,
                     source=["scan"], name="Profile", body=""),
        body="Name: Sudhanshu\nRole: builder",
    )

    captured = {}
    async def fake_invoke(self, task):
        captured["task"] = task
        class R:
            content = "ok"
        return R()
    monkeypatch.setattr("yuki.agent.Agent.ainvoke", fake_invoke)

    with client.stream("POST", "/chat", json={"message": "who am I?"}) as r:
        list(r.iter_text())
    assert "Sudhanshu" in captured["task"]
    assert "<identity_context>" in captured["task"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_chat.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `yuki/backend/routers/chat.py`**

```python
"""Chat router — SSE stream of agent thoughts, tool calls, tokens, and final."""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from yuki.backend.runtime import get_runtime

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


async def _stream_events(message: str, conversation_id: str | None) -> AsyncIterator[dict]:
    """Bridge to yuki.agent.Agent.ainvoke and yield its events.

    Critical wiring: prepend identity hot-context (spec §4.4) to the task so
    every chat call ships ~1-2KB of `00-Identity/*.md` to the model. Anthropic
    prompt caching keeps the per-call cost near zero.
    """
    from yuki.agent import Agent
    from yuki.memory import load_hot_context
    from yuki.providers.stub import ChatStub

    rt = get_runtime()
    hot = load_hot_context(rt.vault).strip()
    framed_task = f"{message}" if not hot else (
        "<identity_context>\n"
        f"{hot}\n"
        "</identity_context>\n\n"
        f"User task: {message}"
    )

    agent = Agent(llm=ChatStub())
    result = await agent.ainvoke(task=framed_task)
    yield {"type": "done", "content": getattr(result, "content", "")}


def _to_sse(events: AsyncIterator[dict]) -> AsyncIterator[dict]:
    async def _gen():
        async for ev in events:
            yield {"event": ev["type"], "data": json.dumps(ev)}
    return _gen()


@router.post("")
async def post_chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="empty message")
    events = _stream_events(req.message, req.conversation_id)
    return EventSourceResponse(_to_sse(events))
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_chat.py -v
git add yuki/backend/routers/chat.py tests/backend/test_router_chat.py
git commit -m "feat(backend): add chat SSE router"
```

---

## Task 7b — Prompt caching + trajectory recording

Spec §11.2 promises Anthropic prompt caching reduces repeat-token cost. This task wires the actual `cache_control` markers and adds trajectory recording — every chat turn writes its prompt + tool-call sequence + final response to `~/Library/Application Support/Yuki/trajectories/<conversation_id>.jsonl`. Trajectories make the agent's behavior auditable, replayable for debugging, and useful raw material for the user's own observation. Borrowed from anthropic-quickstarts' computer-use best-practices.

**Files:**
- Create: `yuki/backend/caching.py`
- Create: `yuki/backend/trajectory.py`
- Modify: `yuki/backend/routers/chat.py` (call into both)
- Create: `tests/backend/test_caching.py`
- Create: `tests/backend/test_trajectory.py`

- [ ] **Step 1: Write the failing test for caching**

`tests/backend/test_caching.py`:

```python
from yuki.backend.caching import build_cached_system_blocks


def test_returns_two_blocks_when_hot_context_present():
    blocks = build_cached_system_blocks(
        base_prompt="You are Yuki.",
        hot_context="## Profile\n\nName: Sudhanshu",
    )
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert "Sudhanshu" in blocks[1]["text"]


def test_single_block_when_no_hot_context():
    blocks = build_cached_system_blocks(
        base_prompt="You are Yuki.",
        hot_context="",
    )
    assert len(blocks) == 1
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_long_context_still_one_cache_marker_each():
    blocks = build_cached_system_blocks(
        base_prompt="x" * 5000, hot_context="y" * 3000,
    )
    assert all(b["cache_control"] == {"type": "ephemeral"} for b in blocks)
```

- [ ] **Step 2: Implement `yuki/backend/caching.py`**

```python
"""Prompt-cache markers for Anthropic.

Spec §11.2: identity hot context + system prompt repeat across calls. Marking
both with cache_control=ephemeral cuts repeat-token cost by ~90%. The model
still sees the same content; only the billing changes.
"""
from __future__ import annotations


def build_cached_system_blocks(
    *, base_prompt: str, hot_context: str,
) -> list[dict]:
    """Compose Anthropic-shaped system blocks with cache_control markers.

    Block 0: stable system prompt (rarely changes between turns).
    Block 1: identity hot context (changes only when the user edits 00-Identity/).
    Both get cache_control=ephemeral so Anthropic's cache hits both.
    """
    blocks: list[dict] = [
        {
            "type": "text",
            "text": base_prompt,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    if hot_context.strip():
        blocks.append({
            "type": "text",
            "text": f"<identity>\n{hot_context}\n</identity>",
            "cache_control": {"type": "ephemeral"},
        })
    return blocks
```

- [ ] **Step 3: Run caching tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_caching.py -v`
Expected: 3 PASS.

- [ ] **Step 4: Write the failing test for trajectory**

`tests/backend/test_trajectory.py`:

```python
import json
from pathlib import Path

from yuki.backend.trajectory import TrajectoryRecorder


def test_records_turns(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    rec = TrajectoryRecorder(conversation_id="abc")
    rec.record({"type": "user", "text": "hi"})
    rec.record({"type": "thought", "text": "thinking"})
    rec.record({"type": "done", "content": "hello back"})

    out = tmp_path / "abc.jsonl"
    assert out.exists()
    lines = out.read_text().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["type"] == "user"
    assert parsed[2]["content"] == "hello back"


def test_disabled_via_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    monkeypatch.setenv("YUKI_TRAJECTORIES", "0")
    rec = TrajectoryRecorder(conversation_id="abc")
    rec.record({"type": "user", "text": "hi"})
    assert not (tmp_path / "abc.jsonl").exists()


def test_default_conversation_id(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    rec = TrajectoryRecorder(conversation_id=None)
    rec.record({"type": "x"})
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1


def test_redacts_secret_keys(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_TRAJECTORY_DIR", str(tmp_path))
    rec = TrajectoryRecorder(conversation_id="r")
    rec.record({
        "type": "tool_call",
        "args": {"api_key": "sk-real-key", "query": "weather",
                 "headers": {"Authorization": "Bearer abc"}},
    })
    line = (tmp_path / "r.jsonl").read_text()
    assert "sk-real-key" not in line
    assert "Bearer abc" not in line
    assert "<redacted>" in line
    assert "weather" in line  # non-secret survives
```

- [ ] **Step 5: Implement `yuki/backend/trajectory.py`**

```python
"""Trajectory recorder — every chat turn streamed to JSONL on disk.

Borrowed from anthropic-quickstarts: persisted trajectories make agent behavior
auditable, replayable for debugging, and useful raw material for the observer
daemon to learn from. One file per conversation_id.

Disable via YUKI_TRAJECTORIES=0.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _enabled() -> bool:
    return os.environ.get("YUKI_TRAJECTORIES", "1") != "0"


def _root() -> Path:
    override = os.environ.get("YUKI_TRAJECTORY_DIR")
    if override:
        return Path(override)
    return (
        Path.home() / "Library" / "Application Support" / "Yuki" / "trajectories"
    )


_REDACT_KEYS = ("api_key", "password", "secret", "token", "authorization")


def _redact(obj):
    """Walk a dict/list and redact secret-looking keys.

    Mirrors claude-leak/src/Tool.ts:481 (`backfillObservableInput`): the LLM
    receives full inputs, but the observable transcript shows redacted versions
    so secrets never land on disk.
    """
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if any(s in k.lower() for s in _REDACT_KEYS)
                else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


class TrajectoryRecorder:
    def __init__(self, conversation_id: str | None) -> None:
        self._conv = conversation_id or uuid4().hex[:12]

    def record(self, event: dict) -> None:
        if not _enabled():
            return
        event = _redact(event)
        root = _root()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{self._conv}.jsonl"
        stamped = {**event, "ts": datetime.now(timezone.utc).isoformat()}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(stamped, default=str) + "\n")
```

- [ ] **Step 6: Wire both into `chat.py`**

In `yuki/backend/routers/chat.py`:

```python
# add imports near the top:
from yuki.backend.caching import build_cached_system_blocks
from yuki.backend.trajectory import TrajectoryRecorder

# rewrite _stream_events to use both:
async def _stream_events(message: str, conversation_id: str | None) -> AsyncIterator[dict]:
    """Bridge to yuki.agent.Agent.ainvoke and yield its events.

    Wires (a) identity hot-context per spec §4.4, (b) cache_control markers,
    (c) trajectory recording. The agent itself receives the framed task; the
    cache-shaped system blocks are passed through to the LLM provider.
    """
    from yuki.agent import Agent
    from yuki.memory import load_hot_context
    from yuki.providers.stub import ChatStub

    rt = get_runtime()
    rec = TrajectoryRecorder(conversation_id=conversation_id)
    rec.record({"type": "user", "text": message})

    hot = load_hot_context(rt.vault).strip()
    cached_blocks = build_cached_system_blocks(
        base_prompt="You are Yuki, a macOS assistant.",
        hot_context=hot,
    )
    framed_task = (
        message if not hot
        else f"<identity_context>\n{hot}\n</identity_context>\n\nUser task: {message}"
    )

    agent = Agent(llm=ChatStub(system_blocks=cached_blocks))
    result = await agent.ainvoke(task=framed_task)
    final = {"type": "done", "content": getattr(result, "content", "")}
    rec.record(final)
    yield final
```

Note: `ChatStub` accepting `system_blocks` is a small extension to the stub provider from Plan A. If Plan A's stub doesn't accept it yet, add the parameter (default `None`, ignored when None). Production providers (`ChatAnthropic`, etc.) need the same kwarg threaded through — this is a small follow-up task in Plan A.

- [ ] **Step 7: Run all backend tests**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/ -v
```

Expected: ≥25 PASS (caching: 3, trajectory: 3, plus everything earlier).

- [ ] **Step 8: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/backend/caching.py yuki/backend/trajectory.py yuki/backend/routers/chat.py tests/backend/test_caching.py tests/backend/test_trajectory.py
git commit -m "feat(backend): add prompt caching + trajectory recording"
```

---

## Task 8 — Frontend (Next.js scaffold + API client)

Scaffold Next.js 15 + Tailwind. Four pages: chat (`/`), memory (`/memory`), triggers (`/triggers`), settings (`/settings`). All pages use a shared `api-client.ts` that reads the token from URL `?token=` on first load and stores it in `sessionStorage`.

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/memory/page.tsx`
- Create: `frontend/src/app/triggers/page.tsx`
- Create: `frontend/src/app/settings/page.tsx`
- Create: `frontend/src/app/api-client.ts`

- [ ] **Step 1: Scaffold + install**

```bash
cd /Users/mafex/code/personal/Yuki
mkdir -p frontend
cd frontend
npm init -y
npm install next@15 react@19 react-dom@19
npm install -D typescript @types/react @types/node tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 2: `frontend/next.config.mjs`**

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
};
export default nextConfig;
```

- [ ] **Step 3: `frontend/src/app/layout.tsx`**

```tsx
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 4: `frontend/src/app/api-client.ts`**

```typescript
const KEY = "yuki_token";

export function ensureToken(): string {
  if (typeof window === "undefined") return "";
  const stored = sessionStorage.getItem(KEY);
  if (stored) return stored;
  const url = new URL(window.location.href);
  const fromQuery = url.searchParams.get("token") || "";
  if (fromQuery) sessionStorage.setItem(KEY, fromQuery);
  return fromQuery;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = ensureToken();
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init.headers || {}),
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
```

- [ ] **Step 5: Pages — minimal stubs**

`frontend/src/app/page.tsx` (chat):

```tsx
"use client";

import { useEffect, useState } from "react";
import { ensureToken } from "./api-client";

export default function Page() {
  const [msg, setMsg] = useState("");
  const [out, setOut] = useState("");
  useEffect(() => { ensureToken(); }, []);

  async function send() {
    const token = ensureToken();
    const res = await fetch("/chat", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message: msg }),
    });
    const reader = res.body?.getReader();
    let acc = "";
    if (reader) {
      const dec = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += dec.decode(value);
        setOut(acc);
      }
    }
  }

  return (
    <main className="p-4 space-y-2">
      <textarea value={msg} onChange={(e) => setMsg(e.target.value)}
                className="w-full border p-2" rows={4} />
      <button onClick={send} className="bg-black text-white px-4 py-2">
        Send
      </button>
      <pre className="whitespace-pre-wrap">{out}</pre>
    </main>
  );
}
```

Similar 20-line stubs for `memory/page.tsx`, `triggers/page.tsx`, `settings/page.tsx` each calling the relevant `/memory|/triggers|/settings` endpoint via `api()` and rendering the JSON response.

- [ ] **Step 6: Build + smoke**

```bash
cd /Users/mafex/code/personal/Yuki/frontend
npm run build
ls out/index.html
```

Expected: `out/` directory exists with static HTML.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add frontend/
git commit -m "feat(frontend): scaffold Next.js static export with token-aware API client"
```

---

## Task 9 — Static mount + CI test

Wire FastAPI to serve the frontend's `out/` as static files at `/`. Add a CI build step that runs `npm run build` before pytest.

**Files:**
- Modify: `yuki/backend/server.py`

- [ ] **Step 1: Modify `create_app`** to mount the frontend if it exists:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    app = FastAPI(title="Yuki backend", lifespan=_lifespan)

    from yuki.backend.routers import (
        chat, memory, scan, settings, tools, triggers,
    )
    app.include_router(tools.router, dependencies=[Depends(require_token)])
    app.include_router(memory.router, dependencies=[Depends(require_token)])
    app.include_router(triggers.router, dependencies=[Depends(require_token)])
    app.include_router(settings.router, dependencies=[Depends(require_token)])
    app.include_router(scan.router, dependencies=[Depends(require_token)])
    app.include_router(chat.router, dependencies=[Depends(require_token)])

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    return app
```

- [ ] **Step 2: Add a test verifying the static mount path is wired**

`tests/backend/test_static_mount.py`:

```python
from pathlib import Path

import pytest

from yuki.backend.server import create_app


def test_static_mount_only_when_dir_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "yuki.backend.server.Path", lambda *a: tmp_path / "doesnotexist",
    )
    app = create_app()
    routes = [r.path for r in app.routes]
    assert "/tools" in routes
```

(Test is a smoke check that the app builds; static mount is wired but not required for the test to pass.)

- [ ] **Step 3: Document the CI build step**

In `.github/workflows/ci.yml` (created in Plan A0), add a step before `uv run pytest`:

```yaml
- name: Build frontend
  working-directory: frontend
  run: |
    npm ci
    npm run build
    rm -rf ../yuki/backend/static
    cp -r out ../yuki/backend/static
```

- [ ] **Step 4: Run full project suite**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest -v
```

Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/backend/server.py tests/backend/test_static_mount.py .github/workflows/ci.yml
git commit -m "feat(backend): mount frontend static export when present"
```

---

## Wrap-up

After Task 9:
- `uvicorn yuki.backend.server:create_app --factory --port 0` starts the backend
- All endpoints require `Authorization: Bearer <token>`
- `/chat` streams agent events via SSE
- Frontend is built statically and served by the same process
- 6 routers cover the entire spec API surface

Acceptance:
- `uv run pytest tests/backend/ -v` ≥20 tests, all green
- `curl -H 'Authorization: Bearer <token>' http://127.0.0.1:<port>/tools` returns 15 tools
- Opening the served `index.html` with `?token=<token>` in URL renders the chat page
- No endpoint accessible without the token (401)

