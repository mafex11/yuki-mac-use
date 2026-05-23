# Plan A — Vendor & Integrate Agent Core (MacOS-Use Fork) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor MacOS-Use's agent + ax + providers + messages + tool subsystems into Yuki's `yuki/` package under our own namespace, strip telemetry entirely, default to Anthropic Claude Sonnet 4.6, and prove the agent loop runs end-to-end with a stub LLM via tests.

**Architecture:** A one-time copy from `/Users/mafex/code/personal/MacOS-Use/macos_use/` into `/Users/mafex/code/personal/Yuki/yuki/`, namespace-rewriting all `from macos_use...` imports to `from yuki...`, deleting the `telemetry/` package and its 8 call sites, bumping the default model, and adding a stub LLM provider for tests. After this plan, `from yuki.agent import Agent` works and an integration test drives one full loop iteration with a fake LLM that returns a `done_tool` call.

**Tech Stack:** All MacOS-Use deps (PyObjC, anthropic, openai, google-genai, groq, ollama, cerebras, mistralai, litellm, pillow, pydantic, requests, rich, tabulate, markdownify, uuid7), plus `pytest-mock` for the stub LLM tests.

**Spec reference:** `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` §2 (foundation: fork MacOS-Use), §3.2 (module layout — `yuki/agent/`, `yuki/ax/`), §10.7 (zero telemetry), §11.4 (no network without reason).

**Prerequisite:** Plan A0 must be complete — `Yuki/` is a git repo with `pyproject.toml`, `uv` env, pytest passing.

---

## Why namespace-rewrite instead of `pip install macos-use`

Two reasons:

1. **We will diverge.** Spec §11 calls for changes inside the agent loop (vault hot-context injection, prompt-cache wiring, message-history pruning) and the system prompt. Pinning a published version blocks our roadmap.
2. **License + ownership.** MIT lets us vendor; we keep upstream copyright headers but the code becomes ours to evolve without coordinating with upstream.

Trade-off: when MacOS-Use ships an upstream improvement (e.g. better LoopGuard), we cherry-pick by hand instead of `uv lock --upgrade`. Acceptable.

---

## File Structure

After this plan:

```
Yuki/
├── pyproject.toml                       # MODIFIED — adds runtime deps
├── yuki/
│   ├── __init__.py                      # MODIFIED — exports Agent
│   ├── agent/                           # COPIED from macos_use/agent/, namespaced
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── service.py                   # MODIFIED — telemetry stripped
│   │   ├── loop.py
│   │   ├── views.py
│   │   ├── context/
│   │   ├── desktop/
│   │   ├── events/
│   │   ├── prompt/
│   │   ├── registry/
│   │   ├── tools/
│   │   ├── tree/
│   │   └── watchdog/
│   ├── ax/                              # COPIED from macos_use/ax/
│   ├── messages/                        # COPIED from macos_use/messages/
│   ├── providers/                       # COPIED from macos_use/providers/, sans events.py untouched
│   │   ├── base.py
│   │   ├── anthropic/
│   │   │   └── llm.py                   # MODIFIED — default model = claude-sonnet-4-6
│   │   ├── openai/
│   │   ├── google/
│   │   ├── ... (all 13 providers)
│   │   └── stub/                        # NEW — fake LLM for tests
│   │       ├── __init__.py
│   │       └── llm.py
│   └── tools/                           # COPIED from macos_use/tool/ (renamed plural)
└── tests/
    ├── test_smoke.py                    # DELETED (Plan A0 throwaway)
    ├── conftest.py                      # MODIFIED — adds shared fixtures
    └── agent/
        ├── __init__.py
        ├── test_imports.py              # NEW — every public surface imports
        └── test_agent_loop_with_stub.py # NEW — one full loop iteration
```

The full `macos_use/telemetry/` package is **not** copied. The 8 call sites in `agent/service.py` are deleted (not stubbed) — the goal is that `grep -r telemetry yuki/` returns nothing.

---

## Task 1 — Copy MacOS-Use into yuki/ (raw, before namespace rewrite)

**Files:**
- Copy: `/Users/mafex/code/personal/MacOS-Use/macos_use/agent/` → `/Users/mafex/code/personal/Yuki/yuki/agent/`
- Copy: `/Users/mafex/code/personal/MacOS-Use/macos_use/ax/` → `/Users/mafex/code/personal/Yuki/yuki/ax/`
- Copy: `/Users/mafex/code/personal/MacOS-Use/macos_use/messages/` → `/Users/mafex/code/personal/Yuki/yuki/messages/`
- Copy: `/Users/mafex/code/personal/MacOS-Use/macos_use/providers/` → `/Users/mafex/code/personal/Yuki/yuki/providers/`
- Copy: `/Users/mafex/code/personal/MacOS-Use/macos_use/tool/` → `/Users/mafex/code/personal/Yuki/yuki/tools/` (renamed plural to match spec §3.2 + downstream plan B–G imports)
- Do NOT copy: `/Users/mafex/code/personal/MacOS-Use/macos_use/telemetry/`

- [ ] **Step 1: Verify the source repo state**

```bash
ls /Users/mafex/code/personal/MacOS-Use/macos_use/
```
Expected: `agent  ax  __init__.py  messages  providers  telemetry  tool`. If anything is missing, stop and ask the user.

- [ ] **Step 2: Confirm the Yuki repo is on a clean working tree**

```bash
cd /Users/mafex/code/personal/Yuki
git status
```
Expected: working tree clean (after Plan A0). If dirty, stop.

- [ ] **Step 3: Copy the five subsystems**

```bash
cd /Users/mafex/code/personal/Yuki
cp -R /Users/mafex/code/personal/MacOS-Use/macos_use/agent yuki/agent
cp -R /Users/mafex/code/personal/MacOS-Use/macos_use/ax yuki/ax
cp -R /Users/mafex/code/personal/MacOS-Use/macos_use/messages yuki/messages
cp -R /Users/mafex/code/personal/MacOS-Use/macos_use/providers yuki/providers
cp -R /Users/mafex/code/personal/MacOS-Use/macos_use/tool yuki/tools
```

- [ ] **Step 4: Strip pycache and DS_Store from the copy**

