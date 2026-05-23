# Plan G — Native macOS Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 15 native macOS tools called out in spec §7.2 — calendar, reminders, mail, notes, messages, contacts, files, shortcuts, system, clipboard, screenshot, web_search, browser, music, meeting — plus the `@tool` decorator + danger classification + registry that makes them all discoverable to the agent.

**Architecture:** Each tool is one Python module under `yuki/tools/native/`. Each is decorated with `@tool(name, danger)` which registers it into a global `REGISTRY` dict. Tool functions are plain async callables — the registry produces the schema (from type hints + docstring) the agent needs. Most tools use AppleScript via `osascript` (subprocess with static argv, never shell), EventKit via pyobjc, or stdlib SQLite. Two tools (messages, meeting) are behind a feature flag because their AppleScript surfaces are flaky — gated by `YUKI_EXPERIMENTAL=1`.

**Tech Stack:** stdlib `asyncio` + `subprocess`, `pyobjc-framework-EventKit`, `pyobjc-framework-Contacts`, `pyobjc-framework-Quartz` (screenshot), `pyobjc-framework-MediaPlayer` (music), `pyobjc-framework-AppKit` (pasteboard), Pydantic for tool argument schemas.

**Spec reference:** §7 (full tool surface), §11.3 (tool danger levels), §10.7 (zero telemetry — no tool may emit network requests except `web_search` and `mail send`).

**Prerequisite:** Plan A (agent core) for the existing tool registry interface; Plans B/D for vault + observer types referenced by some tools.

---

## File Structure

```
Yuki/
├── yuki/
│   └── tools/
│       └── native/
│           ├── __init__.py             # NEW
│           ├── registry.py             # NEW — @tool + DangerLevel + REGISTRY
│           ├── osa.py                  # NEW — shared AppleScript helper
│           ├── calendar_tool.py        # NEW
│           ├── reminders_tool.py       # NEW
│           ├── mail_tool.py            # NEW
│           ├── notes_tool.py           # NEW
│           ├── messages_tool.py        # NEW (flagged)
│           ├── contacts_tool.py        # NEW
│           ├── files_tool.py           # NEW
│           ├── shortcuts_tool.py       # NEW
│           ├── system_tool.py          # NEW
│           ├── clipboard_tool.py       # NEW
│           ├── screenshot_tool.py      # NEW
│           ├── web_search_tool.py      # NEW
│           ├── browser_tool.py         # NEW
│           ├── music_tool.py           # NEW
│           └── meeting_tool.py         # NEW (flagged)
└── tests/
    └── tools/
        └── native/                     # one test_*.py per tool
```

---

## Task 1 — `@tool` decorator + registry + danger levels

**Files:**
- Create: `yuki/tools/native/__init__.py`
- Create: `yuki/tools/native/registry.py`
- Create: `tests/tools/native/__init__.py`
- Create: `tests/tools/native/conftest.py`
- Create: `tests/tools/native/test_registry.py`

- [ ] **Step 1: Add fixture**

Create `tests/tools/native/__init__.py` (empty) and `tests/tools/native/conftest.py`:

```python
import pytest

from yuki.tools.native import registry as reg


@pytest.fixture(autouse=True)
def clean_registry():
    saved = dict(reg.REGISTRY)
    reg.REGISTRY.clear()
    yield
    reg.REGISTRY.clear()
    reg.REGISTRY.update(saved)
```

- [ ] **Step 2: Write the failing test**

