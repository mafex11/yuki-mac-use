# Yuki Production Mac App — Implementation Plan (Plan O)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Yuki as a single `Yuki.app` installed via `brew install --cask`, with a Raycast-style command bar, a corner HUD that streams live agent progress, and a bundled Python backend reached over a Unix Domain Socket (no TCP port, no token, no terminal).

**Architecture:** One Swift `NSApplication` parent spawns a bundled Python child. They talk over a UDS at `~/Library/Application Support/Yuki/yuki.sock`. The agent's per-step events are bridged into the SSE stream so the HUD shows live progress. Python is bundled via `python-build-standalone`; the app ships as a `.zip` Cask.

**Tech Stack:** Swift (AppKit + SwiftUI), Python 3.12 (FastAPI + uvicorn over UDS), `python-build-standalone`, Homebrew Cask, macOS Keychain.

**Spec reference:** `docs/superpowers/specs/2026-05-31-O-production-mac-app.md`

**Phasing:** Phase A (backend, strict TDD over UDS) → Phase B (Swift, exact-code checklists, visual verification) → Phase C (packaging). Phase A must fully pass before Phase B starts.

---

## File Structure

```
Yuki/
├── yuki/
│   ├── backend/
│   │   ├── cli.py                    # MODIFIED — accept --uds, skip token on UDS
│   │   ├── server.py                 # MODIFIED — UDS-mode auth no-op
│   │   ├── auth.py                   # MODIFIED — uds_mode flag
│   │   ├── appstate.py               # NEW — read app_state.json + Keychain
│   │   ├── event_bridge.py           # NEW — QueueEventSubscriber
│   │   ├── queue.py                  # NEW — single-worker control task queue
│   │   └── routers/
│   │       ├── route.py              # NEW — POST /route classifier
│   │       └── chat.py               # MODIFIED — stream agent events; queue control
│   ├── providers/factory.py          # MODIFIED — resolve from app_state.json
│   ├── memory/paths.py               # MODIFIED — add app_support_dir(), socket_path()
│   └── migrations/
│       ├── __init__.py               # NEW — CURRENT_SCHEMA, run_migrations()
│       └── v1.py                     # NEW — no-op baseline
├── app/                              # Swift app (migrate SPM → Xcode in Task 0)
│   └── Yuki/
│       ├── UDSClient.swift           # NEW — streaming HTTP over UDS
│       ├── BackendController.swift   # MODIFIED — spawn over UDS
│       ├── CommandBar.swift          # NEW — frosted panel + history
│       ├── HUD.swift                 # NEW — corner pill + state machine
│       ├── Settings.swift            # NEW — General/Provider/Permissions/About
│       ├── FirstRun.swift            # NEW — permissions + provider onboarding
│       ├── Keychain.swift            # NEW — store/read api keys
│       ├── MenuBar.swift             # MODIFIED — spinner, reveal logs
│       └── HotKey.swift              # MODIFIED — Cmd+Shift+A, configurable
├── release.sh                        # NEW — build + bundle + release
└── tests/
    ├── backend/test_route.py         # NEW
    ├── backend/test_event_bridge.py  # NEW
    ├── backend/test_queue.py         # NEW
    ├── backend/test_appstate.py      # NEW
    └── migrations/test_migrations.py # NEW
```

---

## Phase A — Backend (Python, TDD over UDS)

### Task A1: Path helpers for app-support dir + socket

**Files:**
- Modify: `yuki/memory/paths.py`
- Test: `tests/memory/test_paths.py`

- [ ] **Step 1: Write the failing test**

`tests/memory/test_paths.py` (append):

```python
import os
from pathlib import Path
import pytest
from yuki.memory import paths


def test_app_support_dir_default(monkeypatch):
    monkeypatch.delenv("YUKI_APP_SUPPORT", raising=False)
    monkeypatch.setenv("HOME", "/Users/test")
    assert paths.app_support_dir() == Path(
        "/Users/test/Library/Application Support/Yuki"
    )


def test_app_support_dir_override(monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", "/tmp/yuki")
    assert paths.app_support_dir() == Path("/tmp/yuki")


def test_socket_path(monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", "/tmp/yuki")
    assert paths.socket_path() == Path("/tmp/yuki/yuki.sock")


def test_chat_history_path(monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", "/tmp/yuki")
    assert paths.chat_history_path() == Path("/tmp/yuki/chat_history.jsonl")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_paths.py -v -k "app_support or socket or chat_history"`
Expected: AttributeError on `paths.app_support_dir`.

- [ ] **Step 3: Implement in `yuki/memory/paths.py`**

Add after `index_db_path()`:

```python
def app_support_dir() -> Path:
    override = os.environ.get("YUKI_APP_SUPPORT")
    if override:
        return Path(override)
    return _home() / "Library" / "Application Support" / "Yuki"


def socket_path() -> Path:
    return app_support_dir() / "yuki.sock"


def chat_history_path() -> Path:
    return app_support_dir() / "chat_history.jsonl"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory/test_paths.py -v -k "app_support or socket or chat_history"`
Expected: 4 PASS.

- [ ] **Step 5: Point chat history at the new helper**

In `yuki/runtime/compaction.py`, replace the `history_path()` body:

```python
def history_path() -> Path:
    override = os.environ.get("YUKI_CHAT_HISTORY")
    if override:
        return Path(override)
    from yuki.memory import paths
    return paths.chat_history_path()
```

- [ ] **Step 6: Run full suite + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/memory tests/runtime -q
git add yuki/memory/paths.py yuki/runtime/compaction.py tests/memory/test_paths.py
git commit -m "feat(paths): app_support_dir + socket_path helpers (Plan O A1)"
```

Expected: green.

---

### Task A2: app_state.json reader + Keychain shim

**Files:**
- Create: `yuki/backend/appstate.py`
- Create: `tests/backend/test_appstate.py`

`app_state.json` holds non-secret config (provider, model, hud corner, etc.).
API keys are NOT here — they live in the macOS Keychain, read via the
`security` CLI. In tests we inject keys via env so no real Keychain is touched.

- [ ] **Step 1: Write the failing test**

`tests/backend/test_appstate.py`:

```python
import json
from pathlib import Path
import pytest
from yuki.backend import appstate


def test_returns_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    cfg = appstate.load()
    assert cfg["llm_provider"] == "google"
    assert cfg["llm_model"] == "gemini-2.5-flash"


def test_reads_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    (tmp_path / "app_state.json").write_text(
        json.dumps({"llm_provider": "anthropic", "llm_model": "claude-sonnet-4-6"})
    )
    cfg = appstate.load()
    assert cfg["llm_provider"] == "anthropic"
    assert cfg["llm_model"] == "claude-sonnet-4-6"


def test_api_key_from_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "env-key-123")
    assert appstate.api_key_for("google") == "env-key-123"