```bash
cd /Users/mafex/code/personal/Yuki
find yuki -type d -name __pycache__ -exec rm -rf {} +
find yuki -name '.DS_Store' -delete
```

- [ ] **Step 5: Confirm telemetry was NOT copied**

```bash
cd /Users/mafex/code/personal/Yuki
ls yuki/ | sort
```
Expected: `__init__.py  _smoke.py  agent  ax  messages  providers  tool`. There must be no `telemetry` entry.

- [ ] **Step 6: Snapshot the raw copy in git**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/
git commit -m "$(cat <<'EOF'
chore(vendor): copy MacOS-Use subsystems into yuki/ (pre-rewrite)

Verbatim copy of agent/, ax/, messages/, providers/, tool/ from
CursorTouch/MacOS-Use @ 0.2.0. Telemetry deliberately omitted.
Imports still reference 'macos_use' — fixed in next commit.

Original copyright preserved per MIT license.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

We commit the raw copy *before* rewriting so `git log -p` later cleanly shows what we changed vs. upstream.

---

## Task 2 — Namespace-rewrite all imports

**Files:**
- Modify (in place): every `.py` file under `yuki/agent/`, `yuki/ax/`, `yuki/messages/`, `yuki/providers/`, `yuki/tools/`. Rewrite imports `from macos_use.tool` → `from yuki.tools` to match the renamed directory.

- [ ] **Step 1: Count `macos_use` references before rewrite**

```bash
cd /Users/mafex/code/personal/Yuki
grep -rln "macos_use" yuki/ | wc -l
```
Expected: a non-zero count (likely 60-100 files). Note the number; after rewrite this count must be 0 except for telemetry-import lines we'll delete in Task 3.

- [ ] **Step 2: Rewrite via sed (in place, files only)**

```bash
cd /Users/mafex/code/personal/Yuki
find yuki -type f -name '*.py' -exec sed -i '' 's/macos_use/yuki/g' {} +
```
The trailing `''` on `-i` is required on BSD sed (macOS).

- [ ] **Step 3: Verify rewrite removed every reference except in `yuki/telemetry`-import lines**

```bash
cd /Users/mafex/code/personal/Yuki
grep -rln "macos_use" yuki/
```
Expected: no output. If any remain, inspect them — they're likely string literals (e.g. logger names) we want to deal with explicitly. Open each and replace as appropriate.

- [ ] **Step 4: Find telemetry-import lines that the rewrite turned into broken `from yuki.telemetry...` references**

```bash
cd /Users/mafex/code/personal/Yuki
grep -rn "from yuki.telemetry\|import yuki.telemetry\|yuki\.telemetry" yuki/
```
Expected: hits in `yuki/agent/service.py` (and possibly elsewhere). Note the file paths and line numbers — Task 3 deletes them.

- [ ] **Step 5: Run a quick parse-check on every Python file**

```bash
cd /Users/mafex/code/personal/Yuki
uv run python -c "
import pathlib, ast, sys
errors = []
for p in pathlib.Path('yuki').rglob('*.py'):
    try: ast.parse(p.read_text())
    except SyntaxError as e: errors.append((p, e))
for p, e in errors: print(p, e)
sys.exit(1 if errors else 0)
"
```
Expected: exit 0, no output. Syntax-level rewrite mistakes surface here.

- [ ] **Step 6: Commit the rewrite**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/
git commit -m "$(cat <<'EOF'
refactor(vendor): rewrite macos_use imports → yuki

In-place sed across yuki/**/*.py. Telemetry imports now point at
yuki.telemetry which doesn't exist; the next commit deletes them.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — Delete every telemetry call site

**Files:**
- Modify: `/Users/mafex/code/personal/Yuki/yuki/agent/service.py` — remove imports and 8 call sites (per Task 0 grep, lines ~5, 6, 91, 295, 306, 312, 322, 490, 501, 507, 517 — verify exact lines via grep before editing)

- [ ] **Step 1: List every telemetry reference in the rewritten code**

```bash
cd /Users/mafex/code/personal/Yuki
grep -n "telemetry\|ProductTelemetry\|AgentTelemetryEvent" yuki/agent/service.py
```
Expected: 10-12 hits in `yuki/agent/service.py` — 2 import lines + 1 init line + 8 call sites (each is a 2-3 line block with `self.telemetry.capture(...)` followed by `self.telemetry.flush()`).

- [ ] **Step 2: Open `yuki/agent/service.py`. Delete the two telemetry imports.**

Find and delete these two lines (exact match, near the top of the file):

```python
from yuki.telemetry.service import ProductTelemetry
from yuki.telemetry.views import AgentTelemetryEvent
```

- [ ] **Step 3: Delete the telemetry init in `Agent.__init__`**

Find the line `self.telemetry = ProductTelemetry()` and delete it.

- [ ] **Step 4: Delete all eight `self.telemetry.capture(...)` blocks**

For each grep hit on `self.telemetry.capture(`, delete:
- The `self.telemetry.capture(AgentTelemetryEvent(...))` call (which spans multiple lines — find the matching closing parenthesis)
- The `self.telemetry.flush()` line that follows it

Example block to remove (one of eight):

```python
            self.telemetry.capture(AgentTelemetryEvent(
                ...several kwargs across multiple lines...
            ))
            ...
            self.telemetry.flush()
```

After deleting, ensure surrounding control flow still reads cleanly — these blocks are usually inside `if`/`else`/`try` arms. Don't accidentally orphan an `if` whose only body was the telemetry block; if a branch becomes empty, replace with `pass` or merge with the surrounding logic.

- [ ] **Step 5: Verify no telemetry references remain**

```bash
cd /Users/mafex/code/personal/Yuki
grep -rn "telemetry\|ProductTelemetry\|AgentTelemetryEvent\|posthog\|PostHog\|ANONYMIZED_TELEMETRY" yuki/
```
Expected: zero hits. This is the §10.7 spec compliance check.

- [ ] **Step 6: Re-run the parse-check from Task 2 Step 5**