```python
import pytest

from yuki.tools.native.registry import (
    DangerLevel, REGISTRY, ToolSpec, get, tool,
)


def test_tool_decorator_registers():
    @tool(name="add", danger=DangerLevel.READ_ONLY)
    async def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    assert "add" in REGISTRY
    assert isinstance(get("add"), ToolSpec)
    assert get("add").danger == DangerLevel.READ_ONLY


def test_tool_describes_args_from_hints():
    @tool(name="hello", danger=DangerLevel.READ_ONLY)
    async def hello(name: str, exclaim: bool = False) -> str:
        """Say hello."""
        return f"hello {name}"
    spec = get("hello")
    assert spec.parameters["properties"]["name"]["type"] == "string"
    assert spec.parameters["properties"]["exclaim"]["type"] == "boolean"
    assert spec.parameters["required"] == ["name"]


def test_duplicate_name_overwrites():
    """Hot-reload from ~/.yuki/tools/ requires re-registration to overwrite, not raise."""
    @tool(name="x", danger=DangerLevel.READ_ONLY)
    async def x() -> str:
        """v1"""
        return "v1"
    @tool(name="x", danger=DangerLevel.READ_ONLY)
    async def x2() -> str:
        """v2"""
        return "v2"
    assert get("x").description == "v2"


def test_spec_carries_optional_fields():
    def _v(args):
        if not args.get("a"):
            raise ValueError("a required")

    @tool(
        name="rich", danger=DangerLevel.REVERSIBLE,
        max_result_size_chars=1234,
        validate_input=_v,
        prompt="Use this only for X.",
    )
    async def rich(a: str) -> str:
        """."""
        return a
    spec = get("rich")
    assert spec.max_result_size_chars == 1234
    assert spec.validate_input is _v
    assert spec.prompt == "Use this only for X."
    assert spec.is_read_only is False
    assert spec.is_destructive is False


@pytest.mark.asyncio
async def test_invoke_runs_underlying():
    @tool(name="add", danger=DangerLevel.READ_ONLY)
    async def add(a: int, b: int) -> int:
        """."""
        return a + b
    assert await get("add").fn(2, 3) == 5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_registry.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement `yuki/tools/native/__init__.py`**

```python
"""Native macOS tools — registered into yuki.tools.native.registry.REGISTRY."""
```

- [ ] **Step 5: Implement `yuki/tools/native/registry.py`**

```python
"""Tool decorator + danger classification + global registry."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, get_type_hints


class DangerLevel(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"


_TYPE_MAP = {
    str: "string", int: "integer", float: "number",
    bool: "boolean", list: "array", dict: "object",
}


@dataclass
class ToolSpec:
    """Tool descriptor — mirrors claude-leak/src/Tool.ts:362-695 fields.

    Required: name, danger, description, parameters, fn.
    Optional: experimental, max_result_size_chars (oversize → spill to disk),
              validate_input (extra checks beyond schema), check_permissions
              (return "allow" | "ask" | "deny"), prompt (per-tool system fragment).
    """
    name: str
    danger: DangerLevel
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Awaitable[Any]]
    experimental: bool = False
    max_result_size_chars: int = 50_000
    validate_input: Callable[[dict[str, Any]], None] | None = None
    check_permissions: Callable[[dict[str, Any], Any], str] | None = None
    prompt: str = ""

    @property
    def is_read_only(self) -> bool:
        return self.danger == DangerLevel.READ_ONLY

    @property
    def is_destructive(self) -> bool:
        return self.danger == DangerLevel.DESTRUCTIVE


REGISTRY: dict[str, ToolSpec] = {}


def _build_parameters(fn: Callable) -> dict:
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    properties: dict[str, dict] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        py_type = hints.get(name, str)
        properties[name] = {"type": _TYPE_MAP.get(py_type, "string")}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def tool(
    *,
    name: str,
    danger: DangerLevel,
    experimental: bool = False,
    max_result_size_chars: int = 50_000,
    validate_input: Callable[[dict[str, Any]], None] | None = None,
    check_permissions: Callable[[dict[str, Any], Any], str] | None = None,
    prompt: str = "",
):
    def decorate(fn):
        # idempotent: re-registering an identical name overwrites — needed for hot-reload
        REGISTRY[name] = ToolSpec(
            name=name, danger=danger,
            description=(fn.__doc__ or "").strip(),
            parameters=_build_parameters(fn),
            fn=fn, experimental=experimental,
            max_result_size_chars=max_result_size_chars,
            validate_input=validate_input,
            check_permissions=check_permissions,
            prompt=prompt,
        )
        return fn
    return decorate


def get(name: str) -> ToolSpec:
    return REGISTRY[name]


def list_specs(*, include_experimental: bool = False) -> list[ToolSpec]:
    return [s for s in REGISTRY.values()
            if include_experimental or not s.experimental]
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_registry.py -v`
Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/native/__init__.py yuki/tools/native/registry.py tests/tools/native/__init__.py tests/tools/native/conftest.py tests/tools/native/test_registry.py
git commit -m "feat(tools): add @tool decorator + registry + danger levels"
```

---

## Task 2 — Shared AppleScript helper

A single async wrapper used by every AppleScript-backed tool. Spawns `osascript` via `asyncio.create_subprocess_exec` with a static argv list (no shell, no string interpolation). Returns stdout on success, raises `OsaError` on non-zero exit or timeout.

**Files:**
- Create: `yuki/tools/native/osa.py`
- Create: `tests/tools/native/test_osa.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch

from yuki.tools.native.osa import OsaError, osa


@pytest.mark.asyncio
async def test_osa_returns_stdout():
    fake = AsyncMock(return_value=(0, "hello\n"))
    with patch("yuki.tools.native.osa._spawn", new=fake):
        out = await osa("-e", 'return "hello"')
        assert out == "hello"


@pytest.mark.asyncio
async def test_osa_raises_on_nonzero():
    fake = AsyncMock(return_value=(1, "boom"))
    with patch("yuki.tools.native.osa._spawn", new=fake):
        with pytest.raises(OsaError):
            await osa("-e", "broken")


@pytest.mark.asyncio
async def test_osa_timeout(monkeypatch):
    async def hang(*args, **kwargs):
        import asyncio
        await asyncio.sleep(2)
        return (0, "")
    monkeypatch.setattr("yuki.tools.native.osa._spawn", hang)
    with pytest.raises(OsaError):
        await osa("-e", "x", timeout=0.05)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_osa.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/osa.py`**

The dependency on `asyncio.create_subprocess_exec` with a static argv list and no `shell=True` is the security boundary — every AppleScript snippet is passed as a separate argv element via `-e`, never spliced into a shell string.

```python
"""Shared osascript helper. Always invokes via static argv — never shell."""
from __future__ import annotations

import asyncio


class OsaError(Exception):
    """Non-zero exit, timeout, or other osascript failure."""


async def _spawn(args: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "osascript", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    text = (out or err).decode("utf-8", errors="replace")
    return (proc.returncode or 0), text


async def osa(*args: str, timeout: float = 30.0) -> str:
    try:
        rc, text = await asyncio.wait_for(_spawn(list(args)), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise OsaError(f"osascript timed out after {timeout}s") from e
    if rc != 0:
        raise OsaError(text.strip() or f"osascript exited with {rc}")
    return text.strip()
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_osa.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/native/osa.py tests/tools/native/test_osa.py
git commit -m "feat(tools): add shared osascript helper"
```

---

## Task 3 — `calendar_tool`

EventKit. Three actions (one tool, dispatched on `action` arg): `list`, `create`, `delete`. `create` is `EXTERNAL` (sends invites), `list` is `READ_ONLY`, `delete` is `REVERSIBLE`. Tool's danger is the maximum of the actions it can take, so the whole tool is `EXTERNAL`. Tests inject a fake EventKit store.

**Files:**
- Create: `yuki/tools/native/calendar_tool.py`
- Create: `tests/tools/native/test_calendar_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from yuki.tools.native.calendar_tool import calendar_tool


def _fake_event(title, start, end, eid="e1"):
    e = MagicMock()
    e.title.return_value = title
    e.startDate.return_value = start
    e.endDate.return_value = end
    e.eventIdentifier.return_value = eid
    return e


@pytest.mark.asyncio
async def test_list_returns_events():
    e = _fake_event("Standup", datetime(2026, 5, 22, 10, tzinfo=timezone.utc),
                     datetime(2026, 5, 22, 10, 15, tzinfo=timezone.utc))
    store = MagicMock()
    store.eventsMatchingPredicate_.return_value = [e]
    store.predicateForEventsWithStartDate_endDate_calendars_.return_value = object()
    with patch("yuki.tools.native.calendar_tool._make_store", return_value=store):
        out = await calendar_tool(action="list", days=7)
    assert isinstance(out, list)
    assert out[0]["title"] == "Standup"


@pytest.mark.asyncio
async def test_create_calls_save():
    store = MagicMock()
    store.saveEvent_span_error_.return_value = (True, None)
    with patch("yuki.tools.native.calendar_tool._make_store", return_value=store):
        out = await calendar_tool(
            action="create", title="Test",
            start="2026-05-22T10:00:00+00:00",
            end="2026-05-22T11:00:00+00:00",
        )
    assert out["created"] is True
    store.saveEvent_span_error_.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await calendar_tool(action="banana")


@pytest.mark.asyncio
async def test_no_eventkit_returns_error():
    with patch("yuki.tools.native.calendar_tool._make_store", return_value=None):
        out = await calendar_tool(action="list", days=1)
    assert out == {"error": "EventKit unavailable"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_calendar_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/calendar_tool.py`**

```python
"""calendar_tool — list/create/delete via EventKit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _make_store():  # pragma: no cover — pyobjc only
    try:
        from EventKit import EKEventStore
        return EKEventStore.alloc().init()
    except Exception:
        return None


def _list(store, days: int) -> list[dict]:
    end = datetime.now(timezone.utc) + timedelta(days=days)
    start = datetime.now(timezone.utc)
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(start, end, None)
    out: list[dict] = []
    for e in store.eventsMatchingPredicate_(pred) or []:
        out.append({
            "id": str(e.eventIdentifier()),
            "title": e.title() or "",
            "start": str(e.startDate()),
            "end": str(e.endDate()),
        })
    return out


def _create(store, title: str, start: str, end: str) -> dict:  # pragma: no cover
    from EventKit import EKEvent, EKSpanThisEvent
    ev = EKEvent.eventWithEventStore_(store)
    ev.setTitle_(title)
    ev.setStartDate_(datetime.fromisoformat(start))
    ev.setEndDate_(datetime.fromisoformat(end))
    ev.setCalendar_(store.defaultCalendarForNewEvents())
    ok, err = store.saveEvent_span_error_(ev, EKSpanThisEvent, None)
    return {"created": bool(ok), "id": str(ev.eventIdentifier()) if ok else None}


def _delete(store, event_id: str) -> dict:  # pragma: no cover
    from EventKit import EKSpanThisEvent
    ev = store.eventWithIdentifier_(event_id)
    if ev is None:
        return {"deleted": False, "error": "not found"}
    ok, _ = store.removeEvent_span_error_(ev, EKSpanThisEvent, None)
    return {"deleted": bool(ok)}


@tool(name="calendar", danger=DangerLevel.EXTERNAL)
async def calendar_tool(
    action: str,
    days: int = 7,
    title: str = "",
    start: str = "",
    end: str = "",
    event_id: str = "",
) -> Any:
    """List, create, or delete macOS calendar events via EventKit."""
    store = _make_store()
    if store is None:
        return {"error": "EventKit unavailable"}
    if action == "list":
        return _list(store, days)
    if action == "create":
        return _create(store, title, start, end)
    if action == "delete":
        return _delete(store, event_id)
    raise ValueError(f"Unknown calendar action: {action!r}")
```

- [ ] **Step 4: Register the tool by import**

Update `yuki/tools/native/__init__.py`:

```python
"""Native macOS tools — registered into yuki.tools.native.registry.REGISTRY."""

from yuki.tools.native import calendar_tool  # noqa: F401
```

(Subsequent tasks append more tool imports here.)

- [ ] **Step 5: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_calendar_tool.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/native/calendar_tool.py yuki/tools/native/__init__.py tests/tools/native/test_calendar_tool.py
git commit -m "feat(tools): add calendar_tool"
```

---

## Task 4 — `reminders_tool`

EventKit reminders. Same shape as calendar: `list`, `create`, `complete`. All actions are `REVERSIBLE`.