def test_api_key_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(appstate, "_keychain_get", lambda account: None)
    assert appstate.api_key_for("google") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_appstate.py -v`
Expected: ModuleNotFoundError on `yuki.backend.appstate`.

- [ ] **Step 3: Implement `yuki/backend/appstate.py`**

```python
"""app_state.json (non-secret config) + Keychain (api keys) reader.

Resolution for api keys: env var first (dev mode), then macOS Keychain
(bundled-app mode). Config (provider/model/UI prefs) lives in plaintext json
because none of it is sensitive.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from yuki.memory import paths

log = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "llm_provider": "google",
    "llm_model": "gemini-2.5-flash",
    "hud_corner": "top-right",
    "hotkey": "cmd+shift+a",
    "launch_at_login": False,
}

# Keychain account name per provider.
_KEYCHAIN_SERVICE = "com.yuki.app"
_KEY_ENV = {
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "",  # no key
}


def _path():
    return paths.app_support_dir() / "app_state.json"


def load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("app_state.json unreadable (%s); using defaults", e)
        return dict(_DEFAULTS)
    return {**_DEFAULTS, **data}


def save(cfg: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _keychain_get(account: str) -> str | None:  # pragma: no cover -- real Keychain
    try:
        out = subprocess.run(
            ["security", "find-generic-password",
             "-s", _KEYCHAIN_SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception as e:
        log.warning("keychain read failed for %s: %s", account, e)
    return None


def api_key_for(provider: str) -> str | None:
    import os
    env_name = _KEY_ENV.get(provider, "")
    if env_name:
        val = os.environ.get(env_name)
        if val:
            return val
    return _keychain_get(provider)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_appstate.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add yuki/backend/appstate.py tests/backend/test_appstate.py
git commit -m "feat(backend): app_state.json + Keychain api-key reader (Plan O A2)"
```

---

### Task A3: factory resolves from app_state.json

**Files:**
- Modify: `yuki/providers/factory.py`
- Test: `tests/providers/test_factory_appstate.py`

- [ ] **Step 1: Write the failing test**

`tests/providers/test_factory_appstate.py`:

```python
import pytest
from yuki.providers import factory


def test_resolve_reads_appstate(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.delenv("YUKI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("YUKI_LLM_MODEL", raising=False)
    (tmp_path / "app_state.json").write_text(
        '{"llm_provider": "google", "llm_model": "gemini-2.5-flash"}'
    )
    provider, model = factory._resolve(None, None)
    assert provider == "google"
    assert model == "gemini-2.5-flash"


def test_env_still_overrides_appstate(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    monkeypatch.setenv("YUKI_LLM_PROVIDER", "ollama")
    (tmp_path / "app_state.json").write_text('{"llm_provider": "google"}')
    provider, _ = factory._resolve(None, None)
    assert provider == "ollama"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/providers/test_factory_appstate.py -v`
Expected: FAIL — factory still reads only settings.json/env.

- [ ] **Step 3: Modify `_resolve` in `yuki/providers/factory.py`**

Replace the settings-loading block inside `_resolve`:

```python
    settings: dict[str, Any] = {}
    if forced_provider is None or forced_model is None:
        try:
            from yuki.backend import appstate
            settings = appstate.load()
            # Map appstate keys → the keys _resolve expects.
            settings = {
                "llm_provider": settings.get("llm_provider"),
                "llm_model": settings.get("llm_model"),
            }
        except Exception:
            settings = {}
```

Also wire api keys: in `make_llm`, before each provider branch, populate the
env from appstate if missing:

```python
    if p in ("google", "anthropic"):
        import os
        from yuki.backend import appstate
        key = appstate.api_key_for(p)
        if key:
            env_name = "GOOGLE_API_KEY" if p == "google" else "ANTHROPIC_API_KEY"
            os.environ.setdefault(env_name, key)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/providers/ -v`
Expected: green (new tests pass, existing factory tests still pass).

- [ ] **Step 5: Commit**

```bash
git add yuki/providers/factory.py tests/providers/test_factory_appstate.py
git commit -m "feat(providers): factory resolves provider/model/key from app_state.json + Keychain (Plan O A3)"
```

---

### Task A4: uvicorn over UDS + token no-op

**Files:**
- Modify: `yuki/backend/cli.py`
- Modify: `yuki/backend/server.py`
- Modify: `yuki/backend/auth.py`
- Test: `tests/backend/test_uds_mode.py`

- [ ] **Step 1: Write the failing test**

`tests/backend/test_uds_mode.py`:

```python
from yuki.backend import auth


def test_uds_mode_skips_token(monkeypatch):
    auth.set_uds_mode(True)
    try:
        auth.verify("anything")  # should NOT raise in UDS mode
    finally:
        auth.set_uds_mode(False)


def test_tcp_mode_still_enforces(monkeypatch):
    auth.set_uds_mode(False)
    auth.set_active_token("secret")
    import pytest
    with pytest.raises(auth.AuthError):
        auth.verify("wrong")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_uds_mode.py -v`
Expected: AttributeError on `auth.set_uds_mode`.

- [ ] **Step 3: Modify `yuki/backend/auth.py`**

```python
_uds_mode = False


def set_uds_mode(enabled: bool) -> None:
    global _uds_mode
    _uds_mode = enabled


def verify(presented: str) -> None:
    if _uds_mode:
        return
    if _token is None or not secrets.compare_digest(_token, presented):
        raise AuthError("invalid token")
```

- [ ] **Step 4: Modify `yuki/backend/cli.py` to accept `--uds`**

Replace `main()`:

```python
def main() -> None:
    import argparse
    from yuki.backend import auth
    from yuki.memory import paths

    parser = argparse.ArgumentParser()
    parser.add_argument("--uds", action="store_true",
                        help="bind a Unix Domain Socket instead of TCP")
    args = parser.parse_args()

    _load_env_files()

    if args.uds:
        auth.set_uds_mode(True)
        sock = paths.socket_path()
        sock.parent.mkdir(parents=True, exist_ok=True)
        if sock.exists():
            sock.unlink()
        _watch_parent_death()  # exit if the Swift parent dies (§9 #8)
        print(f"yuki: backend listening on UDS {sock}", file=sys.stderr)
        uvicorn.run(create_app(), uds=str(sock), log_level="info")
        return

    token = os.environ.get("YUKI_AUTH_TOKEN")
    if not token:
        print("YUKI_AUTH_TOKEN env var is required for TCP mode.", file=sys.stderr)
        sys.exit(2)
    set_active_token(token)
    port = int(os.environ.get("YUKI_PORT", "0"))
    if port:
        print(f"yuki: backend listening on http://127.0.0.1:{port}", file=sys.stderr)
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")
```

- [ ] **Step 5: Run to verify it passes + manual UDS smoke**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_uds_mode.py -v
# Manual: start UDS backend, curl it
YUKI_APP_SUPPORT=/tmp/yuki-test uv run python -m yuki.backend.cli --uds &
sleep 3
curl --unix-socket /tmp/yuki-test/yuki.sock http://yuki/healthz
# Expected: {"status":"ok"} or similar 200
kill %1
```

- [ ] **Step 6: Add parent-death watcher**

Add to `yuki/backend/cli.py` (module level):

```python
def _watch_parent_death() -> None:
    """Exit when the spawning parent (Swift app) dies. macOS lacks
    PR_SET_PDEATHSIG, so poll getppid(): re-parenting to launchd (pid 1)
    means our parent is gone."""
    import os
    import threading
    import time

    original_ppid = os.getppid()

    def _poll() -> None:
        while True:
            time.sleep(2)
            if os.getppid() != original_ppid or os.getppid() == 1:
                os._exit(0)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()
```

- [ ] **Step 7: Commit**

```bash
git add yuki/backend/auth.py yuki/backend/cli.py tests/backend/test_uds_mode.py
git commit -m "feat(backend): --uds mode binds Unix socket, skips token auth, parent-death watcher (Plan O A4)"
```

---

### Task A5: agent-event → SSE bridge

**Files:**
- Create: `yuki/backend/event_bridge.py`
- Create: `tests/backend/test_event_bridge.py`

- [ ] **Step 1: Write the failing test**

`tests/backend/test_event_bridge.py`:

```python
import asyncio
import pytest
from yuki.agent.events.views import AgentEvent, EventType
from yuki.backend.event_bridge import QueueEventSubscriber


@pytest.mark.asyncio
async def test_subscriber_pushes_to_queue():
    q: asyncio.Queue = asyncio.Queue()
    sub = QueueEventSubscriber(q)
    sub.invoke(AgentEvent(type=EventType.THOUGHT, data={"thought": "hi"}))
    ev = await asyncio.wait_for(q.get(), timeout=1.0)
    assert ev.type == EventType.THOUGHT
    assert ev.data["thought"] == "hi"


@pytest.mark.asyncio
async def test_event_to_sse_shapes():
    from yuki.backend.event_bridge import event_to_sse
    ev = AgentEvent(type=EventType.TOOL_CALL,
                    data={"tool_name": "app_tool", "tool_params": {"name": "Chrome"}})
    sse = event_to_sse(ev)
    assert sse["type"] == "tool_call"
    assert sse["tool_name"] == "app_tool"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_event_bridge.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/backend/event_bridge.py`**

```python
"""Bridge agent events into an asyncio.Queue the SSE generator drains.