```bash
cd /Users/mafex/code/personal/Yuki
uv run python -c "
import pathlib, ast, sys
errors = []
for p in pathlib.Path('yuki').rglob('*.py'):
    try: ast.parse(p.read_text())
    except SyntaxError as e: errors.append((p, e))
for p, e in errors: print(p, e)
sys.exit(1 if errors else 0)
"
```
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/agent/service.py
git commit -m "$(cat <<'EOF'
refactor: delete all telemetry call sites and imports

Per spec §10.7: zero telemetry, ever. PostHog, AgentTelemetryEvent,
and ProductTelemetry are gone; 8 capture-and-flush blocks in
Agent.invoke / Agent.ainvoke removed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — Add runtime dependencies to pyproject

**Files:**
- Modify: `/Users/mafex/code/personal/Yuki/pyproject.toml`

- [ ] **Step 1: Open `pyproject.toml`, replace the `dependencies = []` block**

Find:

```toml
dependencies = []
```

Replace with the full runtime dep list (mirrors MacOS-Use's pyproject, with versions floor-pinned, `posthog` and `uuid_extensions` removed):

```toml
dependencies = [
    # macOS bindings
    "pyobjc-core>=12.1",
    "pyobjc>=12.1",
    "pyobjc-framework-Quartz>=10.1",
    "pyobjc-framework-Cocoa>=10.1",
    "pyobjc-framework-ApplicationServices>=10.1",
    # Image / OCR / clipboard
    "pillow>=10.2.0",
    "pyautogui>=0.9.54",
    # HTTP & web scraping
    "requests>=2.31.0",
    "markdownify>=0.11.6",
    # Output / logging
    "rich>=13.7.0",
    "tabulate>=0.9.0",
    # Validation
    "pydantic>=2.7.0",
    # Misc
    "python-dotenv>=1.0.0",
    "uuid7>=0.1.0",
    # LLM SDKs (all 13 providers vendored)
    "anthropic>=0.68.1",
    "openai>=1.93.0",
    "google-generativeai>=0.4.0",
    "google-genai>=1.45.0",
    "groq>=0.29.0",
    "ollama>=0.5.1",
    "cerebras-cloud-sdk>=1.50.1",
    "litellm>=1.72.0",
    "mistralai>=1.9.11",
]
```

- [ ] **Step 2: Add `pytest-mock` to dev deps**

In the same file, find:

```toml
[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.7.0",
    "mypy>=1.11.0",
]
```

Replace with:

```toml
[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.7.0",
    "mypy>=1.11.0",
    "types-requests",
]
```

- [ ] **Step 3: Sync the new deps**

```bash
cd /Users/mafex/code/personal/Yuki
uv sync --all-extras
```
Expected: a long install pass. Last line: `Installed N packages in Xs`. If any package fails to resolve (e.g. a yanked version), pin to the closest working version and retry.

- [ ] **Step 4: Confirm a basic top-level import works**

```bash
cd /Users/mafex/code/personal/Yuki
uv run python -c "import yuki.messages; import yuki.providers.base; import yuki.tools; print('ok')"
```
Expected: `ok`. If an `ImportError` surfaces, it's almost certainly a residual `macos_use` reference Task 2's grep missed (likely a string literal or a comment-line that survived sed). Fix and re-run.

- [ ] **Step 5: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
deps: add runtime dependencies for vendored agent core

PyObjC, Pillow, pydantic, all 13 LLM SDKs. Drops posthog and
uuid_extensions (replaced with stdlib + uuid7). Adds pytest-mock
to dev deps for stub-LLM tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — Bump default model to Claude Sonnet 4.6

**Files:**
- Modify: `/Users/mafex/code/personal/Yuki/yuki/providers/anthropic/llm.py`

Per spec §2 (Claude-first) and our `claude-api` skill guidance, the default Anthropic model should be `claude-sonnet-4-6` — the latest and most capable Sonnet at this project's start.

- [ ] **Step 1: Inspect the current default**

```bash
cd /Users/mafex/code/personal/Yuki
grep -n 'claude-3-5-sonnet-latest\|model: str =\|model="claude' yuki/providers/anthropic/llm.py
```
Expected: a line like `model: str = "claude-3-5-sonnet-latest",` near the top of `__init__`.

- [ ] **Step 2: Replace the default**

In `yuki/providers/anthropic/llm.py`, find:

```python
        model: str = "claude-3-5-sonnet-latest",
```

Replace with:

```python
        model: str = "claude-sonnet-4-6",
```

- [ ] **Step 3: Verify nothing else still defaults to a 3.5 model**

```bash
cd /Users/mafex/code/personal/Yuki
grep -rn '"claude-3-5\|claude-3.5\|claude-3-' yuki/
```
Expected: no hits in source (matches in vendored upstream comments are fine; check each one and update if it's a default rather than documentation).

- [ ] **Step 4: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/providers/anthropic/llm.py
git commit -m "$(cat <<'EOF'
deps: bump default Anthropic model to claude-sonnet-4-6

Per spec §2 (Claude-first). Sonnet 4.6 is the current generation at
project start; users can override via ChatAnthropic(model=...).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — Add a stub LLM provider for tests

We need a deterministic, network-free LLM to test the agent loop. The stub implements the `BaseChatLLM` Protocol and returns a scripted sequence of responses.

**Files:**
- Create: `/Users/mafex/code/personal/Yuki/yuki/providers/stub/__init__.py`
- Create: `/Users/mafex/code/personal/Yuki/yuki/providers/stub/llm.py`
- Create: `/Users/mafex/code/personal/Yuki/tests/providers/__init__.py`
- Create: `/Users/mafex/code/personal/Yuki/tests/providers/test_stub_llm.py`

- [ ] **Step 1: Inspect the BaseChatLLM Protocol so the stub conforms**

```bash
cd /Users/mafex/code/personal/Yuki
sed -n '1,80p' yuki/providers/base.py
```
Read the Protocol definition. Confirm method signatures: `invoke()`, `ainvoke()`, optionally `stream()` / `astream()`, and what `LLMEvent` looks like.

```bash
cd /Users/mafex/code/personal/Yuki
sed -n '1,60p' yuki/providers/events.py
```
Read `LLMEvent`, `ToolCall`, `LLMEventType`. The stub will construct these directly.

- [ ] **Step 2: Write the failing test FIRST**

Create `/Users/mafex/code/personal/Yuki/tests/providers/__init__.py` (empty file):

```python
```

Create `/Users/mafex/code/personal/Yuki/tests/providers/test_stub_llm.py`:

```python
"""Unit tests for the stub LLM provider used by integration tests."""

from __future__ import annotations

import pytest

from yuki.messages import HumanMessage, SystemMessage
from yuki.providers.events import LLMEventType
from yuki.providers.stub import ChatStub


def test_stub_returns_scripted_text_response() -> None:
    stub = ChatStub(responses=[{"text": "hello world"}])
    event = stub.invoke(messages=[HumanMessage(content="hi")], tools=[])
    assert event.type == LLMEventType.RESPONSE
    assert event.content == "hello world"


def test_stub_returns_scripted_tool_call() -> None:
    stub = ChatStub(
        responses=[
            {
                "tool_calls": [
                    {"id": "t1", "name": "done_tool", "params": {"answer": "all done"}}
                ]
            }
        ]
    )
    event = stub.invoke(messages=[HumanMessage(content="hi")], tools=[])
    assert event.type == LLMEventType.TOOL_CALL
    assert len(event.tool_calls) == 1
    assert event.tool_calls[0].name == "done_tool"
    assert event.tool_calls[0].params == {"answer": "all done"}


def test_stub_advances_through_responses() -> None:
    stub = ChatStub(
        responses=[
            {"text": "first"},
            {"text": "second"},
        ]
    )
    e1 = stub.invoke(messages=[], tools=[])
    e2 = stub.invoke(messages=[], tools=[])
    assert e1.content == "first"
    assert e2.content == "second"


def test_stub_raises_when_responses_exhausted() -> None:
    stub = ChatStub(responses=[{"text": "only"}])
    stub.invoke(messages=[], tools=[])
    with pytest.raises(IndexError, match="ChatStub exhausted"):
        stub.invoke(messages=[], tools=[])


def test_stub_records_calls_for_inspection() -> None:
    stub = ChatStub(responses=[{"text": "ok"}])
    stub.invoke(messages=[SystemMessage(content="sys"), HumanMessage(content="user")], tools=[])
    assert len(stub.calls) == 1
    assert len(stub.calls[0].messages) == 2
```

- [ ] **Step 3: Run the test to verify it fails (RED)**

```bash
cd /Users/mafex/code/personal/Yuki
uv run pytest tests/providers/test_stub_llm.py -v
```
Expected: collection error or `ImportError: cannot import name 'ChatStub' from 'yuki.providers.stub'`.

- [ ] **Step 4: Implement the stub provider**

Create `/Users/mafex/code/personal/Yuki/yuki/providers/stub/__init__.py`:

```python
"""Stub LLM provider for tests. Returns scripted responses; never makes network calls."""

from yuki.providers.stub.llm import ChatStub

__all__ = ["ChatStub"]
```

Create `/Users/mafex/code/personal/Yuki/yuki/providers/stub/llm.py`:

```python
"""Deterministic, network-free LLM for tests.

The stub implements the same `invoke` / `ainvoke` surface as the real
providers but returns scripted `LLMEvent`s. Use it to drive the agent
loop in integration tests without burning tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from yuki.messages import BaseMessage
from yuki.providers.events import LLMEvent, LLMEventType, ToolCall


@dataclass
class _RecordedCall:
    """One captured invocation of the stub, for test assertions."""

    messages: list[BaseMessage]
    tools: list[Any]


class ChatStub:
    """Scripted LLM. Each `invoke()` consumes the next response from the list.

    Each response dict can contain either:
        {"text": "..."}                              → RESPONSE event
        {"tool_calls": [{"id": str, "name": str,     → TOOL_CALL event
                         "params": dict}, ...]}
    """

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._cursor = 0
        self.calls: list[_RecordedCall] = []

    def invoke(
        self,
        messages: list[BaseMessage],
        tools: list[Any] | None = None,
        **_: Any,
    ) -> LLMEvent:
        if self._cursor >= len(self._responses):
            raise IndexError(
                f"ChatStub exhausted after {self._cursor} call(s); "
                f"add more entries to responses=[]"
            )
        self.calls.append(_RecordedCall(messages=list(messages), tools=list(tools or [])))
        spec = self._responses[self._cursor]
        self._cursor += 1
        return self._spec_to_event(spec)

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        tools: list[Any] | None = None,
        **kwargs: Any,
    ) -> LLMEvent:
        return self.invoke(messages, tools, **kwargs)

    @staticmethod
    def _spec_to_event(spec: dict[str, Any]) -> LLMEvent:
        if "tool_calls" in spec:
            calls = [
                ToolCall(id=tc["id"], name=tc["name"], params=tc["params"])
                for tc in spec["tool_calls"]
            ]
            return LLMEvent(type=LLMEventType.TOOL_CALL, content="", tool_calls=calls)
        if "text" in spec:
            return LLMEvent(type=LLMEventType.RESPONSE, content=spec["text"], tool_calls=[])
        raise ValueError(f"ChatStub response must contain 'text' or 'tool_calls': {spec!r}")
```

Note on `LLMEvent` constructor: if the upstream `LLMEvent` dataclass has a different field name (e.g. `type` vs `event_type`) or requires more fields, adjust the constructor calls above to match. Read `yuki/providers/events.py` to confirm; this is the one place the stub depends on upstream shape.

- [ ] **Step 5: Run the test to verify it passes (GREEN)**

```bash
cd /Users/mafex/code/personal/Yuki
uv run pytest tests/providers/test_stub_llm.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Lint + types**

```bash
cd /Users/mafex/code/personal/Yuki
uv run ruff check yuki/providers/stub tests/providers
uv run ruff format --check yuki/providers/stub tests/providers
uv run mypy yuki/providers/stub tests/providers
```
Expected: each exits 0. If `mypy` complains about the upstream types reachable through `BaseMessage` / `LLMEvent`, accept narrow `# type: ignore[...]` only at the boundary, never inside our own code.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/providers/stub tests/providers
git commit -m "$(cat <<'EOF'
feat(providers): add ChatStub — deterministic LLM for tests

Returns scripted LLMEvents (text or tool_calls), records every
invocation for assertion, never touches the network. Will be used
by Plan A's agent-loop integration test and by every later plan
that needs to exercise agent behaviour.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — Wire up `yuki/__init__.py` public API

The package currently exports only `__version__` (Plan A0 smoke). We add the canonical `Agent` and `ChatAnthropic` exports so downstream plans and end users can `from yuki import Agent`.

**Files:**
- Modify: `/Users/mafex/code/personal/Yuki/yuki/__init__.py`

- [ ] **Step 1: Find the top-level Agent class**

```bash
cd /Users/mafex/code/personal/Yuki
grep -n "^class Agent" yuki/agent/service.py
```
Expected: a single hit. Confirm the class is named `Agent`.

- [ ] **Step 2: Replace `yuki/__init__.py`**

Replace the entire contents of `/Users/mafex/code/personal/Yuki/yuki/__init__.py`:

```python
"""Yuki — a macOS-native personal AI assistant that learns who you are."""

from yuki.agent.service import Agent
from yuki.agent.desktop.views import Browser

__version__ = "0.0.1"

__all__ = ["Agent", "Browser", "__version__"]
```

- [ ] **Step 3: Verify the new public API imports**

```bash
cd /Users/mafex/code/personal/Yuki
uv run python -c "from yuki import Agent, Browser, __version__; print(__version__, Agent.__name__, Browser.__name__)"
```
Expected: `0.0.1 Agent Browser`. If `ImportError`, the most likely cause is a still-broken vendored module — re-run Task 2/3 grep checks.

- [ ] **Step 4: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/__init__.py
git commit -m "$(cat <<'EOF'
feat: export Agent and Browser as public API

`from yuki import Agent` is the canonical entry point per spec §2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — Integration test: drive one full loop iteration with the stub

Goal: prove the vendored agent loop is wired correctly by feeding it a stub LLM that calls `done_tool` immediately. We mock out Desktop / Tree / Watchdog so the test runs anywhere — not just on a real Mac.

**Files:**
- Create: `/Users/mafex/code/personal/Yuki/tests/agent/__init__.py`
- Create: `/Users/mafex/code/personal/Yuki/tests/agent/test_agent_loop_with_stub.py`
- Modify: `/Users/mafex/code/personal/Yuki/tests/conftest.py` — add a fixture that builds a fully-mocked Agent

- [ ] **Step 1: Inspect `Agent.__init__` to learn what to mock**

```bash
cd /Users/mafex/code/personal/Yuki
sed -n '40,140p' yuki/agent/service.py
```
Note which fields are constructed in `__init__` that touch macOS APIs: `Desktop()`, `WatchDog()`, possibly `Tree()` is owned by `Desktop`. These are the things the test fixture replaces with `MagicMock` so a CI Linux runner can pass it (even though spec ties us to macOS-14, mocking still helps catch logic errors fast without booting AX).

- [ ] **Step 2: Add a shared fixture in conftest**

Replace `/Users/mafex/code/personal/Yuki/tests/conftest.py` entirely:

```python
"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from yuki.providers.stub import ChatStub


@pytest.fixture
def chat_stub_factory() -> Any:
    """Returns a builder that creates a ChatStub with the given scripted responses."""

    def _make(responses: list[dict[str, Any]]) -> ChatStub:
        return ChatStub(responses=responses)

    return _make


@pytest.fixture
def fake_desktop() -> MagicMock:
    """A MagicMock standing in for yuki.agent.desktop.service.Desktop.

    Returns a default DesktopState-like object on get_state() so the
    agent loop can run without real macOS APIs.
    """
    desktop = MagicMock(name="Desktop")
    state = MagicMock(name="DesktopState")
    state.tree_state.interactive_nodes = []
    state.tree_state.scrollable_nodes = []
    state.tree_state.informative_nodes = []
    state.active_window = MagicMock(name="ActiveWindow", title="Test", app="TestApp")
    state.windows = []
    state.screenshot = None
    desktop.get_state.return_value = state
    desktop.get_screen_size.return_value = (1920, 1080)
    desktop.get_dpi_scaling.return_value = 2.0
    desktop.get_macos_version.return_value = "macOS 15.0"
    desktop.get_default_language.return_value = "en"
    desktop.get_user_account_type.return_value = "Standard"
    return desktop
```

- [ ] **Step 3: Write the failing test**

Create `/Users/mafex/code/personal/Yuki/tests/agent/__init__.py` (empty file):

```python
```

Create `/Users/mafex/code/personal/Yuki/tests/agent/test_agent_loop_with_stub.py`:

```python
"""End-to-end smoke: Agent.invoke runs one loop iteration with a stub LLM
and produces a final answer via done_tool."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from yuki import Agent
from yuki.providers.stub import ChatStub


@pytest.fixture
def agent_with_done_response(
    chat_stub_factory: Any, fake_desktop: MagicMock
) -> tuple[Agent, ChatStub]:
    """Agent wired to a stub LLM that immediately calls done_tool."""
    stub = chat_stub_factory(
        [
            {
                "tool_calls": [
                    {
                        "id": "call_done_1",
                        "name": "done_tool",
                        "params": {"answer": "Task complete."},
                    }
                ]
            }
        ]
    )

    # Patch Desktop and WatchDog so Agent doesn't try to talk to real macOS APIs.
    with patch("yuki.agent.service.Desktop", return_value=fake_desktop), patch(
        "yuki.agent.service.WatchDog", return_value=MagicMock(name="WatchDog")
    ):
        agent = Agent(llm=stub, max_steps=3, log_to_console=False)
    return agent, stub


def test_agent_invoke_returns_done_answer(
    agent_with_done_response: tuple[Agent, ChatStub],
) -> None:
    agent, stub = agent_with_done_response
    result = agent.invoke(task="Test task")
    assert "Task complete." in str(result.content)
    assert len(stub.calls) == 1, "agent should hit the LLM exactly once"


def test_agent_invoke_passes_system_message(
    agent_with_done_response: tuple[Agent, ChatStub],
) -> None:
    agent, stub = agent_with_done_response
    agent.invoke(task="Test task")
    # First message in the first call should be a SystemMessage.
    first_call_messages = stub.calls[0].messages
    assert first_call_messages, "agent must send at least one message"
    assert first_call_messages[0].__class__.__name__ == "SystemMessage"
```

- [ ] **Step 4: Run the test to verify it fails or surfaces missing wiring (RED)**

```bash
cd /Users/mafex/code/personal/Yuki
uv run pytest tests/agent/test_agent_loop_with_stub.py -v
```
Expected: failures pointing at upstream surface differences — the most common are:

- `Agent.__init__` doesn't accept `llm=` as a positional kwarg (check the signature; adjust the test)
- `Agent.invoke` returns an object whose answer attribute is named differently (e.g. `result.answer` vs `result.content`)
- The mocked Desktop's `get_state()` return shape doesn't match what Context expects

These are **expected** discoveries — adjust the test to match the upstream API. Do NOT modify `yuki/agent/service.py` to match the test; the agent core is the source of truth, the test bends to it.

- [ ] **Step 5: Iterate test → GREEN**

For each red, read `yuki/agent/service.py` to see the actual API, update the test, re-run. Continue until pytest reports 2 passed.

- [ ] **Step 6: Lint + types**

```bash
cd /Users/mafex/code/personal/Yuki
uv run ruff check tests/agent tests/conftest.py
uv run ruff format --check tests/agent tests/conftest.py
uv run mypy tests/agent tests/conftest.py
```
Expected: each exits 0.

- [ ] **Step 7: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add tests/agent tests/conftest.py
git commit -m "$(cat <<'EOF'
test(agent): integration test driving one loop iteration with stub LLM

Mocks Desktop and WatchDog so the test runs anywhere; uses ChatStub
to script a single done_tool response. Proves the vendored agent
loop is wired end-to-end after telemetry strip and namespace rewrite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 — Delete the Plan A0 smoke test

Plan A0 left `yuki/_smoke.py` and `tests/test_smoke.py` as throwaway proof-of-toolchain. Now that real code exists, delete them.

**Files:**
- Delete: `/Users/mafex/code/personal/Yuki/yuki/_smoke.py`
- Delete: `/Users/mafex/code/personal/Yuki/tests/test_smoke.py`

- [ ] **Step 1: Delete both files**

```bash
cd /Users/mafex/code/personal/Yuki
rm yuki/_smoke.py tests/test_smoke.py
```

- [ ] **Step 2: Run the full test suite to confirm nothing depended on them**

```bash
cd /Users/mafex/code/personal/Yuki
uv run pytest -v
```
Expected: only the new tests run (5 stub-LLM tests + 2 agent-loop tests = 7 total). All pass.

- [ ] **Step 3: Run the full check pipeline one more time**

```bash
cd /Users/mafex/code/personal/Yuki
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -v
```
Expected: every command exits 0.

- [ ] **Step 4: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/_smoke.py tests/test_smoke.py  # stages the deletions
git commit -m "$(cat <<'EOF'
chore: remove Plan A0 smoke test now that real code is in place

The yuki/_smoke.py + tests/test_smoke.py pair existed only to prove
the toolchain worked. Real tests under tests/agent/ and
tests/providers/ now serve as the sanity floor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 — Claude-Code-style loop hardening

The vendored MacOS-Use loop has three correctness/robustness issues that the leaked Claude Code source (`/Users/mafex/code/personal/claude-leak/src/query.ts`) gets right. Fix them now while the diff against upstream is still small.

**Files:**
- Modify: `yuki/agent/service.py` (the agent loop)
- Modify: `yuki/agent/loop.py` (LoopGuard) or wherever termination is checked
- Create: `yuki/agent/cost.py` (per-session cost tracker)
- Create: `tests/agent/test_loop_termination.py`
- Create: `tests/agent/test_cost_tracker.py`

### Why each change

1. **Termination signal**: MacOS-Use checks `stop_reason == "end_turn"`. Anthropic's stop_reason is unreliable mid-tool-use (per `claude-leak/src/query.ts:557`). The right signal is "did this assistant message contain any `tool_use` blocks?" If yes → continue; if no → terminate.
2. **Transcript-before-API-call**: a crash mid-stream currently loses the user's prompt. Persist the user message before opening the LLM stream.
3. **Per-session cost tracking**: BYO-key users need to see their spend. Persist `input_tokens / output_tokens / cache_read_tokens / cache_creation_tokens` per session to JSON.

### Steps

- [ ] **Step 1: Write the failing test for termination**

`tests/agent/test_loop_termination.py`:

```python
import pytest

from yuki.agent.loop import should_continue


def _msg(content_blocks: list[dict], stop_reason: str = "end_turn"):
    """Mimic an Anthropic assistant message envelope."""
    return type("M", (), {"content": content_blocks, "stop_reason": stop_reason})()


def test_continue_when_tool_use_present_even_if_stop_reason_end_turn():
    msg = _msg(
        [{"type": "text", "text": "I'll click."},
         {"type": "tool_use", "id": "t1", "name": "click", "input": {}}],
        stop_reason="end_turn",
    )
    assert should_continue(msg) is True


def test_stop_when_no_tool_use_blocks():
    msg = _msg([{"type": "text", "text": "Done."}], stop_reason="end_turn")
    assert should_continue(msg) is False


def test_stop_when_no_blocks_at_all():
    msg = _msg([], stop_reason="end_turn")
    assert should_continue(msg) is False


def test_stop_reason_max_tokens_with_tool_use_still_continues():
    msg = _msg(
        [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}],
        stop_reason="max_tokens",
    )
    assert should_continue(msg) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/test_loop_termination.py -v`
Expected: ImportError on `yuki.agent.loop.should_continue` (function doesn't exist yet).

- [ ] **Step 3: Implement `should_continue` in `yuki/agent/loop.py`**

Add to the existing `loop.py`:

```python
def should_continue(assistant_message) -> bool:
    """Continue the loop iff the assistant emitted any tool_use blocks.

    stop_reason is unreliable per Anthropic's own implementation
    (see claude-leak/src/query.ts:557). The block list is authoritative.
    """
    blocks = getattr(assistant_message, "content", None) or []
    return any(getattr(b, "type", None) == "tool_use" or
               (isinstance(b, dict) and b.get("type") == "tool_use")
               for b in blocks)
```

Then locate the existing termination check in `yuki/agent/service.py` (vendored from MacOS-Use; usually a `while` loop checking `stop_reason`) and replace the predicate with `should_continue(assistant_message)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/test_loop_termination.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Move transcript persistence BEFORE the API call**

In `yuki/agent/service.py`, find the section that records the user message + calls the LLM. The pattern from MacOS-Use is roughly:

```python
# BEFORE (current):
response = await self.llm.invoke(messages)
self._record(user_msg)  # too late — crash above loses the prompt
```

Replace with:

```python
# AFTER:
self._record(user_msg)              # persist BEFORE network call
response = await self.llm.invoke(messages)
```

The `_record` method should append a JSONL line to a session file under `~/Library/Application Support/Yuki/sessions/<session_id>.jsonl`. If `_record` doesn't exist on the vendored agent, add it as a minimal helper:

```python
import json
from pathlib import Path

def _record(self, message: dict) -> None:
    base = Path.home() / "Library" / "Application Support" / "Yuki" / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{self.session_id}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(message, default=str) + "\n")
```

(In Plan I we add a structured `TrajectoryRecorder` that supersedes this; for now this minimal version unblocks the loop.)

- [ ] **Step 6: Write the failing test for cost tracking**

`tests/agent/test_cost_tracker.py`:

```python
import json
from pathlib import Path

import pytest

from yuki.agent.cost import CostTracker


@pytest.fixture
def tmp_cost_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("YUKI_COST_DIR", str(tmp_path))
    return tmp_path


def test_records_usage_per_call(tmp_cost_dir: Path):
    c = CostTracker(session_id="abc")
    c.record(input_tokens=100, output_tokens=50,
             cache_read_tokens=80, cache_creation_tokens=20,
             model="claude-sonnet-4-6")
    c.record(input_tokens=20, output_tokens=10,
             cache_read_tokens=15, cache_creation_tokens=0,
             model="claude-sonnet-4-6")
    totals = c.totals()
    assert totals["input_tokens"] == 120
    assert totals["output_tokens"] == 60
    assert totals["cache_read_tokens"] == 95


def test_persists_to_disk(tmp_cost_dir: Path):
    c = CostTracker(session_id="xyz")
    c.record(input_tokens=10, output_tokens=5,
             cache_read_tokens=0, cache_creation_tokens=0,
             model="claude-sonnet-4-6")
    path = tmp_cost_dir / "xyz.cost.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["totals"]["input_tokens"] == 10


def test_resume_existing_session(tmp_cost_dir: Path):
    c1 = CostTracker(session_id="r")
    c1.record(input_tokens=10, output_tokens=5,
              cache_read_tokens=0, cache_creation_tokens=0,
              model="claude-sonnet-4-6")
    c2 = CostTracker(session_id="r")
    assert c2.totals()["input_tokens"] == 10
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/test_cost_tracker.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 8: Implement `yuki/agent/cost.py`**

```python
"""Per-session cost tracker — persists token usage to disk for BYO-key users.

Mirrors the pattern in claude-leak/src/cost-tracker.ts:143.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path


def _root() -> Path:
    override = os.environ.get("YUKI_COST_DIR")
    if override:
        return Path(override)
    return (
        Path.home() / "Library" / "Application Support" / "Yuki" / "sessions"
    )


class CostTracker:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._totals: dict[str, int] = defaultdict(int)
        self._by_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._load()

    def _path(self) -> Path:
        return _root() / f"{self._session_id}.cost.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for k, v in (data.get("totals") or {}).items():
            self._totals[k] = int(v)
        for model, counts in (data.get("by_model") or {}).items():
            for k, v in counts.items():
                self._by_model[model][k] = int(v)

    def record(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_creation_tokens: int,
        model: str,
    ) -> None:
        for k, v in {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
        }.items():
            self._totals[k] += v
            self._by_model[model][k] += v
        self._save()

    def totals(self) -> dict[str, int]:
        return dict(self._totals)

    def _save(self) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "session_id": self._session_id,
            "totals": dict(self._totals),
            "by_model": {m: dict(c) for m, c in self._by_model.items()},
        }, indent=2), encoding="utf-8")
```

- [ ] **Step 9: Wire CostTracker into the loop**

In `yuki/agent/service.py`, after each LLM response carries usage, call:

```python
self.cost.record(
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
    cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
    cache_creation_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
    model=response.model,
)
```

(Construct `self.cost = CostTracker(session_id=self.session_id)` once in `__init__`.)

- [ ] **Step 10: Run all agent tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/ -v
```

Expected: all green; new tests added (≥7).

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/agent/loop.py yuki/agent/service.py yuki/agent/cost.py tests/agent/test_loop_termination.py tests/agent/test_cost_tracker.py
git commit -m "feat(agent): Claude-Code-style loop termination + transcript ordering + cost tracker"
```

---

## Task 11 — `ToolUseContext` scratch object

Tools currently reach into module globals (Vault, Indexer, Gatekeeper) via `get_runtime()`. Claude Code threads a typed `ToolUseContext` through every tool call (claude-leak/src/Tool.ts:158-300). Adopt the same pattern so tests can construct isolated contexts and tools never reach for globals.

**Files:**
- Create: `yuki/agent/context.py`
- Create: `tests/agent/test_tool_context.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from datetime import datetime, timezone

import pytest

from yuki.agent.context import ToolUseContext


@pytest.mark.asyncio
async def test_context_carries_abort_event():
    ctx = ToolUseContext.bare()
    assert ctx.abort_event is not None
    assert not ctx.abort_event.is_set()
    ctx.abort_event.set()
    assert ctx.abort_event.is_set()


def test_context_app_state_round_trip():
    ctx = ToolUseContext.bare()
    ctx.set_app_state("k", "v")
    assert ctx.get_app_state("k") == "v"
    assert ctx.get_app_state("missing", default="d") == "d"


def test_context_session_id_unique_when_unset():
    a = ToolUseContext.bare()
    b = ToolUseContext.bare()
    assert a.session_id != b.session_id


def test_fork_inherits_app_state_but_independent():
    parent = ToolUseContext.bare()
    parent.set_app_state("k", "v")
    child = parent.fork(agent_id="child-1")
    assert child.get_app_state("k") == "v"
    child.set_app_state("k", "v2")
    assert parent.get_app_state("k") == "v"
    assert child.session_id == parent.session_id
    assert child.agent_id == "child-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/test_tool_context.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/agent/context.py`**

```python
"""ToolUseContext — typed scratch object threaded through every tool call.

Mirrors claude-leak/src/Tool.ts:158-300 (`ToolUseContext`).

Design rules:
- Tools must accept `ctx: ToolUseContext` and never reach for module globals.
- `fork(agent_id=...)` creates a child context that inherits app_state by deep
  copy; mutations on the child don't leak to the parent.
- `abort_event` is shared across the agent loop and all tools so a single
  abort signal stops everything cleanly.
"""
from __future__ import annotations

import asyncio
import copy
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolUseContext:
    session_id: str
    agent_id: str
    abort_event: asyncio.Event
    _app_state: dict[str, Any] = field(default_factory=dict)
    _read_file_cache: dict[str, str] = field(default_factory=dict)

    @classmethod
    def bare(cls) -> "ToolUseContext":
        return cls(
            session_id=uuid.uuid4().hex[:12],
            agent_id="root",
            abort_event=asyncio.Event(),
        )

    def get_app_state(self, key: str, default: Any = None) -> Any:
        return self._app_state.get(key, default)

    def set_app_state(self, key: str, value: Any) -> None:
        self._app_state[key] = value

    def cache_read_file(self, path: str, content: str) -> None:
        self._read_file_cache[path] = content

    def get_cached_read(self, path: str) -> str | None:
        return self._read_file_cache.get(path)

    def fork(self, *, agent_id: str) -> "ToolUseContext":
        return ToolUseContext(
            session_id=self.session_id,
            agent_id=agent_id,
            abort_event=self.abort_event,  # shared
            _app_state=copy.deepcopy(self._app_state),
            _read_file_cache=copy.deepcopy(self._read_file_cache),
        )
```

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/test_tool_context.py -v
```

Expected: 4 PASS.

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki/agent/context.py tests/agent/test_tool_context.py
git commit -m "feat(agent): add ToolUseContext for typed tool-call scratch"
```

Note: actually threading `ctx: ToolUseContext` through every existing native tool is a follow-up — the registry and a few core tools already accept it via `**kwargs` since the @tool decorator passes `**args`; the migration is gradual. This task makes the type available; downstream tasks adopt it.

---

## Acceptance criteria for this plan

The plan is done when **all** of the following are true:

1. `grep -rn "macos_use" yuki/` returns no hits.
2. `grep -rn "telemetry\|posthog\|PostHog\|ProductTelemetry\|AgentTelemetryEvent\|ANONYMIZED_TELEMETRY" yuki/` returns no hits.
3. `from yuki import Agent, Browser, __version__` works in a fresh `uv run python -c '…'`.
4. `uv run pytest -v` reports exactly the tests added in this plan (≥7 passing, 0 failing). Smoke test from A0 is gone.
5. `uv run ruff check .` exits 0.
6. `uv run ruff format --check .` exits 0.
7. `uv run mypy` exits 0.
8. The default Anthropic model is `claude-sonnet-4-6` (`grep -n 'claude-sonnet-4-6' yuki/providers/anthropic/llm.py` returns ≥1 hit).
9. `tests/agent/test_agent_loop_with_stub.py` proves `Agent.invoke()` runs one iteration and returns a result containing the scripted `done_tool` answer.
10. Git history has ≥11 commits since Plan A0's last commit, each scoped to one task in this plan.
11. `should_continue(msg)` is the only termination predicate — `grep -rn "stop_reason" yuki/agent/` returns at most one hit (a comment explaining why we don't trust it).
12. After running the integration test, `~/Library/Application Support/Yuki/sessions/<sid>.cost.json` exists with non-zero token totals.

---

## Out of scope for this plan

Handled by later plans:

- **Memory hot-context injection into the system prompt** — Plan B (memory vault). The agent's prompt template is unchanged here; we just got the loop running.
- **Removing `posthog`/`uuid_extensions` from `uv.lock`** — already done; these were only required by the deleted `telemetry/` package, so they shouldn't appear at all. If `uv.lock` somehow lists them as transitive deps of another package, that's fine.
- **Replacing the system prompt for Yuki branding** — Plan H (FastAPI backend) or earlier when the prompt becomes load-bearing. The vendored prompt still says "MacOS-Use, created by CursorTouch" — that's tolerable in a stub-LLM test and gets fixed before any user sees it.
- **Adding all 13 LLM providers as production-ready paths** — they're vendored and importable, but only Anthropic is the documented happy path. Plan H wires up multi-provider settings UI.
- **Test coverage of the `ax/` module** — exercised indirectly via Desktop/Tree later. Direct unit tests would require macOS hardware in CI, which we explicitly call out as macOS-14-only.
- **Vault-aware tools** — Plan B adds `memory_search` / `memory_read` / `memory_write` to the agent's tool set.

---

## Notes for the executing engineer

- **Vendored copyright:** keep upstream's MIT header on every copied file. We're not stealing — we're forking. If you spot a file with a different copyright (unusual for this codebase), keep that header too.
- **Don't refactor while vendoring.** If you see something ugly in upstream code (and there's some — `agent/service.py` has long `try/except` blocks that the telemetry strip will leave looking awkward), fight the urge to clean it up in this plan. Plan A is a vendor-and-wire-it-up plan, nothing more. Refactor in a later plan with its own commit history.
- **If Task 3's surgery on `agent/service.py` leaves an empty `else:` or `try:` arm,** insert a `pass` statement rather than restructuring control flow. Restructuring is out of scope.
- **macOS-only CI surface:** `pyobjc` deps will install fine on macOS-14 GitHub runners but fail on Linux. CI from Plan A0 already pins `runs-on: macos-14`, so this should "just work."
- **Why one commit per task, not one big commit:** so Plan B's diff against this plan is small and the `git log` is a readable history of what changed and why.