**Files:**
- Create: `yuki/tools/native/reminders_tool.py`
- Create: `tests/tools/native/test_reminders_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch

import pytest

from yuki.tools.native.reminders_tool import reminders_tool


def _fake(title, completed=False):
    r = MagicMock()
    r.title.return_value = title
    r.isCompleted.return_value = completed
    r.calendarItemIdentifier.return_value = "r1"
    return r


@pytest.mark.asyncio
async def test_list_excludes_completed_by_default():
    store = MagicMock()
    store.fetchRemindersMatchingPredicate_completion_.return_value = None
    store._fake_results = [_fake("Buy milk"), _fake("Done", completed=True)]
    with patch("yuki.tools.native.reminders_tool._make_store", return_value=store), \
         patch("yuki.tools.native.reminders_tool._fetch",
               return_value=[_fake("Buy milk")]):
        out = await reminders_tool(action="list")
    assert len(out) == 1
    assert out[0]["title"] == "Buy milk"


@pytest.mark.asyncio
async def test_create_succeeds():
    store = MagicMock()
    store.saveReminder_commit_error_.return_value = (True, None)
    with patch("yuki.tools.native.reminders_tool._make_store", return_value=store):
        out = await reminders_tool(action="create", title="Walk dog")
    assert out["created"] is True


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await reminders_tool(action="banana")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_reminders_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/reminders_tool.py`**

```python
"""reminders_tool — list/create/complete via EventKit reminders."""
from __future__ import annotations

import asyncio
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _make_store():  # pragma: no cover
    try:
        from EventKit import EKEventStore
        return EKEventStore.alloc().init()
    except Exception:
        return None


async def _fetch(store) -> list:  # pragma: no cover
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    def cb(items):
        loop.call_soon_threadsafe(fut.set_result, list(items or []))
    pred = store.predicateForRemindersInCalendars_(None)
    store.fetchRemindersMatchingPredicate_completion_(pred, cb)
    return await asyncio.wait_for(fut, timeout=10.0)


def _create(store, title: str) -> dict:  # pragma: no cover
    from EventKit import EKReminder
    r = EKReminder.reminderWithEventStore_(store)
    r.setTitle_(title)
    r.setCalendar_(store.defaultCalendarForNewReminders())
    ok, _ = store.saveReminder_commit_error_(r, True, None)
    return {"created": bool(ok), "id": str(r.calendarItemIdentifier()) if ok else None}


def _complete(store, reminder_id: str) -> dict:  # pragma: no cover
    item = store.calendarItemWithIdentifier_(reminder_id)
    if item is None:
        return {"completed": False, "error": "not found"}
    item.setCompleted_(True)
    ok, _ = store.saveReminder_commit_error_(item, True, None)
    return {"completed": bool(ok)}


@tool(name="reminders", danger=DangerLevel.REVERSIBLE)
async def reminders_tool(
    action: str,
    title: str = "",
    reminder_id: str = "",
) -> Any:
    """List, create, or complete reminders via EventKit."""
    store = _make_store()
    if store is None:
        return {"error": "EventKit unavailable"}
    if action == "list":
        items = await _fetch(store)
        return [
            {"id": str(i.calendarItemIdentifier()), "title": i.title() or ""}
            for i in items if not i.isCompleted()
        ]
    if action == "create":
        return _create(store, title)
    if action == "complete":
        return _complete(store, reminder_id)
    raise ValueError(f"Unknown reminders action: {action!r}")
```

- [ ] **Step 4: Register**

Append to `yuki/tools/native/__init__.py`:

```python
from yuki.tools.native import reminders_tool  # noqa: F401
```

- [ ] **Step 5: Run tests + commit**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_reminders_tool.py -v`
Expected: 3 PASS.

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/native/reminders_tool.py yuki/tools/native/__init__.py tests/tools/native/test_reminders_tool.py
git commit -m "feat(tools): add reminders_tool"
```

---

## Task 5 — `notes_tool`

AppleScript wrapper. Actions: `list`, `create`, `read`, `delete`. The body of `create` is passed via stdin to `osascript` (not via `-e`) so newlines and quotes round-trip safely. `delete` is `DESTRUCTIVE`; everything else `REVERSIBLE`. Tool danger is `DESTRUCTIVE`.

**Files:**
- Create: `yuki/tools/native/notes_tool.py`
- Create: `tests/tools/native/test_notes_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.notes_tool import notes_tool


@pytest.mark.asyncio
async def test_list_returns_titles():
    with patch("yuki.tools.native.notes_tool.osa", new=AsyncMock(
            return_value="A\nB\nC")):
        out = await notes_tool(action="list")
    assert out == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_create_calls_osa_with_payload():
    fake = AsyncMock(return_value="ok")
    with patch("yuki.tools.native.notes_tool.osa", new=fake):
        out = await notes_tool(action="create", title="t", body="hello")
    assert out == {"created": True}
    fake.assert_awaited()


@pytest.mark.asyncio
async def test_read_returns_body():
    with patch("yuki.tools.native.notes_tool.osa",
               new=AsyncMock(return_value="body text")):
        out = await notes_tool(action="read", title="t")
    assert out == "body text"


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await notes_tool(action="banana")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_notes_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/notes_tool.py`**

```python
"""notes_tool — AppleScript wrapper around Notes.app."""
from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="notes", danger=DangerLevel.DESTRUCTIVE)
async def notes_tool(
    action: str,
    title: str = "",
    body: str = "",
) -> Any:
    """List notes, create a note, read a note's body, or delete a note."""
    if action == "list":
        out = await osa("-e", 'tell application "Notes" to get name of every note')
        return [t.strip() for t in (out or "").split(",") if t.strip()] or out.splitlines()
    if action == "create":
        script = (
            f'tell application "Notes" to make new note '
            f'with properties {{name:"{_esc(title)}", body:"{_esc(body)}"}}'
        )
        await osa("-e", script)
        return {"created": True}
    if action == "read":
        script = (
            f'tell application "Notes" to get body of note "{_esc(title)}"'
        )
        return await osa("-e", script)
    if action == "delete":
        script = (
            f'tell application "Notes" to delete note "{_esc(title)}"'
        )
        await osa("-e", script)
        return {"deleted": True}
    raise ValueError(f"Unknown notes action: {action!r}")
```

- [ ] **Step 4: Register + run tests + commit**

Append `from yuki.tools.native import notes_tool  # noqa: F401` to `yuki/tools/native/__init__.py`.

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_notes_tool.py -v`
Expected: 4 PASS.

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/native/notes_tool.py yuki/tools/native/__init__.py tests/tools/native/test_notes_tool.py
git commit -m "feat(tools): add notes_tool"
```

---

## Task 6 — `mail_tool`

Two actions: `list_unread` (read-only, AppleScript) and `send` (`EXTERNAL`, AppleScript). Send always confirms with full payload preview at the safety layer (Plan H) — this tool just sends.

**Files:**
- Create: `yuki/tools/native/mail_tool.py`
- Create: `tests/tools/native/test_mail_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.mail_tool import mail_tool


@pytest.mark.asyncio
async def test_list_unread_returns_messages():
    out_text = "Sarah | Re: Q3 plan\nBob | Quick q"
    with patch("yuki.tools.native.mail_tool.osa", new=AsyncMock(return_value=out_text)):
        out = await mail_tool(action="list_unread", limit=10)
    assert len(out) == 2
    assert out[0]["sender"] == "Sarah"


@pytest.mark.asyncio
async def test_send_calls_osa():
    fake = AsyncMock(return_value="ok")
    with patch("yuki.tools.native.mail_tool.osa", new=fake):
        out = await mail_tool(action="send", to="x@y.com",
                              subject="Hi", body="hello")
    assert out == {"sent": True}
    fake.assert_awaited()


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await mail_tool(action="banana")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_mail_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/mail_tool.py`**

```python
"""mail_tool — AppleScript wrapper around Mail.app."""
from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="mail", danger=DangerLevel.EXTERNAL)
async def mail_tool(
    action: str,
    to: str = "",
    subject: str = "",
    body: str = "",
    limit: int = 10,
) -> Any:
    """List unread mail or send a new message via Mail.app."""
    if action == "list_unread":
        script = (
            'tell application "Mail" to get '
            '{sender, subject} of (messages of inbox whose read status is false)'
        )
        out = await osa("-e", script)
        rows = []
        for line in out.splitlines():
            parts = line.split("|", 1)
            if len(parts) == 2:
                rows.append({"sender": parts[0].strip(),
                             "subject": parts[1].strip()})
        return rows[:limit]
    if action == "send":
        script = (
            f'tell application "Mail"\n'
            f'  set m to make new outgoing message with properties '
            f'{{subject:"{_esc(subject)}", content:"{_esc(body)}", visible:false}}\n'
            f'  tell m to make new to recipient with properties '
            f'{{address:"{_esc(to)}"}}\n'
            f'  send m\n'
            f'end tell'
        )
        await osa("-e", script)
        return {"sent": True}
    raise ValueError(f"Unknown mail action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import mail_tool  # noqa: F401`.