The agent loop may emit from a worker thread, so put_nowait must hop back to
the event loop via call_soon_threadsafe.
"""

from __future__ import annotations

import asyncio
from typing import Any

from yuki.agent.events.subscriber import BaseEventSubscriber
from yuki.agent.events.views import AgentEvent, EventType


class QueueEventSubscriber(BaseEventSubscriber):
    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._loop = asyncio.get_event_loop()

    def invoke(self, event: AgentEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


def event_to_sse(ev: AgentEvent) -> dict[str, Any]:
    d: dict[str, Any] = {"type": ev.type.value}
    d.update(ev.data)
    return d
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_event_bridge.py -v`
Expected: 2 PASS. (If `pytest-asyncio` missing: `uv add --dev pytest-asyncio` and add `asyncio_mode = "auto"` to pyproject `[tool.pytest.ini_options]`.)

- [ ] **Step 5: Commit**

```bash
git add yuki/backend/event_bridge.py tests/backend/test_event_bridge.py
git commit -m "feat(backend): QueueEventSubscriber bridges agent events to SSE (Plan O A5)"
```

---

### Task A6: stream control events live

**Files:**
- Modify: `yuki/backend/routers/chat.py`

This rewires `_stream_control` to run the agent in a background task while
draining the event queue, yielding each step as SSE. ConsoleEventSubscriber
stays alongside (so terminal logs survive).

- [ ] **Step 1: Modify `_stream_control` in `yuki/backend/routers/chat.py`**

Replace the `agent = Agent(llm=llm)` + blocking-invoke block with:

```python
    import asyncio as _asyncio
    from yuki.backend.event_bridge import QueueEventSubscriber, event_to_sse

    queue: _asyncio.Queue = _asyncio.Queue()
    agent = Agent(llm=llm, event_subscriber=QueueEventSubscriber(queue))

    foreground_bundle = ""
    try:
        win = agent.desktop.get_foreground_window()
        if win:
            foreground_bundle = win.bundle_id or ""
    except Exception:
        foreground_bundle = ""
    log.info(f"[/control] foreground app: {foreground_bundle or '(none)'}")

    started = datetime.now(UTC)
    t0 = time.monotonic()
    outcome = "success"
    failure_mode = FailureMode.NONE
    content = ""

    task = _asyncio.create_task(agent.ainvoke(task=framed))
    while True:
        try:
            ev = await _asyncio.wait_for(queue.get(), timeout=0.25)
            yield event_to_sse(ev)
        except _asyncio.TimeoutError:
            if task.done():
                break
    try:
        result = await task
        content = getattr(result, "content", "") or ""
        if not getattr(result, "is_done", True):
            outcome = "failure"
            failure_mode = FailureMode.AGENT_STEP_LIMIT
    except Exception as e:
        outcome = "failure"
        failure_mode = FailureMode.PROVIDER_ERROR
        content = f"agent error: {e}"
```

Keep the existing `append_task_record(...)` and final `done` yield below this.

- [ ] **Step 2: Verify ConsoleEventSubscriber survives**

Note in `yuki/agent/service.py:125-128`: passing `event_subscriber` skips the
`else` branch that adds ConsoleEventSubscriber. Fix so both run — modify
`Agent.__init__`:

```python
        if event_subscriber is not None:
            self.event.add_subscriber(event_subscriber)
        if log_to_console:
            self.event.add_subscriber(ConsoleEventSubscriber())
        if log_to_file:
            self.event.add_subscriber(FileEventSubscriber())
```

(Change the `elif`/`else` chain so console logging is independent of whether a
custom subscriber was passed.)

- [ ] **Step 3: Manual smoke**

```bash
YUKI_APP_SUPPORT=/tmp/yuki-test uv run python -m yuki.backend.cli --uds &
sleep 3
curl --no-buffer --unix-socket /tmp/yuki-test/yuki.sock \
  -X POST http://yuki/chat/control \
  -H 'Content-Type: application/json' \
  -d '{"message":"open chrome"}'
# Expected: a STREAM of SSE events (tool_call, tool_result, ...) then done,
# NOT a single done at the end.
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add yuki/backend/routers/chat.py yuki/agent/service.py
git commit -m "feat(backend): /control streams live agent events via SSE (Plan O A6)"
```

---

### Task A7: POST /route classifier

**Files:**
- Create: `yuki/backend/routers/route.py`
- Modify: `yuki/backend/server.py` (register router)
- Create: `tests/backend/test_route.py`

- [ ] **Step 1: Write the failing test**

`tests/backend/test_route.py`:

```python
from yuki.backend.routers.route import _heuristic_route


def test_heuristic_action_verbs_go_control():
    assert _heuristic_route("open whatsapp and message saran") == "control"
    assert _heuristic_route("click the submit button") == "control"


def test_heuristic_questions_go_chat():
    assert _heuristic_route("what is the capital of france") == "chat"
    assert _heuristic_route("explain how tcp works") == "chat"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_route.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/backend/routers/route.py`**

```python
"""POST /route — classify a user message as 'chat' or 'control'.

LLM-first with a deterministic heuristic fallback so the UI never stalls.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("yuki")
router = APIRouter(prefix="/route", tags=["route"])

_ACTION_VERBS = {
    "open", "close", "click", "type", "send", "message", "search", "find",
    "play", "pause", "scroll", "switch", "launch", "quit", "copy", "paste",
    "screenshot", "navigate", "go", "fill", "submit", "download", "delete",
    "rename", "move", "drag", "select", "press",
}


class RouteRequest(BaseModel):
    message: str


def _heuristic_route(message: str) -> str:
    first = re.findall(r"[a-z']+", message.lower())[:3]
    if any(w in _ACTION_VERBS for w in first):
        return "control"
    return "chat"


_PROMPT = """Classify the user's request as either "chat" or "control".

- "control": the user wants you to DO something on their Mac (open apps, send
  messages, click, type, automate, find/play media, manipulate files).
- "chat": the user is asking a question or wants information, with no action
  on their machine.

Examples:
- "open whatsapp and message mom" -> control
- "what's the weather" -> chat
- "find me an interesting video and play it" -> control
- "explain quantum tunneling" -> chat

Respond with ONLY one word: chat or control.

User request: {message}"""


@router.post("")
async def post_route(req: RouteRequest) -> dict[str, Any]:
    msg = req.message.strip()
    if not msg:
        return {"route": "chat", "reason": "empty"}
    try:
        from yuki.messages import HumanMessage
        from yuki.providers.factory import make_llm
        llm = make_llm()
        event = await llm.ainvoke(
            messages=[HumanMessage(content=_PROMPT.format(message=msg))],
            tools=[],
        )
        text = (event.content or "").strip().lower() if event else ""
        if "control" in text:
            return {"route": "control", "reason": "llm"}
        if "chat" in text:
            return {"route": "chat", "reason": "llm"}
    except Exception as e:
        log.warning("route classifier llm failed: %s; using heuristic", e)
    return {"route": _heuristic_route(msg), "reason": "heuristic"}
```

- [ ] **Step 4: Register in `yuki/backend/server.py`**

In `create_app`, add to the import tuple and include it:

```python
    from yuki.backend.routers import (
        chat, health, memory, route, safety, scan, settings, tools, triggers,
    )
    ...
    app.include_router(route.router, dependencies=[Depends(require_token)])
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_route.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Add `POST /settings/provider` (for B6 onboarding)**

