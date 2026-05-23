# Plan H — Safety & Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the safety layer that wraps every native-tool call (Plan G) and every UI-tool call (Plan A) with confirmation, danger-level gating, trusted-routine bypass, and burst-mode override. After this plan, no tool can execute without consent except `READ_ONLY` ones.

**Architecture:** A single `Gatekeeper` object owns confirmation state. It exposes `await gate(spec, args)` which (1) reads the tool's `DangerLevel`, (2) checks burst-mode, (3) checks active trusted-routine context, (4) calls a `Confirmer` (pluggable: console for tests, SwiftUI bridge in production), (5) returns approve/deny/payload-modified. The agent's tool-execution loop calls `Gatekeeper.gate()` before every tool call. Trusted-routine state is persisted as a marker on routine notes (Plan B's `RoutineNote.trusted = True`). Burst mode is a 30-second timer started by long-press of the global hotkey (Plan J).

**Tech Stack:** stdlib `asyncio`, Pydantic (Plan B), `pytest-asyncio`.

**Spec reference:** §7.5 (full danger-level + confirmation + escape valves), §11.3 (action safety), §11.2 (audit log of every executed action).

**Prerequisite:** Plans A (agent core), B (RoutineNote schema), G (DangerLevel + ToolSpec).

---

## File Structure

```
Yuki/
├── yuki/
│   └── safety/
│       ├── __init__.py                 # NEW — exports Gatekeeper, Decision, Confirmer
│       ├── decision.py                 # NEW — Decision dataclass + reasons enum
│       ├── confirmer.py                # NEW — Confirmer protocol + InMemoryConfirmer
│       ├── trusted.py                  # NEW — TrustedRoutineRegistry
│       ├── burst.py                    # NEW — BurstMode timer
│       ├── audit.py                    # NEW — append every executed action to vault episode
│       └── gatekeeper.py               # NEW — main entry point
└── tests/
    └── safety/
        ├── __init__.py
        ├── conftest.py
        ├── test_decision.py
        ├── test_confirmer.py
        ├── test_trusted.py
        ├── test_burst.py
        ├── test_audit.py
        └── test_gatekeeper.py
```

---

## Task 1 — `Decision` + `Confirmer` protocol

**Files:**
- Create: `yuki/safety/__init__.py`
- Create: `yuki/safety/decision.py`
- Create: `yuki/safety/confirmer.py`
- Create: `tests/safety/__init__.py`
- Create: `tests/safety/conftest.py`
- Create: `tests/safety/test_decision.py`
- Create: `tests/safety/test_confirmer.py`

- [ ] **Step 1: Add empty fixtures**

Create `tests/safety/__init__.py` (empty) and `tests/safety/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def tmp_safety_env(tmp_path: Path, monkeypatch) -> Path:
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    (vault / "60-Episodes").mkdir(parents=True)
    return vault
```

- [ ] **Step 2: Write the failing test for Decision**

`tests/safety/test_decision.py`:

```python
from yuki.safety.decision import Decision, Reason


def test_approve_default_payload():
    d = Decision.approve(payload={"x": 1})
    assert d.approved is True
    assert d.payload == {"x": 1}
    assert d.reason == Reason.USER


def test_deny_carries_reason():
    d = Decision.deny(reason=Reason.SAFETY_FORBIDDEN)
    assert d.approved is False
    assert d.reason == Reason.SAFETY_FORBIDDEN


def test_modified_payload_round_trip():
    d = Decision.approve(payload={"to": "x@y", "subject": "edited"},
                         reason=Reason.USER_EDITED)
    assert d.payload["subject"] == "edited"
    assert d.reason == Reason.USER_EDITED
```

- [ ] **Step 3: Write the failing test for Confirmer**

`tests/safety/test_confirmer.py`:

```python
import pytest

from yuki.safety.confirmer import InMemoryConfirmer
from yuki.safety.decision import Decision, Reason


@pytest.mark.asyncio
async def test_in_memory_returns_queued_decision():
    c = InMemoryConfirmer(responses=[
        Decision.approve(payload={"x": 1}),
        Decision.deny(reason=Reason.USER),
    ])
    a = await c.ask(tool_name="t", args={}, danger="reversible", preview="p")
    b = await c.ask(tool_name="t", args={}, danger="reversible", preview="p")
    assert a.approved is True
    assert b.approved is False


@pytest.mark.asyncio
async def test_in_memory_default_approves():
    c = InMemoryConfirmer()
    decision = await c.ask(tool_name="t", args={}, danger="reversible", preview="p")
    assert decision.approved is True


@pytest.mark.asyncio
async def test_records_history():
    c = InMemoryConfirmer()
    await c.ask(tool_name="calendar", args={"action": "list"},
                danger="read_only", preview="")
    assert c.asked == [("calendar", {"action": "list"}, "read_only", "")]
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_decision.py tests/safety/test_confirmer.py -v`
Expected: ModuleNotFoundError × 2.

- [ ] **Step 5: Implement `yuki/safety/__init__.py`**

```python
"""Safety subsystem: confirmation, trusted routines, burst mode, audit."""
```

- [ ] **Step 6: Implement `yuki/safety/decision.py`**

```python
"""Decision — the result of a confirmation check."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Reason(str, Enum):
    USER = "user"
    USER_EDITED = "user_edited"
    AUTO_READ_ONLY = "auto_read_only"
    AUTO_TRUSTED_ROUTINE = "auto_trusted_routine"
    AUTO_BURST_MODE = "auto_burst_mode"
    SAFETY_FORBIDDEN = "safety_forbidden"


@dataclass
class Decision:
    approved: bool
    payload: dict[str, Any] = field(default_factory=dict)
    reason: Reason = Reason.USER

    @classmethod
    def approve(
        cls, payload: dict[str, Any] | None = None,
        reason: Reason = Reason.USER,
    ) -> "Decision":
        return cls(approved=True, payload=dict(payload or {}), reason=reason)

    @classmethod
    def deny(cls, reason: Reason = Reason.USER) -> "Decision":
        return cls(approved=False, payload={}, reason=reason)
```

- [ ] **Step 7: Implement `yuki/safety/confirmer.py`**

```python
"""Confirmer protocol + an in-memory implementation for tests."""
from __future__ import annotations

from typing import Any, Protocol

from yuki.safety.decision import Decision


class Confirmer(Protocol):
    async def ask(
        self,
        tool_name: str,
        args: dict[str, Any],
        danger: str,
        preview: str,
    ) -> Decision: ...


class InMemoryConfirmer:
    def __init__(self, responses: list[Decision] | None = None) -> None:
        self._responses = list(responses or [])
        self.asked: list[tuple[str, dict, str, str]] = []

    async def ask(
        self, tool_name: str, args: dict, danger: str, preview: str,
    ) -> Decision:
        self.asked.append((tool_name, dict(args), danger, preview))
        if self._responses:
            return self._responses.pop(0)
        return Decision.approve(payload=dict(args))
```

- [ ] **Step 8: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_decision.py tests/safety/test_confirmer.py -v`
Expected: 6 PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/safety/ tests/safety/__init__.py tests/safety/conftest.py tests/safety/test_decision.py tests/safety/test_confirmer.py
git commit -m "feat(safety): add Decision + Confirmer protocol"
```

---

## Task 2 — `TrustedRoutineRegistry`

A trusted routine: when active, `REVERSIBLE` tools auto-approve; `EXTERNAL` and `DESTRUCTIVE` always re-confirm. Tracks success counts per routine id (in `00-Identity/trusted-routines.md` markdown for transparency). After 5 consecutive successful runs, asks user once if the routine should be marked trusted.

**Files:**
- Create: `yuki/safety/trusted.py`
- Create: `tests/safety/test_trusted.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.schemas import RoutineNote
from yuki.memory.vault import Vault
from yuki.safety.trusted import TrustedRoutineRegistry


def _routine(slug, trusted=False) -> RoutineNote:
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    return RoutineNote(
        id=f"routine-{slug}", type="routine", created_at=now, updated_at=now,
        confidence=0.9, source=["scan"], name=slug.title(),
        schedule="weekdays 9am", steps=[], trusted=trusted,
    )


def test_is_trusted_returns_false_when_not_active(tmp_safety_env: Path):
    reg = TrustedRoutineRegistry()
    assert reg.is_active() is False


def test_enter_makes_routine_active(tmp_safety_env: Path):
    v = Vault()
    v.write(_routine("morning", trusted=True), body="")
    reg = TrustedRoutineRegistry()
    reg.enter("routine-morning")
    assert reg.is_active() is True
    assert reg.current_id() == "routine-morning"


def test_enter_untrusted_routine_is_noop(tmp_safety_env: Path):
    v = Vault()
    v.write(_routine("untrusted", trusted=False), body="")
    reg = TrustedRoutineRegistry()
    reg.enter("routine-untrusted")
    assert reg.is_active() is False


def test_record_success_then_propose_trust(tmp_safety_env: Path):
    v = Vault()
    v.write(_routine("morning", trusted=False), body="")
    reg = TrustedRoutineRegistry()
    for _ in range(4):
        assert reg.record_success("routine-morning") is False
    assert reg.record_success("routine-morning") is True


def test_exit_clears_active(tmp_safety_env: Path):
    v = Vault()
    v.write(_routine("morning", trusted=True), body="")
    reg = TrustedRoutineRegistry()
    reg.enter("routine-morning")
    reg.exit()
    assert reg.is_active() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_trusted.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/safety/trusted.py`**

```python
"""Trusted-routine registry — in-process active routine + success counter."""
from __future__ import annotations

from collections import defaultdict

from yuki.memory.schemas import RoutineNote
from yuki.memory.vault import Vault, VaultError

_PROPOSE_THRESHOLD = 5


class TrustedRoutineRegistry:
    def __init__(self) -> None:
        self._active_id: str | None = None
        self._successes: dict[str, int] = defaultdict(int)

    def enter(self, routine_id: str) -> None:
        v = Vault()
        try:
            note, _ = v.read(routine_id)
        except VaultError:
            return
        if not isinstance(note, RoutineNote) or not note.trusted:
            return
        self._active_id = routine_id

    def exit(self) -> None:
        self._active_id = None

    def is_active(self) -> bool:
        return self._active_id is not None

    def current_id(self) -> str | None:
        return self._active_id

    def record_success(self, routine_id: str) -> bool:
        """Record one success; return True if the proposal threshold was just crossed."""
        self._successes[routine_id] += 1
        return self._successes[routine_id] == _PROPOSE_THRESHOLD
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_trusted.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/safety/trusted.py tests/safety/test_trusted.py
git commit -m "feat(safety): add TrustedRoutineRegistry"
```

---

## Task 3 — `BurstMode`

30-second timer started by the menu-bar app on long-press of `⌘⇧Y`. Exposes `is_active()`. The gate auto-approves `REVERSIBLE` (only) while active.

**Files:**
- Create: `yuki/safety/burst.py`
- Create: `tests/safety/test_burst.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio

import pytest

from yuki.safety.burst import BurstMode


@pytest.mark.asyncio
async def test_initial_inactive():
    b = BurstMode()
    assert b.is_active() is False


@pytest.mark.asyncio
async def test_engage_active_for_duration():
    b = BurstMode()
    b.engage(duration=0.05)
    assert b.is_active() is True
    await asyncio.sleep(0.1)
    assert b.is_active() is False


@pytest.mark.asyncio
async def test_re_engage_extends():
    b = BurstMode()
    b.engage(duration=0.05)
    await asyncio.sleep(0.03)
    b.engage(duration=0.1)
    await asyncio.sleep(0.05)
    assert b.is_active() is True


@pytest.mark.asyncio
async def test_disengage_immediate():
    b = BurstMode()
    b.engage(duration=10)
    b.disengage()
    assert b.is_active() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_burst.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/safety/burst.py`**

```python
"""BurstMode — short-lived auto-approve window for reversible actions."""
from __future__ import annotations

import time


class BurstMode:
    def __init__(self) -> None:
        self._active_until: float = 0.0

    def engage(self, duration: float = 30.0) -> None:
        self._active_until = max(self._active_until, time.monotonic() + duration)

    def disengage(self) -> None:
        self._active_until = 0.0

    def is_active(self) -> bool:
        return time.monotonic() < self._active_until
```

- [ ] **Step 4: Run tests + commit**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_burst.py -v`
Expected: 4 PASS.

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/safety/burst.py tests/safety/test_burst.py
git commit -m "feat(safety): add BurstMode"
```

---

## Task 4 — Action audit log

Every executed action — approved by user, auto-approved by trusted routine, or auto-approved by burst — is appended to `60-Episodes/actions-YYYY-MM-DD.md`.

**Files:**
- Create: `yuki/safety/audit.py`
- Create: `tests/safety/test_audit.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from pathlib import Path

from yuki.safety.audit import append_action_audit


def test_writes_to_dated_file(tmp_safety_env: Path):
    append_action_audit(
        tool_name="calendar", args={"action": "list"},
        danger="read_only", reason="auto_read_only",
        ts=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    out = tmp_safety_env / "60-Episodes" / "actions-2026-05-22.md"
    assert out.exists()
    text = out.read_text()
    assert "calendar" in text
    assert "auto_read_only" in text


def test_appends_multiple(tmp_safety_env: Path):
    base = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
    for i in range(3):
        append_action_audit(
            tool_name=f"t{i}", args={}, danger="reversible",
            reason="user", ts=base,
        )
    out = (tmp_safety_env / "60-Episodes" / "actions-2026-05-22.md").read_text()
    assert "t0" in out and "t1" in out and "t2" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_audit.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/safety/audit.py`**

```python
"""Action audit — append every executed tool call to a daily episode file."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from yuki.memory import paths


def append_action_audit(
    *,
    tool_name: str,
    args: dict[str, Any],
    danger: str,
    reason: str,
    ts: datetime,
) -> None:
    out_dir = paths.vault_dir() / "60-Episodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    day = ts.date().isoformat()
    path = out_dir / f"actions-{day}.md"
    line = (
        f"- {ts.isoformat()} | {tool_name} | {danger} | {reason} | "
        f"{json.dumps(args, default=str)}\n"
    )
    if not path.exists():
        path.write_text(f"# Action audit — {day}\n\n{line}", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
```

- [ ] **Step 4: Run tests + commit**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_audit.py -v`
Expected: 2 PASS.

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/safety/audit.py tests/safety/test_audit.py
git commit -m "feat(safety): add action audit log"
```

---

## Task 5 — `Gatekeeper`

The main entry point. The agent's tool runner calls `await gatekeeper.gate(spec, args)` and the result is a `Decision`. Implements the matrix:

| Danger      | Active trusted routine | Burst | Default |
|-------------|------------------------|-------|---------|
| read_only   | auto                   | auto  | auto    |
| reversible  | auto                   | auto  | confirm |
| external    | confirm                | confirm | confirm |
| destructive | confirm (typed yes)    | confirm (typed yes) | confirm (typed yes) |

After execution, the caller calls `gatekeeper.record_executed(spec, args, decision)` to write the audit row.

**Files:**
- Create: `yuki/safety/gatekeeper.py`
- Modify: `yuki/safety/__init__.py`
- Create: `tests/safety/test_gatekeeper.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yuki.memory.schemas import RoutineNote
from yuki.memory.vault import Vault
from yuki.safety.burst import BurstMode
from yuki.safety.confirmer import InMemoryConfirmer
from yuki.safety.decision import Decision, Reason
from yuki.safety.gatekeeper import Gatekeeper
from yuki.safety.trusted import TrustedRoutineRegistry
from yuki.tools.native.registry import DangerLevel, ToolSpec


def _spec(name: str, danger: DangerLevel) -> ToolSpec:
    async def fn(**kwargs):
        return None
    return ToolSpec(
        name=name, danger=danger, description="", parameters={}, fn=fn,
    )


@pytest.mark.asyncio
async def test_read_only_auto_approves(tmp_safety_env: Path):
    g = Gatekeeper(confirmer=InMemoryConfirmer(),
                   trusted=TrustedRoutineRegistry(), burst=BurstMode())
    d = await g.gate(_spec("calendar", DangerLevel.READ_ONLY), {"action": "list"})
    assert d.approved is True
    assert d.reason == Reason.AUTO_READ_ONLY


@pytest.mark.asyncio
async def test_reversible_default_confirms(tmp_safety_env: Path):
    confirmer = InMemoryConfirmer(responses=[Decision.deny()])
    g = Gatekeeper(confirmer=confirmer,
                   trusted=TrustedRoutineRegistry(), burst=BurstMode())
    d = await g.gate(_spec("notes", DangerLevel.REVERSIBLE), {"action": "delete"})
    assert d.approved is False


@pytest.mark.asyncio
async def test_reversible_in_burst_auto_approves(tmp_safety_env: Path):
    burst = BurstMode()
    burst.engage(duration=10)
    g = Gatekeeper(confirmer=InMemoryConfirmer(),
                   trusted=TrustedRoutineRegistry(), burst=burst)
    d = await g.gate(_spec("notes", DangerLevel.REVERSIBLE), {"x": 1})
    assert d.approved is True
    assert d.reason == Reason.AUTO_BURST_MODE


@pytest.mark.asyncio
async def test_reversible_in_trusted_routine_auto_approves(tmp_safety_env: Path):
    v = Vault()
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    v.write(RoutineNote(
        id="routine-x", type="routine", created_at=now, updated_at=now,
        confidence=1.0, source=[], name="X", schedule="?", steps=[], trusted=True,
    ), body="")
    trusted = TrustedRoutineRegistry()
    trusted.enter("routine-x")
    g = Gatekeeper(confirmer=InMemoryConfirmer(), trusted=trusted, burst=BurstMode())
    d = await g.gate(_spec("notes", DangerLevel.REVERSIBLE), {})
    assert d.approved is True
    assert d.reason == Reason.AUTO_TRUSTED_ROUTINE


@pytest.mark.asyncio
async def test_external_always_confirms_even_in_trusted(tmp_safety_env: Path):
    v = Vault()
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    v.write(RoutineNote(
        id="routine-x", type="routine", created_at=now, updated_at=now,
        confidence=1.0, source=[], name="X", schedule="?", steps=[], trusted=True,
    ), body="")
    trusted = TrustedRoutineRegistry()
    trusted.enter("routine-x")
    confirmer = InMemoryConfirmer(responses=[Decision.deny()])
    g = Gatekeeper(confirmer=confirmer, trusted=trusted, burst=BurstMode())
    d = await g.gate(_spec("mail", DangerLevel.EXTERNAL), {"to": "x"})
    assert d.approved is False


@pytest.mark.asyncio
async def test_record_executed_writes_audit(tmp_safety_env: Path):
    g = Gatekeeper(confirmer=InMemoryConfirmer(),
                   trusted=TrustedRoutineRegistry(), burst=BurstMode())
    spec = _spec("notes", DangerLevel.REVERSIBLE)
    d = Decision.approve(payload={"x": 1}, reason=Reason.USER)
    g.record_executed(spec, {"x": 1}, d)
    files = list((tmp_safety_env / "60-Episodes").glob("actions-*.md"))
    assert len(files) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_gatekeeper.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/safety/gatekeeper.py`**

```python
"""Gatekeeper — danger-level gate + trusted-routine + burst + audit."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from yuki.safety.audit import append_action_audit
from yuki.safety.burst import BurstMode
from yuki.safety.confirmer import Confirmer
from yuki.safety.decision import Decision, Reason
from yuki.safety.trusted import TrustedRoutineRegistry
from yuki.tools.native.registry import DangerLevel, ToolSpec


def _preview(spec: ToolSpec, args: dict[str, Any]) -> str:
    return f"{spec.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"


class Gatekeeper:
    def __init__(
        self,
        confirmer: Confirmer,
        trusted: TrustedRoutineRegistry,
        burst: BurstMode,
    ) -> None:
        self._confirmer = confirmer
        self._trusted = trusted
        self._burst = burst

    async def gate(self, spec: ToolSpec, args: dict[str, Any]) -> Decision:
        danger = spec.danger
        if danger == DangerLevel.READ_ONLY:
            return Decision.approve(payload=dict(args), reason=Reason.AUTO_READ_ONLY)

        if danger == DangerLevel.REVERSIBLE:
            if self._trusted.is_active():
                return Decision.approve(
                    payload=dict(args), reason=Reason.AUTO_TRUSTED_ROUTINE,
                )
            if self._burst.is_active():
                return Decision.approve(
                    payload=dict(args), reason=Reason.AUTO_BURST_MODE,
                )

        # external + destructive always ask; reversible asks if no escape valve.
        return await self._confirmer.ask(
            tool_name=spec.name, args=dict(args),
            danger=danger.value, preview=_preview(spec, args),
        )

    def record_executed(
        self, spec: ToolSpec, args: dict[str, Any], decision: Decision,
    ) -> None:
        if not decision.approved:
            return
        append_action_audit(
            tool_name=spec.name, args=args,
            danger=spec.danger.value, reason=decision.reason.value,
            ts=datetime.now(timezone.utc),
        )
```

- [ ] **Step 4: Update `yuki/safety/__init__.py`**

```python
"""Safety subsystem."""

from yuki.safety.burst import BurstMode
from yuki.safety.confirmer import Confirmer, InMemoryConfirmer
from yuki.safety.decision import Decision, Reason
from yuki.safety.gatekeeper import Gatekeeper
from yuki.safety.trusted import TrustedRoutineRegistry

__all__ = [
    "BurstMode", "Confirmer", "Decision", "Gatekeeper",
    "InMemoryConfirmer", "Reason", "TrustedRoutineRegistry",
]
```

- [ ] **Step 5: Run all safety tests + full suite**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/ -v
cd /Users/mafex/code/personal/Yuki && uv run pytest -v
```

Expected: all green; ≥20 safety tests + everything else.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/safety/gatekeeper.py yuki/safety/__init__.py tests/safety/test_gatekeeper.py
git commit -m "feat(safety): add Gatekeeper with danger matrix + escape valves"
```

---

## Task 6 — Allow-rules + tool `check_permissions` integration

The current Gatekeeper is binary: approve or deny. Real users want "remember this" — a one-time approval that persists for the session, the project, or forever. Mirrors `claude-leak/src/Tool.ts`'s `checkPermissions(input, ctx) → "allow" | "ask" | "deny"` with three-scope allow-rules (session / project / user).

**Files:**
- Create: `yuki/safety/allow_rules.py`
- Modify: `yuki/safety/gatekeeper.py` (consult allow-rules + tool's `check_permissions`)
- Create: `tests/safety/test_allow_rules.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

import pytest

from yuki.safety.allow_rules import AllowRules


@pytest.fixture
def tmp_rules_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("YUKI_ALLOW_RULES_DIR", str(tmp_path))
    return tmp_path


def test_session_rule_only_persists_in_memory(tmp_rules_dir: Path):
    r = AllowRules(session_id="s1")
    r.allow(tool_name="mail", scope="session")
    assert r.is_allowed(tool_name="mail") is True
    assert not (tmp_rules_dir / "user.json").exists()


def test_user_rule_writes_to_disk(tmp_rules_dir: Path):
    r = AllowRules(session_id="s1")
    r.allow(tool_name="calendar", scope="user")
    data = json.loads((tmp_rules_dir / "user.json").read_text())
    assert "calendar" in data["tools"]


def test_user_rule_loaded_on_init(tmp_rules_dir: Path):
    r = AllowRules(session_id="s1")
    r.allow(tool_name="reminders", scope="user")
    r2 = AllowRules(session_id="s2")  # different session, fresh instance
    assert r2.is_allowed(tool_name="reminders") is True


def test_revoke_user_rule(tmp_rules_dir: Path):
    r = AllowRules(session_id="s1")
    r.allow(tool_name="x", scope="user")
    r.revoke(tool_name="x", scope="user")
    assert r.is_allowed(tool_name="x") is False


def test_per_arg_scoping(tmp_rules_dir: Path):
    """Allow `files.read` on ~/code only, not arbitrary paths."""
    r = AllowRules(session_id="s1")
    r.allow(tool_name="files", scope="session", args_match={"action": "read"})
    assert r.is_allowed(tool_name="files", args={"action": "read", "path": "/x"}) is True
    assert r.is_allowed(tool_name="files", args={"action": "delete", "path": "/x"}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/test_allow_rules.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/safety/allow_rules.py`**

```python
"""Three-scope allow-rules: session (in-memory) / project (per-cwd) / user (global).

Mirrors Claude Code's allow-rules system. The Gatekeeper consults this BEFORE
asking the Confirmer; if any rule matches, the action auto-approves with a
"remembered" reason in the audit log.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

Scope = Literal["session", "project", "user"]


def _user_path() -> Path:
    override = os.environ.get("YUKI_ALLOW_RULES_DIR")
    if override:
        return Path(override) / "user.json"
    return (
        Path.home() / "Library" / "Application Support" / "Yuki" / "allow-rules" / "user.json"
    )


def _project_path() -> Path:
    override = os.environ.get("YUKI_ALLOW_RULES_DIR")
    cwd = Path.cwd().resolve()
    safe = str(cwd).replace("/", "_")
    if override:
        return Path(override) / f"project-{safe}.json"
    return (
        Path.home() / "Library" / "Application Support" / "Yuki" / "allow-rules" / f"project-{safe}.json"
    )


def _matches(args_match: dict | None, args: dict | None) -> bool:
    if not args_match:
        return True
    if not args:
        return False
    return all(args.get(k) == v for k, v in args_match.items())


class AllowRules:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._session: list[dict] = []
        self._user: list[dict] = self._load(_user_path())
        self._project: list[dict] = self._load(_project_path())

    def _load(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        return list(data.get("tools", []))

    def _save(self, path: Path, rules: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tools": rules}, indent=2), encoding="utf-8")

    def allow(
        self, *, tool_name: str, scope: Scope,
        args_match: dict[str, Any] | None = None,
    ) -> None:
        rule = {"tool": tool_name, "args_match": args_match}
        if scope == "session":
            self._session.append(rule)
        elif scope == "user":
            self._user.append(rule)
            self._save(_user_path(), self._user)
        elif scope == "project":
            self._project.append(rule)
            self._save(_project_path(), self._project)

    def revoke(
        self, *, tool_name: str, scope: Scope,
        args_match: dict[str, Any] | None = None,
    ) -> None:
        target = {"tool": tool_name, "args_match": args_match}
        if scope == "session":
            self._session = [r for r in self._session if r != target]
        elif scope == "user":
            self._user = [r for r in self._user if r != target]
            self._save(_user_path(), self._user)
        elif scope == "project":
            self._project = [r for r in self._project if r != target]
            self._save(_project_path(), self._project)

    def is_allowed(
        self, *, tool_name: str, args: dict[str, Any] | None = None,
    ) -> bool:
        for rules in (self._session, self._project, self._user):
            for rule in rules:
                if rule["tool"] != tool_name:
                    continue
                if _matches(rule.get("args_match"), args):
                    return True
        return False
```

- [ ] **Step 4: Wire into `Gatekeeper`**

Update `yuki/safety/gatekeeper.py`:

```python
# add import:
from yuki.safety.allow_rules import AllowRules


class Gatekeeper:
    def __init__(
        self,
        confirmer: Confirmer,
        trusted: TrustedRoutineRegistry,
        burst: BurstMode,
        allow_rules: AllowRules | None = None,
    ) -> None:
        self._confirmer = confirmer
        self._trusted = trusted
        self._burst = burst
        self._allow_rules = allow_rules or AllowRules(session_id="default")

    async def gate(self, spec: ToolSpec, args: dict[str, Any]) -> Decision:
        # 1. Tool's own check_permissions takes priority.
        if spec.check_permissions is not None:
            verdict = spec.check_permissions(args, None)
            if verdict == "deny":
                return Decision.deny(reason=Reason.SAFETY_FORBIDDEN)
            if verdict == "allow":
                return Decision.approve(payload=dict(args), reason=Reason.AUTO_READ_ONLY)
            # "ask" → fall through

        # 2. Existing read-only auto-approve.
        if spec.danger == DangerLevel.READ_ONLY:
            return Decision.approve(payload=dict(args), reason=Reason.AUTO_READ_ONLY)

        # 3. Allow-rules (session/project/user).
        if self._allow_rules.is_allowed(tool_name=spec.name, args=args):
            return Decision.approve(payload=dict(args), reason=Reason.USER)

        # 4. Existing escape valves (trusted routine, burst mode).
        if spec.danger == DangerLevel.REVERSIBLE:
            if self._trusted.is_active():
                return Decision.approve(payload=dict(args), reason=Reason.AUTO_TRUSTED_ROUTINE)
            if self._burst.is_active():
                return Decision.approve(payload=dict(args), reason=Reason.AUTO_BURST_MODE)

        # 5. Otherwise ask the user.
        return await self._confirmer.ask(
            tool_name=spec.name, args=dict(args),
            danger=spec.danger.value, preview=_preview(spec, args),
        )
```

- [ ] **Step 5: Update `__init__.py` to export `AllowRules`**

In `yuki/safety/__init__.py`, add `AllowRules` to imports and `__all__`.

- [ ] **Step 6: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/safety/ -v
```

Expected: ≥25 PASS (allow_rules: 5, plus everything earlier).

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/safety/allow_rules.py yuki/safety/gatekeeper.py yuki/safety/__init__.py tests/safety/test_allow_rules.py
git commit -m "feat(safety): allow/ask/deny + scoped allow-rules + tool check_permissions"
```

---

## Wrap-up

After Task 5, the safety subsystem is ready for the agent runtime to wrap every tool call:

```python
# Pseudocode of how the agent runtime (Plan A continuation) will use it:
spec = registry.get(tool_call.name)
decision = await gatekeeper.gate(spec, tool_call.args)
if not decision.approved:
    raise PermissionDenied(decision.reason)
result = await spec.fn(**decision.payload)
gatekeeper.record_executed(spec, decision.payload, decision)
```

Acceptance:
- `uv run pytest tests/safety/ -v` ≥20 tests, all green
- Reading the gatekeeper code makes it obvious that `EXTERNAL` and `DESTRUCTIVE` cannot be auto-approved by any escape valve
- `actions-YYYY-MM-DD.md` accumulates one row per executed tool call with full args + reason