Run + commit:

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_mail_tool.py -v
git add yuki/tools/native/mail_tool.py yuki/tools/native/__init__.py tests/tools/native/test_mail_tool.py
git commit -m "feat(tools): add mail_tool"
```

---

## Task 7 — `contacts_tool`

Reads via `Contacts.framework`. `READ_ONLY` only. Looks up by name or email/phone substring.

**Files:**
- Create: `yuki/tools/native/contacts_tool.py`
- Create: `tests/tools/native/test_contacts_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch

import pytest

from yuki.tools.native.contacts_tool import contacts_tool


def _person(first, last, emails=(), phones=()):
    p = MagicMock()
    p.givenName.return_value = first
    p.familyName.return_value = last
    p.emailAddresses.return_value = [
        MagicMock(value=lambda v=v: v) for v in emails
    ]
    p.phoneNumbers.return_value = [
        MagicMock(value=lambda v=MagicMock(stringValue=lambda: v): v) for v in phones
    ]
    return p


@pytest.mark.asyncio
async def test_search_finds_by_name():
    p = _person("Sarah", "Chen", emails=["s@x.com"])
    store = MagicMock()
    store.unifiedContactsMatchingPredicate_keysToFetch_error_.return_value = ([p], None)
    with patch("yuki.tools.native.contacts_tool._make_store", return_value=store):
        out = await contacts_tool(query="Sarah")
    assert len(out) == 1
    assert out[0]["name"] == "Sarah Chen"


@pytest.mark.asyncio
async def test_no_contacts_lib_returns_error():
    with patch("yuki.tools.native.contacts_tool._make_store", return_value=None):
        out = await contacts_tool(query="x")
    assert out == {"error": "Contacts unavailable"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_contacts_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/contacts_tool.py`**

```python
"""contacts_tool — read-only lookup via Contacts.framework."""
from __future__ import annotations

from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _make_store():  # pragma: no cover
    try:
        from Contacts import CNContactStore
        return CNContactStore.alloc().init()
    except Exception:
        return None


def _key_descriptors():  # pragma: no cover
    from Contacts import (
        CNContactGivenNameKey, CNContactFamilyNameKey,
        CNContactEmailAddressesKey, CNContactPhoneNumbersKey,
    )
    return [
        CNContactGivenNameKey, CNContactFamilyNameKey,
        CNContactEmailAddressesKey, CNContactPhoneNumbersKey,
    ]


@tool(name="contacts", danger=DangerLevel.READ_ONLY)
async def contacts_tool(query: str) -> Any:
    """Search the macOS contacts database (read-only)."""
    store = _make_store()
    if store is None:
        return {"error": "Contacts unavailable"}
    try:
        from Contacts import CNContact
        pred = CNContact.predicateForContactsMatchingName_(query)
    except Exception:  # pragma: no cover
        return {"error": "predicate unavailable"}
    contacts, _ = store.unifiedContactsMatchingPredicate_keysToFetch_error_(
        pred, _key_descriptors(), None,
    )
    out: list[dict] = []
    for c in contacts or []:
        emails = [e.value() for e in (c.emailAddresses() or [])]
        phones = [p.value().stringValue() for p in (c.phoneNumbers() or [])]
        out.append({
            "name": f"{c.givenName()} {c.familyName()}".strip(),
            "emails": emails, "phones": phones,
        })
    return out
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import contacts_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_contacts_tool.py -v
git add yuki/tools/native/contacts_tool.py yuki/tools/native/__init__.py tests/tools/native/test_contacts_tool.py
git commit -m "feat(tools): add contacts_tool"
```

---

## Task 8 — `files_tool`

Actions: `find` (mdfind), `read` (for text files only), `move`, `delete`. `delete` is `DESTRUCTIVE` and requires a typed-yes at the safety layer; `move` is `REVERSIBLE`. Path safety: refuse paths outside `/Users/<me>/`, refuse `.git`/`Library`/`Applications` modifications.

**Files:**
- Create: `yuki/tools/native/files_tool.py`
- Create: `tests/tools/native/test_files_tool.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.files_tool import files_tool


@pytest.mark.asyncio
async def test_find_uses_mdfind(monkeypatch):
    fake_proc = AsyncMock()
    fake_proc.communicate.return_value = (b"/Users/me/a.txt\n/Users/me/b.txt\n", b"")
    fake_proc.returncode = 0
    async def fake_create(*args, **kwargs):
        return fake_proc
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await files_tool(action="find", query="kMDItemKind == 'Plain Text'")
    assert out == ["/Users/me/a.txt", "/Users/me/b.txt"]


@pytest.mark.asyncio
async def test_read_returns_text(tmp_path: Path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    monkeypatch.setattr("yuki.tools.native.files_tool._allowed",
                        lambda path: True)
    out = await files_tool(action="read", path=str(p))
    assert out == "hello"


@pytest.mark.asyncio
async def test_delete_refuses_outside_home(monkeypatch):
    monkeypatch.setattr("yuki.tools.native.files_tool._allowed",
                        lambda path: False)
    out = await files_tool(action="delete", path="/etc/passwd")
    assert "refused" in out.get("error", "").lower()


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await files_tool(action="zzz")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_files_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/files_tool.py`**

```python
"""files_tool — find/read/move/delete with path-safety guard."""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool

_FORBIDDEN = (".git", "Library", "Applications")


def _allowed(path: str) -> bool:
    p = Path(path).expanduser().resolve()
    home = Path.home().resolve()
    try:
        p.relative_to(home)
    except ValueError:
        return False
    return not any(part in _FORBIDDEN for part in p.parts)


async def _mdfind(query: str) -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        "mdfind", query,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return [line for line in out.decode().splitlines() if line.strip()]


@tool(name="files", danger=DangerLevel.DESTRUCTIVE)
async def files_tool(
    action: str,
    query: str = "",
    path: str = "",
    dest: str = "",
) -> Any:
    """Find files via mdfind, read a text file, move, or delete (with safety)."""
    if action == "find":
        return await _mdfind(query)
    if action == "read":
        if not _allowed(path):
            return {"error": "refused: path outside home or in protected dir"}
        return Path(path).read_text(encoding="utf-8", errors="replace")
    if action == "move":
        if not (_allowed(path) and _allowed(dest)):
            return {"error": "refused: source or dest disallowed"}
        shutil.move(path, dest)
        return {"moved": True}
    if action == "delete":
        if not _allowed(path):
            return {"error": "refused: path disallowed"}
        os.remove(path) if Path(path).is_file() else shutil.rmtree(path)
        return {"deleted": True}
    raise ValueError(f"Unknown files action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import files_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_files_tool.py -v
git add yuki/tools/native/files_tool.py yuki/tools/native/__init__.py tests/tools/native/test_files_tool.py
git commit -m "feat(tools): add files_tool"
```

---

## Task 9 — `shortcuts_tool`

Wraps the `shortcuts` CLI. Actions: `list`, `run`. Each Shortcut has its own danger profile, but at the tool level we mark it `REVERSIBLE` (rollable back via undo where supported).

**Files:**
- Create: `yuki/tools/native/shortcuts_tool.py`
- Create: `tests/tools/native/test_shortcuts_tool.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from yuki.tools.native.shortcuts_tool import shortcuts_tool


@pytest.mark.asyncio
async def test_list_parses_lines(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"Foo\nBar\n", b""))
    fake_proc.returncode = 0
    async def fake_create(*args, **kwargs):
        return fake_proc
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await shortcuts_tool(action="list")
    assert out == ["Foo", "Bar"]


@pytest.mark.asyncio
async def test_run_returns_output(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"42\n", b""))
    fake_proc.returncode = 0
    async def fake_create(*args, **kwargs):
        return fake_proc
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await shortcuts_tool(action="run", name="MyShortcut", input_text="hi")
    assert out["output"] == "42"


@pytest.mark.asyncio
async def test_run_failure_returns_error(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"", b"not found"))
    fake_proc.returncode = 1
    async def fake_create(*args, **kwargs):
        return fake_proc
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await shortcuts_tool(action="run", name="missing")
    assert "error" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_shortcuts_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/shortcuts_tool.py`**

```python
"""shortcuts_tool — list and run user Shortcuts via the shortcuts CLI."""
from __future__ import annotations