The Swift first-run/Settings UI needs to persist provider+model and trigger a
test. Add to `yuki/backend/routers/route.py` (or a new `settings_provider`
router; route.py is fine since it's small):

```python
class ProviderConfig(BaseModel):
    provider: str
    model: str | None = None


@router.post("/../settings/provider", include_in_schema=False)
async def _unused() -> None:  # placeholder; see real router below
    ...
```

Cleaner: create `yuki/backend/routers/provider.py`:

```python
"""POST /settings/provider — persist provider/model; GET tests connection."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from yuki.backend import appstate

router = APIRouter(prefix="/settings/provider", tags=["settings"])


class ProviderConfig(BaseModel):
    provider: str
    model: str | None = None


@router.post("")
async def set_provider(cfg: ProviderConfig) -> dict[str, str]:
    state = appstate.load()
    state["llm_provider"] = cfg.provider
    if cfg.model:
        state["llm_model"] = cfg.model
    appstate.save(state)
    return {"ok": "true"}


@router.get("/test")
async def test_provider() -> dict[str, bool]:
    try:
        from yuki.messages import HumanMessage
        from yuki.providers.factory import make_llm
        llm = make_llm()
        ev = await llm.ainvoke(messages=[HumanMessage(content="ping")], tools=[])
        return {"ok": bool(ev and (ev.content or "").strip())}
    except Exception:
        return {"ok": False}
```

Register in `server.py`: `app.include_router(provider.router, dependencies=[Depends(require_token)])`.

- [ ] **Step 7: Commit**

```bash
git add yuki/backend/routers/route.py yuki/backend/routers/provider.py yuki/backend/server.py tests/backend/test_route.py
git commit -m "feat(backend): POST /route classifier + /settings/provider (Plan O A7)"
```

---

### Task A8: single-worker control queue

**Files:**
- Create: `yuki/backend/queue.py`
- Create: `tests/backend/test_queue.py`

- [ ] **Step 1: Write the failing test**

`tests/backend/test_queue.py`:

```python
import asyncio
import pytest
from yuki.backend.queue import ControlQueue


@pytest.mark.asyncio
async def test_serializes_tasks():
    q = ControlQueue()
    order = []

    async def job(name):
        order.append(f"start-{name}")
        await asyncio.sleep(0.05)
        order.append(f"end-{name}")
        return name

    h1 = await q.submit(lambda: job("a"))
    h2 = await q.submit(lambda: job("b"))
    r1 = await h1
    r2 = await h2
    assert r1 == "a" and r2 == "b"
    # b must not start until a ends
    assert order == ["start-a", "end-a", "start-b", "end-b"]


@pytest.mark.asyncio
async def test_depth_reports_waiting():
    q = ControlQueue()

    async def slow():
        await asyncio.sleep(0.1)

    await q.submit(slow)
    await q.submit(slow)
    assert q.depth() >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_queue.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/backend/queue.py`**

```python
"""FIFO single-worker queue so two /control tasks never fight the mouse."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class ControlQueue:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._waiting = 0

    def depth(self) -> int:
        return self._waiting

    async def submit(self, job: Callable[[], Awaitable[Any]]) -> asyncio.Future:
        """Schedule job; returns a future resolving to its result.
        Jobs run one at a time in submission order."""
        fut: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _run() -> None:
            self._waiting += 1
            async with self._lock:
                self._waiting -= 1
                try:
                    result = await job()
                    fut.set_result(result)
                except Exception as e:
                    fut.set_exception(e)

        asyncio.create_task(_run())
        return fut
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_queue.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add yuki/backend/queue.py tests/backend/test_queue.py
git commit -m "feat(backend): single-worker ControlQueue (Plan O A8)"
```

Note: wiring the queue into the `/control` route is deferred to integration
(Task A6 already streams; queueing wraps the create_task). The module + tests
land here; the route uses a module-global `ControlQueue()` and submits the
agent run through it in a follow-up edit during Phase B integration testing.

---

### Task A9: schema versioning + migrations skeleton

**Files:**
- Create: `yuki/migrations/__init__.py`
- Create: `yuki/migrations/v1.py`
- Create: `tests/migrations/test_migrations.py`

- [ ] **Step 1: Write the failing test**

`tests/migrations/test_migrations.py`:

```python
from yuki.migrations import CURRENT_SCHEMA, run_migrations


def test_current_schema_is_int():
    assert isinstance(CURRENT_SCHEMA, int)
    assert CURRENT_SCHEMA >= 1


def test_run_migrations_noop_at_current(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_APP_SUPPORT", str(tmp_path))
    # Fresh install: nothing stored, should stamp current and not error.
    applied = run_migrations()
    assert applied == []  # nothing to migrate on a fresh v1 install
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/migrations/test_migrations.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/migrations/__init__.py`**

```python
"""Forward-only, idempotent schema migrations.

CURRENT_SCHEMA is the version the running code expects. run_migrations reads
the stored version from app_state.json, runs each migration > stored, and
stamps the new version. v0.1 ships at schema 1 with nothing to migrate.
"""

from __future__ import annotations

import logging

from yuki.backend import appstate

log = logging.getLogger(__name__)

CURRENT_SCHEMA = 1

# Ordered (version, callable) migrations. Each takes no args, is idempotent.
_MIGRATIONS: list[tuple[int, object]] = []


def run_migrations() -> list[int]:
    cfg = appstate.load()
    stored = int(cfg.get("schema_version", 1))
    applied: list[int] = []
    for version, fn in _MIGRATIONS:
        if version > stored:
            log.info("running migration to schema %d", version)
            fn()  # type: ignore[operator]
            applied.append(version)
    if applied or stored != CURRENT_SCHEMA:
        cfg["schema_version"] = CURRENT_SCHEMA
        appstate.save(cfg)
    return applied
```

`yuki/migrations/v1.py`:

```python
"""Baseline schema. Nothing to migrate from."""
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/migrations/test_migrations.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Call on backend startup**

In `yuki/backend/server.py` `_lifespan`, after `get_runtime()`:

```python
    try:
        from yuki.migrations import run_migrations
        run_migrations()
    except Exception as e:
        log.warning("migrations failed: %s", e)
```

- [ ] **Step 6: Commit**

```bash
git add yuki/migrations/ tests/migrations/ yuki/backend/server.py
git commit -m "feat(migrations): schema versioning skeleton (Plan O A9)"
```

---

### Task A10: chat_cli over UDS

**Files:**
- Modify: `yuki/backend/chat_cli.py`

- [ ] **Step 1: Add UDS transport selection**

In `_resolve_url`/client setup, detect UDS mode. Replace the `httpx.Client()`
construction so that when `YUKI_UDS=1` (or socket file exists), it uses a UDS
transport:

```python
def _make_client() -> httpx.Client:
    from yuki.memory import paths
    sock = paths.socket_path()
    if os.environ.get("YUKI_UDS") == "1" or sock.exists():
        transport = httpx.HTTPTransport(uds=str(sock))
        return httpx.Client(transport=transport, base_url="http://yuki")
    return httpx.Client()
```

Update `_check_backend`, `_post_chat`, `_post_simple`, `_get_status` to use
`base_url` when set (so they call `client.post("/chat", ...)` not a full URL).

- [ ] **Step 2: Manual smoke**

```bash
YUKI_APP_SUPPORT=/tmp/yuki-test uv run python -m yuki.backend.cli --uds &
sleep 3
YUKI_APP_SUPPORT=/tmp/yuki-test YUKI_UDS=1 uv run python -m yuki.backend.chat_cli
# Type "hello" → expect a reply with ctx badge, over the socket.
kill %1
```

- [ ] **Step 3: Commit**

```bash
git add yuki/backend/chat_cli.py
git commit -m "feat(cli): chat_cli speaks over UDS (Plan O A10)"
```

---

### Phase A gate

Before any Swift work:

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest -q
```

All green. The entire backend is now operable over UDS with live streaming,
routing, queue, app-state config, and migrations. Verified end-to-end with
`curl --unix-socket` and the UDS chat_cli.

---

## Phase B — Swift app

Swift UI tasks are verified visually against §9 acceptance criteria, not unit
tests. Each task lists exact files, exact code, and a manual verification step.

### Task B0: Migrate SPM → Xcode project

**Files:**
- Create: `app/Yuki.xcodeproj` (via Xcode)
- Modify: `app/Yuki/Info.plist`
- Delete: `app/Package.swift` (after migration verified)

- [ ] **Step 1: Create the Xcode project**

In Xcode: File → New → Project → macOS → App. Product name `Yuki`, bundle id
`com.yuki.app`, interface SwiftUI, language Swift, location `app/`. Delete the
template `ContentView.swift`/`YukiApp.swift` Xcode generated; add the existing
`app/Yuki/*.swift` files to the target (drag into Project Navigator, check
"Yuki" target membership).

- [ ] **Step 2: Configure Info.plist**

Set:
- `LSUIElement` = `YES` (menu-bar app, no Dock icon)
- `LSMinimumSystemVersion` = `13.0`
- `CFBundleIdentifier` = `com.yuki.app`
- Add usage strings (even though we don't screenshot, AX needs none but be safe):
  no special keys required for Accessibility (it's runtime-prompted).

- [ ] **Step 3: Add entitlements file**

Create `app/Yuki/Yuki.entitlements`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.app-sandbox</key><false/>
  <key>com.apple.security.automation.apple-events</key><true/>
</dict>
</plist>
```
(App sandbox OFF — Yuki needs to drive arbitrary apps, incompatible with
sandbox.) Set `CODE_SIGN_ENTITLEMENTS` to this file in build settings.

- [ ] **Step 4: Verify it builds + runs**

```bash
cd /Users/mafex/code/personal/Yuki/app
xcodebuild -project Yuki.xcodeproj -scheme Yuki -configuration Debug build
```
Expected: BUILD SUCCEEDED. Run from Xcode; menu-bar "Y" appears, no Dock icon.

- [ ] **Step 5: Commit**

```bash
git add app/
git commit -m "build(app): migrate SPM to Xcode project, LSUIElement, entitlements (Plan O B0)"
```

---

### Task B1: UDSClient — streaming HTTP over Unix socket

**Files:**
- Create: `app/Yuki/UDSClient.swift`

Risk task (§8.1). Uses `Network.framework` `NWConnection` over
`NWEndpoint.unix` because URLSession's UDS + streaming support is unreliable.
Implements: a one-shot request/response, and a streaming SSE read.

- [ ] **Step 1: Implement `app/Yuki/UDSClient.swift`**

```swift
import Foundation
import Network

/// Minimal HTTP/1.1 client over a Unix Domain Socket using NWConnection.
/// Supports a buffered request (postJSON) and a line-streaming request (streamSSE).
final class UDSClient {
    private let socketPath: String

    init(socketPath: String) { self.socketPath = socketPath }

    private func makeConnection() -> NWConnection {
        let endpoint = NWEndpoint.unix(path: socketPath)
        let params = NWParameters.tcp
        return NWConnection(to: endpoint, using: params)
    }

    /// Buffered POST returning the full response body as Data.
    func postJSON(path: String, body: Data) async throws -> Data {
        try await withCheckedThrowingContinuation { cont in
            let conn = makeConnection()
            var received = Data()
            conn.stateUpdateHandler = { state in
                if case .failed(let err) = state { cont.resume(throwing: err) }
            }
            conn.start(queue: .global())
            let req = Self.httpRequest(method: "POST", path: path, body: body)
            conn.send(content: req, completion: .contentProcessed { err in
                if let err = err { cont.resume(throwing: err); return }
            })
            func readMore() {
                conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) {
                    data, _, isComplete, err in
                    if let data = data { received.append(data) }
                    if isComplete || err != nil {
                        conn.cancel()
                        cont.resume(returning: Self.stripHeaders(received))
                    } else { readMore() }
                }
            }
            readMore()
        }
    }

    /// Streaming POST: calls onEvent for each SSE "data:" line as it arrives.
    func streamSSE(path: String, body: Data,
                   onEvent: @escaping (String) -> Void,
                   onDone: @escaping () -> Void) {
        let conn = makeConnection()
        var buffer = Data()
        var headersDone = false
        conn.stateUpdateHandler = { state in
            if case .failed = state { onDone() }
            if case .cancelled = state { onDone() }
        }
        conn.start(queue: .global())
        let req = Self.httpRequest(method: "POST", path: path, body: body)
        conn.send(content: req, completion: .contentProcessed { _ in })
        func readMore() {
            conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) {
                data, _, isComplete, err in
                if let data = data {
                    buffer.append(data)
                    if !headersDone, let range = buffer.range(of: Data("\r\n\r\n".utf8)) {
                        buffer.removeSubrange(buffer.startIndex..<range.upperBound)
                        headersDone = true
                    }
                    while let nl = buffer.firstIndex(of: 0x0A) {
                        let lineData = buffer[buffer.startIndex..<nl]
                        buffer.removeSubrange(buffer.startIndex...nl)
                        if let line = String(data: lineData, encoding: .utf8) {
                            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                            if trimmed.hasPrefix("data:") {
                                onEvent(String(trimmed.dropFirst(5))
                                    .trimmingCharacters(in: .whitespaces))
                            }
                        }
                    }
                }
                if isComplete || err != nil { conn.cancel(); onDone() }
                else { readMore() }
            }
        }
        readMore()
    }

    private static func httpRequest(method: String, path: String, body: Data) -> Data {
        var head = "\(method) \(path) HTTP/1.1\r\n"
        head += "Host: yuki\r\n"
        head += "Content-Type: application/json\r\n"
        head += "Content-Length: \(body.count)\r\n"
        head += "Connection: close\r\n\r\n"
        var data = Data(head.utf8)
        data.append(body)
        return data
    }

    private static func stripHeaders(_ data: Data) -> Data {
        if let range = data.range(of: Data("\r\n\r\n".utf8)) {
            return data.subdata(in: range.upperBound..<data.endIndex)
        }
        return data
    }
}
```

- [ ] **Step 2: Manual verification (with Phase A backend running on UDS)**

Add a temporary debug call in `AppDelegate.applicationDidFinishLaunching`:
```swift
Task {
    let c = UDSClient(socketPath: NSHomeDirectory() +
        "/Library/Application Support/Yuki/yuki.sock")
    let data = try await c.postJSON(path: "/healthz", body: Data("{}".utf8))
    NSLog("healthz: \(String(data: data, encoding: .utf8) ?? "nil")")
}
```
Run backend with `--uds`, run the app, confirm the NSLog prints the healthz
JSON. Then remove the debug call.

- [ ] **Step 3: Commit**

```bash
git add app/Yuki/UDSClient.swift
git commit -m "feat(app): UDSClient — streaming HTTP over Unix socket (Plan O B1)"
```

---

### Task B2: BackendController spawns bundled Python over UDS

**Files:**
- Modify: `app/Yuki/BackendController.swift`

- [ ] **Step 1: Rewrite `BackendController.swift`**

```swift
import Foundation

enum BackendError: Error { case missingPython, startupTimeout }

actor BackendController {
    private var process: Process?

    private var socketPath: String {
        NSHomeDirectory() + "/Library/Application Support/Yuki/yuki.sock"
    }

    func start() async throws {
        let res = Bundle.main.resourceURL!
        let python = res.appendingPathComponent("python/bin/python3")
        guard FileManager.default.fileExists(atPath: python.path) else {
            throw BackendError.missingPython
        }
        // Clean stale socket.
        try? FileManager.default.removeItem(atPath: socketPath)

        let p = Process()
        p.executableURL = python
        p.arguments = ["-m", "yuki.backend.cli", "--uds"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = res.appendingPathComponent(
            "python/lib/python3.12/site-packages").path
        env["TIKTOKEN_CACHE_DIR"] = res.appendingPathComponent("tiktoken").path
        p.environment = env
        let logURL = URL(fileURLWithPath: NSHomeDirectory() +
            "/Library/Application Support/Yuki/python.log")
        try? FileManager.default.createDirectory(
            at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let handle = try FileHandle(forWritingTo: logURL)
        p.standardError = handle
        p.standardOutput = handle
        try p.run()
        self.process = p
        try await waitForSocket()
    }

    func stop() {
        process?.terminate()
        process = nil
    }

    private func waitForSocket() async throws {
        let deadline = Date().addingTimeInterval(20)
        let client = UDSClient(socketPath: socketPath)
        while Date() < deadline {
            if FileManager.default.fileExists(atPath: socketPath),
               let _ = try? await client.postJSON(path: "/healthz",
                                                   body: Data("{}".utf8)) {
                return
            }
            try? await Task.sleep(nanoseconds: 300_000_000)
        }
        throw BackendError.startupTimeout
    }
}
```

- [ ] **Step 2: Update `YukiApp.swift` AppDelegate**

```swift
func applicationDidFinishLaunching(_ notification: Notification) {
    Task {
        do {
            try await backend.start()
            menu.attach()
            hotkey.register(
                onTap: { CommandBar.shared.toggle() },
                onLongPress: nil
            )
            FirstRun.runIfNeeded()
        } catch {
            NSLog("Yuki failed to start: \(error)")
            FatalDialog.show(error: error)
        }
    }
}
```

- [ ] **Step 3: Verify (after Python tree is bundled in B-late / C)**

For now, point at a dev Python: temporarily set `python` to the repo's
`.venv/bin/python3` and `PYTHONPATH` to the repo root, confirm the app spawns
the backend and healthz passes. Real bundling happens in Phase C.

- [ ] **Step 4: Commit**

```bash
git add app/Yuki/BackendController.swift app/Yuki/YukiApp.swift
git commit -m "feat(app): BackendController spawns bundled Python over UDS (Plan O B2)"
```

---

### Task B3: Keychain helper

**Files:**
- Create: `app/Yuki/Keychain.swift`

- [ ] **Step 1: Implement `app/Yuki/Keychain.swift`**

```swift
import Foundation
import Security

enum Keychain {
    static let service = "com.yuki.app"

    static func set(_ value: String, account: String) {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        SecItemAdd(add as CFDictionary, nil)
    }

    static func get(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
```

- [ ] **Step 2: Verify**

Temporary debug: `Keychain.set("test123", account: "google")` then
`NSLog(Keychain.get(account: "google") ?? "nil")`. Confirm prints `test123`.
Confirm Python side reads it: `security find-generic-password -s com.yuki.app -a google -w` prints `test123`. Remove debug.

- [ ] **Step 3: Commit**

```bash
git add app/Yuki/Keychain.swift
git commit -m "feat(app): Keychain helper for api keys (Plan O B3)"
```

---

### Task B4: CommandBar (frosted panel + history + routing)

**Files:**
- Create: `app/Yuki/CommandBar.swift`
- Delete: `app/Yuki/ChatOverlay.swift` (superseded)

- [ ] **Step 1: Implement `app/Yuki/CommandBar.swift`**

```swift
import AppKit
import SwiftUI

@MainActor
final class CommandBar {
    static let shared = CommandBar()
    private var panel: NSPanel?

    func toggle() {
        if let p = panel, p.isVisible { p.orderOut(nil); return }
        if panel == nil { build() }
        position()
        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func close() { panel?.orderOut(nil) }

    private func build() {
        let p = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 720, height: 120),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered, defer: false)
        p.level = .floating
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.contentView = NSHostingView(rootView: CommandBarView())
        p.isMovableByWindowBackground = true
        panel = p
    }

    private func position() {
        guard let p = panel, let screen = NSScreen.main else { return }
        let f = screen.visibleFrame
        let x = f.midX - 360
        let y = f.maxY - f.height * 0.30
        p.setFrameOrigin(NSPoint(x: x, y: y))
    }
}

struct CommandBarView: View {
    @State private var input = ""
    @State private var history: [(role: String, text: String)] = []
    @State private var ctxBadge = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("yuki").font(.headline).foregroundStyle(.secondary)
                Spacer()
                Text(ctxBadge).font(.caption).foregroundStyle(.tertiary)
            }
            if !history.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(history.indices, id: \.self) { i in
                            Text(history[i].role == "human"
                                 ? "> \(history[i].text)" : history[i].text)
                                .font(.callout)
                                .foregroundStyle(history[i].role == "human"
                                                 ? .primary : .secondary)
                        }
                    }
                }.frame(maxHeight: 200)
            }
            TextField("Ask Yuki…", text: $input)
                .textFieldStyle(.plain)
                .font(.title3)
                .onSubmit { submit() }
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .onAppear { loadStatus() }
    }

    private func submit() {
        let msg = input.trimmingCharacters(in: .whitespaces)
        guard !msg.isEmpty else { return }
        input = ""
        if msg == "/clear" { clearHistory(); return }
        if msg == "/compact" { compact(); return }
        history.append((role: "human", text: msg))
        Task { await route(msg) }
    }

    private func route(_ msg: String) async {
        let decision = await Backend.shared.route(msg)
        if decision == "control" {
            CommandBar.shared.close()
            HUD.shared.begin(task: msg)
            await Backend.shared.runControl(msg)
        } else {
            let (reply, badge) = await Backend.shared.chat(msg)
            history.append((role: "ai", text: reply))
            ctxBadge = badge
        }
    }

    private func loadStatus() {
        Task {
            let st = await Backend.shared.status()
            ctxBadge = st.badge
            history = await Backend.shared.recentHistory()
        }
    }
    private func clearHistory() {
        Task { _ = await Backend.shared.clear(); history = []; loadStatus() }
    }
    private func compact() {
        Task { let b = await Backend.shared.compact(); ctxBadge = b }
    }
}
```

- [ ] **Step 2: Stub `Backend` facade**

Create `app/Yuki/Backend.swift` — a thin async wrapper over `UDSClient`:

```swift
import Foundation

@MainActor
final class Backend {
    static let shared = Backend()
    private let client = UDSClient(socketPath: NSHomeDirectory() +
        "/Library/Application Support/Yuki/yuki.sock")

    func route(_ msg: String) async -> String {
        let body = try? JSONSerialization.data(withJSONObject: ["message": msg])
        guard let data = try? await client.postJSON(path: "/route", body: body ?? Data()),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return "chat" }
        return (obj["route"] as? String) ?? "chat"
    }

    func chat(_ msg: String) async -> (String, String) {
        // /chat is SSE; collect the single 'done' event.
        var reply = ""; var badge = ""
        await withCheckedContinuation { cont in
            let body = try! JSONSerialization.data(withJSONObject: ["message": msg])
            client.streamSSE(path: "/chat", body: body, onEvent: { line in
                if let d = line.data(using: .utf8),
                   let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                    if o["type"] as? String == "done" {
                        reply = o["content"] as? String ?? ""
                        badge = o["ctx_badge"] as? String ?? ""
                    }
                }
            }, onDone: { cont.resume() })
        }
        return (reply, badge)
    }

    func runControl(_ msg: String) async {
        await withCheckedContinuation { cont in
            let body = try! JSONSerialization.data(withJSONObject: ["message": msg])
            client.streamSSE(path: "/chat/control", body: body, onEvent: { line in
                if let d = line.data(using: .utf8),
                   let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                    Task { @MainActor in HUD.shared.handle(event: o) }
                }
            }, onDone: { cont.resume() })
        }
    }

    func status() async -> (badge: String, percent: Int) {
        guard let data = try? await client.postJSON(path: "/chat/status",
                                                    body: Data("{}".utf8)),
              let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return ("", 0) }
        return (o["ctx_badge"] as? String ?? "", o["ctx_percent"] as? Int ?? 0)
    }
    func recentHistory() async -> [(role: String, text: String)] { [] } // fill from /chat/status later
    func clear() async -> Bool {
        _ = try? await client.postJSON(path: "/chat/clear", body: Data("{}".utf8)); return true
    }
    func compact() async -> String {
        guard let data = try? await client.postJSON(path: "/chat/compact",
                                                    body: Data("{}".utf8)),
              let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return "" }
        return o["ctx_badge"] as? String ?? ""
    }
}
```

Note: `/chat/status` is GET in the backend — change `Backend.status()` to do a
GET via a small `getJSON` added to `UDSClient` (mirror `postJSON` with method
"GET", empty body). Add that method when implementing.

- [ ] **Step 3: Verify visually**

Cmd+Shift+A opens a frosted rounded panel at top-third. Type "what is 2+2",
Enter → routes to chat → "4" appears above input with a ctx badge. Type
"open chrome" → panel closes, HUD appears (next task). Esc closes panel.

- [ ] **Step 4: Commit**

```bash
git add app/Yuki/CommandBar.swift app/Yuki/Backend.swift
git rm app/Yuki/ChatOverlay.swift
git commit -m "feat(app): Raycast-style CommandBar + Backend UDS facade (Plan O B4)"
```

---

### Task B5: HUD pill + state machine

**Files:**
- Create: `app/Yuki/HUD.swift`

- [ ] **Step 1: Implement `app/Yuki/HUD.swift`**

```swift
import AppKit
import SwiftUI