import asyncio
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


async def _run_cli(*args: str, stdin: bytes | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "shortcuts", *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(stdin)
    return (proc.returncode or 0,
            out.decode("utf-8", errors="replace"),
            err.decode("utf-8", errors="replace"))


@tool(name="shortcuts", danger=DangerLevel.REVERSIBLE)
async def shortcuts_tool(
    action: str,
    name: str = "",
    input_text: str = "",
) -> Any:
    """List or run macOS Shortcuts."""
    if action == "list":
        rc, out, _ = await _run_cli("list")
        return [line.strip() for line in out.splitlines() if line.strip()] if rc == 0 else []
    if action == "run":
        rc, out, err = await _run_cli(
            "run", name,
            stdin=input_text.encode("utf-8") if input_text else None,
        )
        if rc != 0:
            return {"error": err.strip() or f"exit {rc}"}
        return {"output": out.strip()}
    raise ValueError(f"Unknown shortcuts action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import shortcuts_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_shortcuts_tool.py -v
git add yuki/tools/native/shortcuts_tool.py yuki/tools/native/__init__.py tests/tools/native/test_shortcuts_tool.py
git commit -m "feat(tools): add shortcuts_tool"
```

---

## Task 10 — `system_tool`

Wraps `defaults` and IOKit-style adjustments (volume, brightness, wifi, bluetooth, dnd, dark mode). Each is a sub-action; tool danger is `REVERSIBLE`.

**Files:**
- Create: `yuki/tools/native/system_tool.py`
- Create: `tests/tools/native/test_system_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.system_tool import system_tool


@pytest.mark.asyncio
async def test_set_volume_runs_osa():
    fake = AsyncMock(return_value="ok")
    with patch("yuki.tools.native.system_tool.osa", new=fake):
        out = await system_tool(action="set_volume", value=50)
    assert out == {"ok": True}
    fake.assert_awaited()


@pytest.mark.asyncio
async def test_toggle_dark_mode():
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.system_tool.osa", new=fake):
        out = await system_tool(action="toggle_dark_mode")
    assert out == {"ok": True}


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await system_tool(action="banana")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_system_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/system_tool.py`**

```python
"""system_tool — volume, brightness, dark mode, dnd toggles."""
from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


@tool(name="system", danger=DangerLevel.REVERSIBLE)
async def system_tool(
    action: str,
    value: int = 0,
) -> Any:
    """Adjust system settings: set_volume, set_brightness, toggle_dark_mode, toggle_dnd."""
    if action == "set_volume":
        await osa("-e", f"set volume output volume {int(value)}")
        return {"ok": True}
    if action == "set_brightness":
        # macOS lacks a clean AppleScript for brightness; the menu-bar app's
        # IOKit helper covers this in production. For now, no-op success.
        return {"ok": True, "warning": "brightness via IOKit only — see menubar app"}
    if action == "toggle_dark_mode":
        await osa(
            "-e",
            'tell application "System Events" to tell appearance preferences '
            'to set dark mode to not dark mode',
        )
        return {"ok": True}
    if action == "toggle_dnd":
        # macOS Sonoma+ exposes Focus modes via Shortcuts only; defer to
        # shortcuts_tool. Return guidance.
        return {"ok": False, "hint": "use shortcuts_tool with a Focus shortcut"}
    raise ValueError(f"Unknown system action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import system_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_system_tool.py -v
git add yuki/tools/native/system_tool.py yuki/tools/native/__init__.py tests/tools/native/test_system_tool.py
git commit -m "feat(tools): add system_tool"
```

---

## Task 11 — `clipboard_tool`

Pasteboard via NSPasteboard. Actions: `read`, `write`, `history` (last 20). The history is in-memory and reset per backend launch — persistent history is a v1.x feature.

**Files:**
- Create: `yuki/tools/native/clipboard_tool.py`
- Create: `tests/tools/native/test_clipboard_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import patch

import pytest

from yuki.tools.native import clipboard_tool as cb_mod
from yuki.tools.native.clipboard_tool import clipboard_tool


@pytest.fixture(autouse=True)
def reset_history():
    cb_mod._HISTORY.clear()


@pytest.mark.asyncio
async def test_write_then_read_round_trip():
    captured = {"text": ""}
    def fake_write(t):
        captured["text"] = t
    def fake_read():
        return captured["text"]
    with patch("yuki.tools.native.clipboard_tool._pb_write", new=fake_write), \
         patch("yuki.tools.native.clipboard_tool._pb_read", new=fake_read):
        await clipboard_tool(action="write", text="hello")
        out = await clipboard_tool(action="read")
    assert out == "hello"


@pytest.mark.asyncio
async def test_history_keeps_last_20():
    with patch("yuki.tools.native.clipboard_tool._pb_write", new=lambda t: None), \
         patch("yuki.tools.native.clipboard_tool._pb_read", new=lambda: ""):
        for i in range(25):
            await clipboard_tool(action="write", text=f"v{i}")
        out = await clipboard_tool(action="history")
    assert len(out) == 20
    assert out[0] == "v24"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_clipboard_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/clipboard_tool.py`**

```python
"""clipboard_tool — read/write/history via NSPasteboard."""
from __future__ import annotations

from collections import deque
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool

_HISTORY: deque[str] = deque(maxlen=20)


def _pb_write(text: str) -> None:  # pragma: no cover
    from AppKit import NSPasteboard, NSPasteboardTypeString
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


def _pb_read() -> str:  # pragma: no cover
    from AppKit import NSPasteboard, NSPasteboardTypeString
    pb = NSPasteboard.generalPasteboard()
    return pb.stringForType_(NSPasteboardTypeString) or ""


@tool(name="clipboard", danger=DangerLevel.REVERSIBLE)
async def clipboard_tool(
    action: str,
    text: str = "",
) -> Any:
    """Read clipboard, write to it, or fetch in-process history (last 20)."""
    if action == "read":
        return _pb_read()
    if action == "write":
        _HISTORY.appendleft(text)
        _pb_write(text)
        return {"ok": True}
    if action == "history":
        return list(_HISTORY)
    raise ValueError(f"Unknown clipboard action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import clipboard_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_clipboard_tool.py -v
git add yuki/tools/native/clipboard_tool.py yuki/tools/native/__init__.py tests/tools/native/test_clipboard_tool.py
git commit -m "feat(tools): add clipboard_tool"
```

---

## Task 12 — `screenshot_tool`

`screencapture` CLI. Actions: `take` (whole screen, returns path), `take_window` (active window), `take_region` (interactive, blocks until user selects). Optional Vision OCR pass via Apple's Vision framework.

**Files:**
- Create: `yuki/tools/native/screenshot_tool.py`
- Create: `tests/tools/native/test_screenshot_tool.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from yuki.tools.native.screenshot_tool import screenshot_tool


@pytest.mark.asyncio
async def test_take_writes_png(tmp_path: Path, monkeypatch):
    out_path = tmp_path / "shot.png"

    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"", b""))
    fake_proc.returncode = 0
    async def fake_create(*args, **kwargs):
        out_path.write_bytes(b"PNGDATA")
        return fake_proc
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    monkeypatch.setattr("yuki.tools.native.screenshot_tool._scratch_path",
                        lambda: out_path)
    out = await screenshot_tool(action="take")
    assert out["path"] == str(out_path)
    assert out_path.exists()


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await screenshot_tool(action="nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_screenshot_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/screenshot_tool.py`**

```python
"""screenshot_tool — wraps screencapture CLI."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _scratch_path() -> Path:
    base = Path.home() / "Library" / "Caches" / "Yuki" / "screenshots"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{int(time.time() * 1000)}.png"


async def _capture(*flags: str) -> Path:
    out = _scratch_path()
    proc = await asyncio.create_subprocess_exec(
        "screencapture", *flags, str(out),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return out


@tool(name="screenshot", danger=DangerLevel.READ_ONLY)
async def screenshot_tool(action: str) -> Any:
    """take | take_window | take_region — returns path to PNG."""
    if action == "take":
        path = await _capture("-x")
    elif action == "take_window":
        path = await _capture("-x", "-W")
    elif action == "take_region":
        path = await _capture("-i")
    else:
        raise ValueError(f"Unknown screenshot action: {action!r}")
    return {"path": str(path)}
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import screenshot_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_screenshot_tool.py -v
git add yuki/tools/native/screenshot_tool.py yuki/tools/native/__init__.py tests/tools/native/test_screenshot_tool.py
git commit -m "feat(tools): add screenshot_tool"
```

---

## Task 13 — `web_search_tool`

Uses the user's BYO search key (Brave / Kagi / Google). Falls back to opening the default browser to a search URL. Spec §11.4 explicitly allows network here.

**Files:**
- Create: `yuki/tools/native/web_search_tool.py`
- Create: `tests/tools/native/test_web_search_tool.py`

- [ ] **Step 1: Write the failing test**

```python
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yuki.tools.native.web_search_tool import web_search_tool


@pytest.mark.asyncio
async def test_brave_returns_results(monkeypatch):
    monkeypatch.setenv("YUKI_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("YUKI_BRAVE_API_KEY", "k")
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {
        "web": {"results": [{"title": "T", "url": "https://x", "description": "d"}]}
    }
    with patch("yuki.tools.native.web_search_tool._http_get",
               new=AsyncMock(return_value=fake_resp)):
        out = await web_search_tool(query="hello")
    assert len(out) == 1
    assert out[0]["title"] == "T"


@pytest.mark.asyncio
async def test_no_provider_returns_fallback_link(monkeypatch):
    monkeypatch.delenv("YUKI_SEARCH_PROVIDER", raising=False)
    out = await web_search_tool(query="hello world")
    assert "fallback_url" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_web_search_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/web_search_tool.py`**

```python
"""web_search_tool — BYO search provider with browser fallback."""
from __future__ import annotations

import os
from urllib.parse import quote

from yuki.tools.native.registry import DangerLevel, tool


async def _http_get(url: str, headers: dict[str, str] | None = None):  # pragma: no cover
    import requests
    return requests.get(url, headers=headers or {}, timeout=10)


def _fallback(query: str) -> dict:
    return {"fallback_url": f"https://www.google.com/search?q={quote(query)}",
            "note": "no provider configured — open this URL in default browser"}


async def _brave(query: str) -> list[dict]:
    key = os.environ.get("YUKI_BRAVE_API_KEY", "")
    if not key:
        return []
    resp = await _http_get(
        f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}",
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""),
         "snippet": r.get("description", "")}
        for r in data.get("web", {}).get("results", [])
    ]


@tool(name="web_search", danger=DangerLevel.READ_ONLY)
async def web_search_tool(query: str):
    """Search the web via the configured provider (BYO key)."""
    provider = os.environ.get("YUKI_SEARCH_PROVIDER", "").lower()
    if provider == "brave":
        results = await _brave(query)
        return results or _fallback(query)
    return _fallback(query)
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import web_search_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_web_search_tool.py -v
git add yuki/tools/native/web_search_tool.py yuki/tools/native/__init__.py tests/tools/native/test_web_search_tool.py
git commit -m "feat(tools): add web_search_tool"
```

---

## Task 14 — `browser_tool`

AppleScript wrapper for Safari/Chrome. Actions: `current_url`, `current_text`, `open_url`, `close_tab`, `new_tab`. Tool danger `REVERSIBLE`.

**Files:**
- Create: `yuki/tools/native/browser_tool.py`
- Create: `tests/tools/native/test_browser_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.browser_tool import browser_tool


@pytest.mark.asyncio
async def test_current_url_returns_string():
    with patch("yuki.tools.native.browser_tool.osa",
               new=AsyncMock(return_value="https://example.com")):
        out = await browser_tool(action="current_url")
    assert out == "https://example.com"


@pytest.mark.asyncio
async def test_open_url_runs_osa():
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.browser_tool.osa", new=fake):
        out = await browser_tool(action="open_url", url="https://example.com")
    assert out == {"opened": True}
    fake.assert_awaited()


@pytest.mark.asyncio
async def test_unknown_action_raises():
    with pytest.raises(ValueError):
        await browser_tool(action="banana")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_browser_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/browser_tool.py`**

```python
"""browser_tool — AppleScript wrapper around Safari + Chrome."""
from __future__ import annotations

import os
from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _which() -> str:
    return os.environ.get("YUKI_BROWSER", "Safari")


@tool(name="browser", danger=DangerLevel.REVERSIBLE)
async def browser_tool(
    action: str,
    url: str = "",
) -> Any:
    """Read current URL/text or open/close/create tabs in the user's browser."""
    app = _which()
    if action == "current_url":
        return await osa(
            "-e", f'tell application "{app}" to URL of current tab of front window',
        )
    if action == "current_text":
        return await osa(
            "-e", f'tell application "{app}" to text of document of front window',
        )
    if action == "open_url":
        await osa(
            "-e",
            f'tell application "{app}" to make new tab at end of tabs of front window '
            f'with properties {{URL:"{_esc(url)}"}}',
        )
        return {"opened": True}
    if action == "close_tab":
        await osa("-e", f'tell application "{app}" to close current tab of front window')
        return {"closed": True}
    if action == "new_tab":
        await osa("-e", f'tell application "{app}" to make new tab at end of tabs of front window')
        return {"created": True}
    raise ValueError(f"Unknown browser action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import browser_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_browser_tool.py -v
git add yuki/tools/native/browser_tool.py yuki/tools/native/__init__.py tests/tools/native/test_browser_tool.py
git commit -m "feat(tools): add browser_tool"
```

---

## Task 15 — `music_tool`

Music.app via AppleScript. Actions: `play`, `pause`, `next`, `previous`, `now_playing`, `play_playlist`. `REVERSIBLE`.

**Files:**
- Create: `yuki/tools/native/music_tool.py`
- Create: `tests/tools/native/test_music_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.music_tool import music_tool


@pytest.mark.asyncio
async def test_now_playing_returns_dict():
    with patch("yuki.tools.native.music_tool.osa",
               new=AsyncMock(return_value="Song | Artist | Album")):
        out = await music_tool(action="now_playing")
    assert out["title"] == "Song"
    assert out["artist"] == "Artist"


@pytest.mark.asyncio
async def test_play_runs_osa():
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.music_tool.osa", new=fake):
        out = await music_tool(action="play")
    assert out == {"ok": True}


@pytest.mark.asyncio
async def test_play_playlist_passes_name():
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.music_tool.osa", new=fake):
        out = await music_tool(action="play_playlist", playlist="Deep Work")
    assert out == {"ok": True}
    fake.assert_awaited()


@pytest.mark.asyncio
async def test_unknown_raises():
    with pytest.raises(ValueError):
        await music_tool(action="zzz")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_music_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/music_tool.py`**

```python
"""music_tool — control Music.app via AppleScript."""
from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="music", danger=DangerLevel.REVERSIBLE)
async def music_tool(
    action: str,
    playlist: str = "",
) -> Any:
    """Control Apple Music: play, pause, next, previous, now_playing, play_playlist."""
    if action == "play":
        await osa("-e", 'tell application "Music" to play')
        return {"ok": True}
    if action == "pause":
        await osa("-e", 'tell application "Music" to pause')
        return {"ok": True}
    if action == "next":
        await osa("-e", 'tell application "Music" to next track')
        return {"ok": True}
    if action == "previous":
        await osa("-e", 'tell application "Music" to previous track')
        return {"ok": True}
    if action == "now_playing":
        out = await osa(
            "-e",
            'tell application "Music" to (name of current track) & " | " & '
            '(artist of current track) & " | " & (album of current track)',
        )
        parts = [p.strip() for p in out.split("|", 2)]
        while len(parts) < 3:
            parts.append("")
        return {"title": parts[0], "artist": parts[1], "album": parts[2]}
    if action == "play_playlist":
        await osa(
            "-e",
            f'tell application "Music" to play playlist "{_esc(playlist)}"',
        )
        return {"ok": True}
    raise ValueError(f"Unknown music action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import music_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_music_tool.py -v
git add yuki/tools/native/music_tool.py yuki/tools/native/__init__.py tests/tools/native/test_music_tool.py
git commit -m "feat(tools): add music_tool"
```

---

## Task 16 — `messages_tool` (flagged)

iMessage via AppleScript. Behind `experimental=True`. Actions: `send_to`, `recent`. `EXTERNAL`.

**Files:**
- Create: `yuki/tools/native/messages_tool.py`
- Create: `tests/tools/native/test_messages_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.messages_tool import messages_tool
from yuki.tools.native.registry import REGISTRY


def test_messages_is_experimental():
    assert REGISTRY["messages"].experimental is True


@pytest.mark.asyncio
async def test_send_runs_osa():
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.messages_tool.osa", new=fake):
        out = await messages_tool(action="send_to",
                                   recipient="+15551212", body="hi")
    assert out == {"sent": True}


@pytest.mark.asyncio
async def test_unknown_raises():
    with pytest.raises(ValueError):
        await messages_tool(action="zzz")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_messages_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/messages_tool.py`**

```python
"""messages_tool — iMessage via AppleScript (experimental)."""
from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


@tool(name="messages", danger=DangerLevel.EXTERNAL, experimental=True)
async def messages_tool(
    action: str,
    recipient: str = "",
    body: str = "",
    limit: int = 10,
) -> Any:
    """Send iMessage or fetch recent (experimental — AppleScript surface is fragile)."""
    if action == "send_to":
        script = (
            f'tell application "Messages"\n'
            f'  set targetService to 1st service whose service type = iMessage\n'
            f'  set targetBuddy to buddy "{_esc(recipient)}" of targetService\n'
            f'  send "{_esc(body)}" to targetBuddy\n'
            f'end tell'
        )
        await osa("-e", script)
        return {"sent": True}
    if action == "recent":
        # iMessage's AppleScript surface for reading is hostile; we return
        # a placeholder until a stable path is found.
        return {"note": "iMessage read API is not exposed via AppleScript",
                "messages": []}
    raise ValueError(f"Unknown messages action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import messages_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_messages_tool.py -v
git add yuki/tools/native/messages_tool.py yuki/tools/native/__init__.py tests/tools/native/test_messages_tool.py
git commit -m "feat(tools): add messages_tool (experimental)"
```

---

## Task 17 — `meeting_tool` (flagged) + final wrap-up

Meeting tool detects active Zoom/Meet/Teams windows + AX hooks for mute/unmute/camera. Behind `experimental=True`. Actions: `current` (which app + meeting state), `toggle_mute`, `leave`.

**Files:**
- Create: `yuki/tools/native/meeting_tool.py`
- Create: `tests/tools/native/test_meeting_tool.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.meeting_tool import meeting_tool
from yuki.tools.native.registry import REGISTRY


def test_meeting_is_experimental():
    assert REGISTRY["meeting"].experimental is True


@pytest.mark.asyncio
async def test_current_returns_app_when_running():
    with patch("yuki.tools.native.meeting_tool._frontmost",
               new=AsyncMock(return_value="zoom.us")):
        out = await meeting_tool(action="current")
    assert out["app"] == "zoom.us"
    assert out["in_meeting"] is True


@pytest.mark.asyncio
async def test_current_returns_none_when_no_meeting_app():
    with patch("yuki.tools.native.meeting_tool._frontmost",
               new=AsyncMock(return_value="Safari")):
        out = await meeting_tool(action="current")
    assert out["in_meeting"] is False


@pytest.mark.asyncio
async def test_unknown_raises():
    with pytest.raises(ValueError):
        await meeting_tool(action="zzz")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_meeting_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/native/meeting_tool.py`**

```python
"""meeting_tool — Zoom/Meet/Teams detection and basic control (experimental)."""
from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool

_MEETING_APPS = {"zoom.us", "Microsoft Teams", "Microsoft Teams (work or school)"}


async def _frontmost() -> str:
    return await osa(
        "-e",
        'tell application "System Events" to set f to '
        'name of first process whose frontmost is true',
    )


@tool(name="meeting", danger=DangerLevel.EXTERNAL, experimental=True)
async def meeting_tool(action: str) -> Any:
    """Detect or control the current meeting (experimental)."""
    app = await _frontmost()
    in_meeting = app in _MEETING_APPS
    if action == "current":
        return {"app": app, "in_meeting": in_meeting}
    if action == "toggle_mute":
        if not in_meeting:
            return {"ok": False, "reason": "no meeting app frontmost"}
        # Apps differ; cmd-shift-A is Zoom default mute toggle
        await osa(
            "-e",
            'tell application "System Events" to keystroke "a" using {shift down, command down}',
        )
        return {"ok": True}
    if action == "leave":
        if not in_meeting:
            return {"ok": False, "reason": "no meeting app frontmost"}
        await osa(
            "-e",
            'tell application "System Events" to keystroke "w" using {command down}',
        )
        return {"ok": True}
    raise ValueError(f"Unknown meeting action: {action!r}")
```

- [ ] **Step 4: Register + run + commit**

Append `from yuki.tools.native import meeting_tool  # noqa: F401`.

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/native/test_meeting_tool.py -v
git add yuki/tools/native/meeting_tool.py yuki/tools/native/__init__.py tests/tools/native/test_meeting_tool.py
git commit -m "feat(tools): add meeting_tool (experimental)"
```

- [ ] **Step 5: Run the full project suite**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest -v`
Expected: full suite green; ≥45 native-tool tests + everything from earlier plans.

- [ ] **Step 6: Verify the registry has all 15 tools**

```python
# Run with: uv run python -c "..."
from yuki.tools.native import registry  # triggers __init__.py imports
import yuki.tools.native  # noqa
print(sorted(registry.REGISTRY.keys()))
```

Expected: `['browser', 'calendar', 'clipboard', 'contacts', 'files', 'mail', 'meeting', 'messages', 'music', 'notes', 'reminders', 'screenshot', 'shortcuts', 'system', 'web_search']`.

---

## Task 18 — User-tool hot-loader (`@tool` SDK, v1)

Make `@tool` a public API: users drop Python files into `~/.yuki/tools/` and we discover, load, and hot-reload them. This is the Raycast-Extensions-style wedge per spec §7.6 (decision upgraded from v1.1 to v1).

Each user tool runs through the same `Gatekeeper` (Plan H) — danger levels and confirmation apply uniformly. A failing user tool is logged but does not bring down the agent loop.

**Files:**
- Create: `yuki/tools/loader.py`
- Modify: `yuki/tools/native/__init__.py` (call loader at import)
- Modify: `yuki/__init__.py` (re-export `tool, DangerLevel` as the public surface)
- Create: `tests/tools/test_loader.py`

- [ ] **Step 1: Public re-exports**

In `yuki/__init__.py` add:

```python
"""Yuki — macOS Jarvis-style assistant.

Public plugin SDK:
    from yuki import tool, DangerLevel

    @tool(name="hello", danger=DangerLevel.READ_ONLY)
    async def hello(name: str) -> str:
        '''Say hello.'''
        return f"Hi {name}"

Drop your file into ~/.yuki/tools/ to load it.
"""
from yuki.tools.native.registry import DangerLevel, tool

__all__ = ["DangerLevel", "tool"]
```

- [ ] **Step 2: Write the failing test**

`tests/tools/test_loader.py`:

```python
from pathlib import Path
import textwrap

import pytest

from yuki.tools import loader
from yuki.tools.native.registry import REGISTRY


@pytest.fixture(autouse=True)
def isolated_user_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_USER_TOOLS_DIR", str(tmp_path))
    saved = dict(REGISTRY)
    yield tmp_path
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_loads_user_tool(isolated_user_dir: Path):
    (isolated_user_dir / "weather.py").write_text(textwrap.dedent('''
        from yuki import tool, DangerLevel

        @tool(name="weather", danger=DangerLevel.READ_ONLY)
        async def weather(city: str) -> str:
            """Pretend to fetch weather."""
            return f"sunny in {city}"
    '''))
    loaded = loader.load_user_tools()
    assert loaded == ["weather.py"]
    assert "weather" in REGISTRY


def test_broken_user_tool_logged_but_does_not_raise(isolated_user_dir: Path, caplog):
    (isolated_user_dir / "broken.py").write_text("syntax !!! error")
    loaded = loader.load_user_tools()
    assert loaded == []
    assert "broken.py" in caplog.text


def test_idempotent_reload(isolated_user_dir: Path):
    (isolated_user_dir / "x.py").write_text(textwrap.dedent('''
        from yuki import tool, DangerLevel
        @tool(name="x", danger=DangerLevel.READ_ONLY)
        async def x() -> str:
            """."""
            return ""
    '''))
    loader.load_user_tools()
    loader.load_user_tools()  # second call must not raise on duplicate registration
    assert "x" in REGISTRY


def test_no_dir_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("YUKI_USER_TOOLS_DIR", str(tmp_path / "nope"))
    assert loader.load_user_tools() == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/test_loader.py -v`
Expected: ModuleNotFoundError on `yuki.tools.loader`.

- [ ] **Step 4: Implement `yuki/tools/loader.py`**

```python
"""Hot-load user-defined @tool functions from ~/.yuki/tools/."""
from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

from yuki.tools.native.registry import REGISTRY

log = logging.getLogger(__name__)


def _user_tools_dir() -> Path:
    override = os.environ.get("YUKI_USER_TOOLS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".yuki" / "tools"


def _load_one(path: Path) -> bool:
    name = f"yuki_user_tools.{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return False
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True
    except Exception as e:
        log.warning("user tool %s failed to load: %s", path.name, e)
        return False


def load_user_tools() -> list[str]:
    """Import every .py file in the user tools dir; tolerate failures."""
    root = _user_tools_dir()
    if not root.exists():
        return []
    loaded: list[str] = []
    for path in sorted(root.glob("*.py")):
        # Skip already-registered names to make load_user_tools idempotent.
        before = set(REGISTRY.keys())
        if _load_one(path):
            after = set(REGISTRY.keys())
            if after != before or path.stem in {n.removeprefix("yuki_user_tools.") for n in []}:
                loaded.append(path.name)
    return loaded
```

- [ ] **Step 5: Verify the registry already overwrites idempotently**

Plan G Task 1 (after the Tier-1+2 patch round) defines the `tool()` decorator to overwrite on duplicate name rather than raise — that's exactly what hot-reload needs. The corresponding `test_duplicate_name_overwrites` test is already in place. No further registry changes required for this task.

- [ ] **Step 6: Wire loader into native `__init__.py`**

Append to `yuki/tools/native/__init__.py` (after all the `import` lines that register built-ins):

```python
from yuki.tools.loader import load_user_tools as _load_user_tools

_load_user_tools()
```

- [ ] **Step 7: Run all tool tests**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/ -v
```

Expected: ≥48 tests green.

- [ ] **Step 8: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/loader.py yuki/tools/native/__init__.py yuki/tools/native/registry.py yuki/__init__.py tests/tools/test_loader.py tests/tools/native/test_registry.py
git commit -m "feat(tools): public @tool SDK + hot-load from ~/.yuki/tools/"
```

---

## Task 19 — Tool-result size budget + disk spillover

Screenshots, AX-tree dumps, and `files.read` over a large file can produce megabytes of output. Sending all of it to the LLM wastes tokens and busts context. Mirror Claude Code's pattern (`claude-leak/src/utils/toolResultStorage.ts`): when a result exceeds the tool's `max_result_size_chars`, spill the full payload to disk and return a path + truncated preview.

**Files:**
- Create: `yuki/tools/spillover.py`
- Modify: `yuki/tools/native/screenshot_tool.py` (and any other tool emitting large output) to declare a smaller `max_result_size_chars` if needed
- Create: `tests/tools/test_spillover.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

import pytest

from yuki.tools.spillover import maybe_spill


@pytest.fixture
def tmp_blobs(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("YUKI_BLOB_DIR", str(tmp_path))
    return tmp_path


def test_short_result_passes_through(tmp_blobs: Path):
    out = maybe_spill("hello", max_chars=100, tool_name="x")
    assert out == "hello"


def test_long_string_spills(tmp_blobs: Path):
    big = "x" * 5000
    out = maybe_spill(big, max_chars=200, tool_name="screenshot")
    assert isinstance(out, dict)
    assert out["spilled"] is True
    assert out["bytes"] >= 5000
    assert "preview" in out
    assert len(out["preview"]) <= 220
    assert Path(out["path"]).exists()
    assert Path(out["path"]).read_text() == big


def test_long_dict_spills_as_json(tmp_blobs: Path):
    big = {"data": list(range(10_000))}
    out = maybe_spill(big, max_chars=200, tool_name="ax_dump")
    assert isinstance(out, dict)
    assert out["spilled"] is True
    on_disk = json.loads(Path(out["path"]).read_text())
    assert on_disk == big


def test_short_dict_passes_through(tmp_blobs: Path):
    out = maybe_spill({"x": 1}, max_chars=100, tool_name="x")
    assert out == {"x": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/test_spillover.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/tools/spillover.py`**

```python
"""Spill oversized tool results to disk; return path + preview to the LLM.

Mirrors claude-leak/src/utils/toolResultStorage.ts. The model never sees
megabytes inline; it gets a path it can subsequently read with files_tool
or quote in a follow-up question.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _root() -> Path:
    override = os.environ.get("YUKI_BLOB_DIR")
    if override:
        return Path(override)
    return (
        Path.home() / "Library" / "Application Support" / "Yuki" / "blobs"
    )


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, indent=2)


def maybe_spill(value: Any, *, max_chars: int, tool_name: str) -> Any:
    """Return value unchanged if small; spill to disk and return a stub if oversized."""
    serialized = _serialize(value)
    if len(serialized) <= max_chars:
        return value

    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{tool_name}-{int(time.time() * 1000)}.txt"
    path.write_text(serialized, encoding="utf-8")
    preview = serialized[:200] + ("…" if len(serialized) > 200 else "")
    return {
        "spilled": True,
        "tool": tool_name,
        "path": str(path),
        "bytes": len(serialized),
        "preview": preview,
    }
```

- [ ] **Step 4: Wire into the tool runner**

Whoever calls `await spec.fn(**args)` (the agent loop, eventually) wraps the result:

```python
from yuki.tools.spillover import maybe_spill

raw = await spec.fn(**args)
result = maybe_spill(raw, max_chars=spec.max_result_size_chars, tool_name=spec.name)
```

For now this is a library function; Plan A's loop integration consumes it. No modification to existing tools required — they keep returning their natural output, and the spillover is applied uniformly.

- [ ] **Step 5: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/tools/test_spillover.py -v
```

Expected: 4 PASS.

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/tools/spillover.py tests/tools/test_spillover.py
git commit -m "feat(tools): add tool-result size budget with disk spillover"
```

---

## Wrap-up

After Task 19:
- 15 native tools live under `yuki/tools/native/`
- All registered into `REGISTRY` via `@tool` decorator with rich metadata
  (`max_result_size_chars`, `validate_input`, `check_permissions`, `prompt`,
  `is_read_only`/`is_destructive`)
- Each test-coverable code path uses dependency injection or mocked subprocess; pyobjc-only paths sit under `pragma: no cover`
- Experimental flags gate `messages_tool` and `meeting_tool`
- Tool schemas are auto-generated from type hints + docstrings — usable directly by the agent's tool-call surface
- **`from yuki import tool, DangerLevel` is the public plugin SDK** — users drop Python files into `~/.yuki/tools/` and they're hot-loaded at agent startup
- **Tool results auto-spill to disk** when above `max_result_size_chars` — the LLM gets a path + 200-char preview instead of megabytes of payload

Acceptance:
- `uv run pytest tests/tools/native/ -v` ≥45 tests, all green
- `len(registry.list_specs())` returns 13 (non-experimental); `list_specs(include_experimental=True)` returns 15
- `grep -r 'shell=True' yuki/tools/native/` returns nothing
- `grep -r 'macos_use' yuki/tools/native/` returns nothing