@MainActor
final class HUD: ObservableObject {
    static let shared = HUD()
    private var panel: NSPanel?

    @Published var line = ""
    @Published var state: State = .idle
    enum State { case idle, running, success, failure }

    private static let verbMap: [String: String] = [
        "app_tool": "Switching to", "click_tool": "Clicking",
        "type_tool": "Typing", "shortcut_tool": "Pressing",
        "shell_tool": "Running", "scroll_tool": "Scrolling",
        "scrape_tool": "Reading", "wait_tool": "Waiting",
        "list_app_notes": "Checking app notes", "read_app_note": "Reading guidance",
    ]

    func begin(task: String) {
        state = .running
        line = "Starting…"
        show()
    }

    func handle(event o: [String: Any]) {
        guard let type = o["type"] as? String else { return }
        switch type {
        case "tool_call":
            let tool = o["tool_name"] as? String ?? ""
            let verb = Self.verbMap[tool] ?? tool
            line = verb
        case "done":
            state = .success
            line = (o["content"] as? String ?? "Done").prefix(120).description
            fadeAfter(5)
        case "error":
            state = .failure
            line = o["error"] as? String ?? "Failed"
            // sticky — no auto-fade
        default: break
        }
    }

    private func show() {
        if panel == nil { build() }
        position()
        panel?.orderFront(nil)
    }
    private func fadeAfter(_ secs: Double) {
        Task { try? await Task.sleep(nanoseconds: UInt64(secs * 1e9))
            if state == .success { panel?.orderOut(nil); state = .idle } }
    }
    private func build() {
        let p = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 300, height: 80),
                        styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        p.level = .floating; p.isOpaque = false
        p.backgroundColor = .clear; p.hasShadow = true
        p.contentView = NSHostingView(rootView: HUDView(hud: self))
        panel = p
    }
    private func position() {
        guard let p = panel, let s = NSScreen.main else { return }
        let f = s.visibleFrame
        let corner = UserDefaults.standard.string(forKey: "yuki.hudCorner") ?? "top-right"
        let m: CGFloat = 16
        let x: CGFloat, y: CGFloat
        switch corner {
        case "top-left": x = f.minX + m; y = f.maxY - 80 - m
        case "bottom-right": x = f.maxX - 300 - m; y = f.minY + m
        case "bottom-left": x = f.minX + m; y = f.minY + m
        default: x = f.maxX - 300 - m; y = f.maxY - 80 - m
        }
        p.setFrameOrigin(NSPoint(x: x, y: y))
    }
}

struct HUDView: View {
    @ObservedObject var hud: HUD
    var body: some View {
        HStack(spacing: 10) {
            icon
            Text(hud.line).font(.callout).lineLimit(2)
            Spacer()
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .frame(width: 300)
    }
    @ViewBuilder private var icon: some View {
        switch hud.state {
        case .running: ProgressView().controlSize(.small)
        case .success: Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
        case .failure: Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
        case .idle: EmptyView()
        }
    }
}
```

- [ ] **Step 2: Verify visually**

Run a `/control` task. HUD pill appears in top-right (or configured corner),
spinner + "Switching to Chrome" → "Typing youtube.com" → green check → fades
after 5s. Force a failure (disconnect provider) → red, sticky.

- [ ] **Step 3: Commit**

```bash
git add app/Yuki/HUD.swift
git commit -m "feat(app): corner HUD pill with live state machine (Plan O B5)"
```

---

### Task B6: First-run (permissions + provider onboarding)

**Files:**
- Create: `app/Yuki/FirstRun.swift`

- [ ] **Step 1: Implement `app/Yuki/FirstRun.swift`**

```swift
import AppKit
import SwiftUI
import ApplicationServices

@MainActor
enum FirstRun {
    static func runIfNeeded() {
        let configured = (try? Backend.shared) != nil
        let axOK = AXIsProcessTrusted()
        let hasProvider = UserDefaults.standard.bool(forKey: "yuki.providerConfigured")
        if axOK && hasProvider { return }
        showWindow()
    }

    private static func showWindow() {
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 520, height: 420),
                         styleMask: [.titled, .closable],
                         backing: .buffered, defer: false)
        w.title = "Welcome to Yuki"
        w.center()
        w.contentView = NSHostingView(rootView: FirstRunView(window: w))
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    static func openAccessibilitySettings() {
        let url = URL(string:
          "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
        NSWorkspace.shared.open(url)
    }
}

struct FirstRunView: View {
    let window: NSWindow
    @State private var axGranted = AXIsProcessTrusted()
    @State private var provider = "google"
    @State private var apiKey = ""
    @State private var testResult = ""
    let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Welcome to Yuki").font(.title.bold())

            GroupBox("1. Accessibility permission") {
                HStack {
                    Image(systemName: axGranted ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(axGranted ? .green : .secondary)
                    Text(axGranted ? "Granted" : "Yuki needs Accessibility to drive apps")
                    Spacer()
                    if !axGranted {
                        Button("Open Settings") { FirstRun.openAccessibilitySettings() }
                    }
                }.padding(6)
            }

            GroupBox("2. Choose how Yuki thinks") {
                VStack(alignment: .leading) {
                    Picker("Provider", selection: $provider) {
                        Text("Google Gemini (free tier)").tag("google")
                        Text("Anthropic Claude").tag("anthropic")
                        Text("Local (Ollama)").tag("ollama")
                    }.pickerStyle(.radioGroup)
                    if provider != "ollama" {
                        SecureField("API key", text: $apiKey)
                        Link("Get a key",
                             destination: URL(string: provider == "google"
                               ? "https://aistudio.google.com/apikey"
                               : "https://console.anthropic.com/settings/keys")!)
                            .font(.caption)
                    }
                    HStack {
                        Button("Test connection") { test() }
                        Text(testResult).font(.caption)
                    }
                }.padding(6)
            }

            Spacer()
            HStack {
                Spacer()
                Button("Finish") { finish() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!axGranted)
            }
        }
        .padding(24)
        .onReceive(timer) { _ in axGranted = AXIsProcessTrusted() }
    }

    private func test() {
        if provider != "ollama" && !apiKey.isEmpty {
            Keychain.set(apiKey, account: provider)
        }
        Task {
            let ok = await Backend.shared.testConnection(provider: provider)
            testResult = ok ? "✓ Connected" : "✗ Failed — check key"
        }
    }
    private func finish() {
        if provider != "ollama" && !apiKey.isEmpty {
            Keychain.set(apiKey, account: provider)
        }
        Backend.shared.saveProvider(provider)   // writes app_state.json via backend
        UserDefaults.standard.set(true, forKey: "yuki.providerConfigured")
        window.close()
    }
}
```

Add `testConnection` + `saveProvider` to `Backend` (POST to a new
`/settings/provider` endpoint, or reuse existing `/settings`). If `/settings`
doesn't accept provider writes, add a tiny `POST /settings/provider` in
Phase A follow-up. (Note: small backend addition — fold into Task A3's
settings router or add now.)

- [ ] **Step 2: Verify**

Fresh launch (delete `~/Library/Application Support/Yuki/` and the
`yuki.providerConfigured` default first). Window appears, AX row flips to
green when you grant in Settings, paste a Gemini key, Test → ✓, Finish closes.

- [ ] **Step 3: Commit**

```bash
git add app/Yuki/FirstRun.swift app/Yuki/Backend.swift
git commit -m "feat(app): first-run permissions + provider onboarding (Plan O B6)"
```

---

### Task B7: Settings window + HotKey config + MenuBar refresh

**Files:**
- Create: `app/Yuki/Settings.swift`
- Modify: `app/Yuki/HotKey.swift`, `app/Yuki/MenuBar.swift`

- [ ] **Step 1: Implement `app/Yuki/Settings.swift`**

Tabs: General (launch-at-login via `SMAppService`, hud corner picker, hotkey
field), Provider (reuse FirstRunView's provider section), Permissions (live AX
status), About (version + GitHub link). Persist to `UserDefaults` +
`Backend.saveProvider`. (Full SwiftUI `TabView` with `Form` per tab — standard
boilerplate, ~120 lines.)

Key piece — launch at login:
```swift
import ServiceManagement
func setLaunchAtLogin(_ on: Bool) {
    if on { try? SMAppService.mainApp.register() }
    else { try? SMAppService.mainApp.unregister() }
}
```

- [ ] **Step 2: Make HotKey configurable**

In `HotKey.swift`, read keycode+modifiers from `UserDefaults["yuki.hotkey"]`
(default Cmd+Shift+A: keycode 0 = 'A', `cmdKey|shiftKey`). Re-register when
settings change (post a Notification the AppDelegate observes).

- [ ] **Step 3: MenuBar refresh**

`MenuBar.swift`: add "Settings…" (opens Settings window), "Reveal logs in
Finder" (`NSWorkspace.shared.selectFile`), spinner animation while a control
task runs (observe `HUD.shared.state == .running`).

- [ ] **Step 4: Verify**

Settings opens from menu bar. Toggle launch-at-login (check System Settings →
General → Login Items). Change HUD corner → next task's pill appears there.
Change hotkey → new combo works.

- [ ] **Step 5: Commit**

```bash
git add app/Yuki/Settings.swift app/Yuki/HotKey.swift app/Yuki/MenuBar.swift
git commit -m "feat(app): Settings window, configurable hotkey, menu-bar refresh (Plan O B7)"
```

---

### Task B8: Queue wiring + "next:" subtitle

**Files:**
- Modify: `app/Yuki/HUD.swift`, `app/Yuki/Backend.swift`

- [ ] **Step 1: Serialize control submissions in Backend**

`Backend.runControl` should not start a second SSE stream while one is active.
Add an `actor`-guarded flag or a Swift `AsyncStream` queue; if busy, set
`HUD.shared.queuedPreview = msg` and wait. When the current stream's `onDone`
fires, drain the next.

- [ ] **Step 2: HUD shows "next:"**

Add `@Published var queuedPreview: String?`; render a second line "next:
\(preview)" when set.

- [ ] **Step 3: Verify**

Fire two `/control` tasks quickly. Second waits; HUD shows "next: …"; second
starts only after first's green check.

- [ ] **Step 4: Commit**

```bash
git add app/Yuki/HUD.swift app/Yuki/Backend.swift
git commit -m "feat(app): client-side control queue with next-preview (Plan O B8)"
```

---

## Phase C — Packaging + ship

### Task C1: release.sh + python bundling

**Files:**
- Create: `release.sh`
- Create: `app/ExportOptions.plist`
- Create: `requirements.txt` (frozen from uv)

- [ ] **Step 1: Freeze deps**

```bash
cd /Users/mafex/code/personal/Yuki
uv export --frozen --no-dev > requirements.txt
```

- [ ] **Step 2: Write `release.sh`**

Use the script from spec §6.1. Adjust the python-build-standalone URL to the
current 3.12 arm64 `install_only` release. Add the tiktoken preload step:

```bash
# After installing deps, preload tiktoken BPE into the bundle:
TIKTOKEN_CACHE_DIR="$APP/Contents/Resources/tiktoken" \
  "$APP/Contents/Resources/python/bin/python3" -c \
  "import tiktoken; tiktoken.get_encoding('cl100k_base')"
```

- [ ] **Step 3: `app/ExportOptions.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>mac-application</string>
  <key>signingStyle</key><string>automatic</string>
</dict>
</plist>
```

- [ ] **Step 4: Build once, verify the .app runs standalone**

```bash
chmod +x release.sh
./release.sh 0.1.0-test
# Then: open build/Yuki.app  (verify it launches, backend starts from bundled python)
lsof -iTCP -sTCP:LISTEN | grep -i yuki   # expect NOTHING (UDS only)
```

- [ ] **Step 5: Commit**

```bash
git add release.sh app/ExportOptions.plist requirements.txt
git commit -m "build: release.sh bundles python-build-standalone, tiktoken preload (Plan O C1)"
```

---

### Task C2: Cask + first release + README

**Files:**
- Create: `../homebrew-tap/Casks/yuki.rb`
- Modify: `README.md`

- [ ] **Step 1: Real release**

```bash
./release.sh 0.1.0
```
(Builds, zips, creates GitHub release, writes the Cask, pushes the tap.)

- [ ] **Step 2: Verify install on a clean path**

```bash
brew untap mafex11/tap 2>/dev/null; brew tap mafex11/tap
brew install --cask mafex11/tap/yuki
open /Applications/Yuki.app   # right-click → Open (unsigned)
```

- [ ] **Step 3: README install section**

Add to `README.md`:
- `brew install --cask mafex11/tap/yuki`
- Gatekeeper note + screenshot ("right-click → Open the first time")
- Permissions walkthrough
- "Press ⌘⇧A"

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: install instructions for Cask + Gatekeeper note (Plan O C2)"
```

---

## Self-Review

**Spec coverage:**
- §3.2 UDS → A4. §3.3 bundling → C1. §3.4 lifecycle → B2/B7. §3.5 storage → A1.
- §4.1 CommandBar → B4. §4.2 HUD → B5. §4.3 MenuBar → B7. §4.4 Settings → B7.
  §4.5 permissions assistant → B6.
- §5.1 /route → A7. §5.2 event bridge → A5/A6. §5.3 queue → A8/B8. §5.4 UDS
  auth → A4. §5.5 provider onboarding → B6. §5.6 Ollama → B6 (picker). §5.7
  chat_cli UDS → A10.
- §6 build → C1/C2. §7.1 auto-start → B7. §7.2 migrations → A9. §7.3 logs →
  B2 (python.log) + B7 (reveal logs).

**Gaps found + folded in:** `POST /settings/provider` for B6 — note added in
B6 Step 1 to add a small settings write endpoint (fold into A-phase if doing
strictly; acceptable as a B6 backend touch-up).

**Type consistency:** `Backend` facade methods (`route`, `chat`, `runControl`,
`status`, `clear`, `compact`, `testConnection`, `saveProvider`) referenced
consistently across B4/B5/B6/B7/B8. `UDSClient` needs a `getJSON` for the GET
`/chat/status` — noted in B4 Step 2.

**v0.1 acceptance (§9):** all 10 criteria map to tasks; #8 (force-quit kills
helper) needs the child-death pattern from §8 risk 4 — add to B2 as a Python
`os.getppid()` poll in `cli.py --uds` mode.

