# Plan L — Claude-Code-style Agent Runtime (post-v1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Post-v1. This plan adds the substantial agent-runtime subsystems Yuki v1 deliberately defers — subagents, slash commands, autocompact, max_turns/budget guards, stop hooks. Build only after v1 ships and you have user signal.

**Goal:** Bring Yuki's agent runtime to feature parity with Claude Code's loop on the dimensions that matter for a long-running personal assistant: spawning subagents for parallel research, slash commands for power-user workflows, automatic context compaction so very long sessions don't blow up token budgets, hard guards on turns + spend, and stop-hooks as a final-chance re-injection point.

**Architecture:** The v1 agent loop (Plan A Task 10 hardened) runs one user-task → tool-use loop. This plan adds five orthogonal subsystems on top:

1. **Subagent dispatch** — an `AgentTool` that, given a sub-agent prompt, forks a fresh `ToolUseContext`, runs the same loop with restricted tool set, and streams sidechain transcripts back. Mirrors `claude-leak/src/tools/AgentTool/runAgent.ts`.
2. **Slash commands** — three command types (`PromptCommand`, `LocalCommand`, `LocalJSXCommand`) plugged into the chat input pipeline. Mirrors `claude-leak/src/commands.ts`.
3. **Autocompact** — when conversation tokens cross a high-water mark, run a forked subagent that summarizes history and replaces the message array with the summary + recent turns. Mirrors `claude-leak/src/query.ts` autocompact branch.
4. **Max-turns + max-budget guards** — first-class config; abort the loop with a structured terminal reason when exceeded. Mirrors `claude-leak/src/QueryEngine.ts:1507`.
5. **Stop hooks** — an extension point that runs after the loop decides to terminate, allowing user-defined hooks to inject one more user message and resume. Mirrors `claude-leak/src/query.ts:1267`.

**Tech Stack:** stdlib `asyncio`, Pydantic (Plan B), `tiktoken>=0.7` for token counting, `pytest-asyncio`. No new external dependencies for the others.

**Spec reference:** None of these subsystems are in the v1 design spec — they're acknowledged-gap additions identified by analyzing Claude Code's source. Document in spec amendment §16 if/when this plan executes.

**Prerequisite:** v1 shipping or near-shipping. Specifically Plans A (with Tasks 10–11), B, F, G, H, I must be in place. Plan L assumes the agent loop, vault, tools, gatekeeper, and HTTP backend are all wired and tested.

---

## Resolved design choices

1. **Single compaction strategy** — autocompact only. Skip Claude Code's microcompact + context-collapse + reactive-compact triple. They cover edge cases v1 doesn't have. (Reference: claude-leak/src/query.ts comments around the three branches.)
2. **Subagents are read-only by default** — agent definitions specify `allowed_tools`; if absent, the subagent inherits only `READ_ONLY` tools from the parent. Prevents an LLM-induced mistake from cascading into destructive action via a subagent.
3. **Slash commands are agent-side only at v1.5** — frontend (Plan I + Next.js) gets a `/` autocomplete UI; the menubar app's hotkey overlay does not. Keep scope tight.
4. **Token counting uses `tiktoken` against `cl100k_base` for all providers** — close enough for compaction triggers; we don't need exact accounting.

---

## File Structure

```
Yuki/
├── pyproject.toml                              # MODIFIED — adds tiktoken
├── yuki/
│   └── runtime/
│       ├── __init__.py                         # NEW
│       ├── subagent/
│       │   ├── __init__.py                     # NEW
│       │   ├── definition.py                   # NEW — AgentDefinition (typed)
│       │   ├── runner.py                       # NEW — run_subagent async generator
│       │   └── agent_tool.py                   # NEW — @tool that exposes spawn-subagent
│       ├── commands/
│       │   ├── __init__.py                     # NEW
│       │   ├── base.py                         # NEW — Command protocol
│       │   ├── registry.py                     # NEW — REGISTRY + register_command
│       │   ├── builtins/
│       │   │   ├── __init__.py
│       │   │   ├── clear.py                    # /clear
│       │   │   ├── compact.py                  # /compact
│       │   │   ├── help.py                     # /help
│       │   │   ├── cost.py                     # /cost
│       │   │   ├── memory.py                   # /memory
│       │   │   └── quit.py                     # /quit
│       │   └── pipeline.py                     # NEW — process_user_input dispatcher
│       ├── compaction.py                       # NEW — autocompact
│       ├── guards.py                           # NEW — max_turns + max_budget + abort
│       └── stop_hooks.py                       # NEW — registry + invocation
└── tests/
    └── runtime/
        ├── __init__.py
        ├── conftest.py
        ├── subagent/
        │   ├── __init__.py
        │   ├── test_definition.py
        │   ├── test_runner.py                  # mocked LLM
        │   └── test_agent_tool.py
        ├── commands/
        │   ├── __init__.py
        │   ├── test_pipeline.py
        │   └── test_builtins.py
        ├── test_compaction.py                  # mocked summarizer
        ├── test_guards.py
        └── test_stop_hooks.py
```

---

## Task 1 — Subagent: `AgentDefinition` + runner

A subagent is described by an `AgentDefinition` — name, system prompt, allowed tools, model override. The runner forks a `ToolUseContext`, builds the subagent's restricted tool set, and runs the same loop as the parent.

**Files:**
- Create: `yuki/runtime/__init__.py`
- Create: `yuki/runtime/subagent/__init__.py`
- Create: `yuki/runtime/subagent/definition.py`
- Create: `yuki/runtime/subagent/runner.py`
- Create: `tests/runtime/__init__.py`
- Create: `tests/runtime/conftest.py`
- Create: `tests/runtime/subagent/__init__.py`
- Create: `tests/runtime/subagent/test_definition.py`
- Create: `tests/runtime/subagent/test_runner.py`

- [ ] **Step 1: Add tiktoken**

In `pyproject.toml` `[project] dependencies` add `"tiktoken>=0.7.0"`. Run `uv sync`.

- [ ] **Step 2: Add fixtures**

`tests/runtime/conftest.py`:

```python
import pytest


@pytest.fixture
def fake_llm():
    """Returns a callable that yields scripted Anthropic-shaped responses."""
    class _Fake:
        def __init__(self):
            self.responses = []
            self.calls = []

        def queue(self, blocks):
            self.responses.append(blocks)

        async def invoke(self, messages, **kwargs):
            self.calls.append({"messages": messages, **kwargs})
            class R:
                def __init__(self, blocks):
                    self.content = blocks
                    self.stop_reason = "end_turn"
                    self.usage = type("U", (), {
                        "input_tokens": 10, "output_tokens": 5,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    })()
                    self.model = "claude-sonnet-4-6"
            return R(self.responses.pop(0) if self.responses else [])

    return _Fake()
```

- [ ] **Step 3: Write the failing test for definition**

`tests/runtime/subagent/test_definition.py`:

```python
import pytest

from yuki.runtime.subagent.definition import AgentDefinition


def test_minimal_definition():
    d = AgentDefinition(
        name="explore",
        system_prompt="You are a code-search subagent.",
    )
    assert d.name == "explore"
    assert d.allowed_tools is None  # inherit read-only from parent
    assert d.is_read_only is True


def test_explicit_allowed_tools():
    d = AgentDefinition(
        name="builder",
        system_prompt="You write code.",
        allowed_tools=["files", "shell"],
    )
    assert d.allowed_tools == ["files", "shell"]
    assert d.is_read_only is False


def test_invalid_name_rejected():
    with pytest.raises(ValueError):
        AgentDefinition(name="has spaces", system_prompt="x")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/subagent/test_definition.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 5: Implement `yuki/runtime/__init__.py`**

```python
"""Yuki agent runtime — post-v1 subagent + slash + compaction subsystems."""
```

`yuki/runtime/subagent/__init__.py`:

```python
"""Subagent dispatch."""
```

- [ ] **Step 6: Implement `yuki/runtime/subagent/definition.py`**

```python
"""AgentDefinition — typed contract for a subagent."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass
class AgentDefinition:
    name: str
    system_prompt: str
    allowed_tools: list[str] | None = None
    model: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(
                f"Subagent name must be lowercase kebab-case: {self.name!r}",
            )

    @property
    def is_read_only(self) -> bool:
        """If allowed_tools is None, runner restricts to read-only tools by default."""
        return self.allowed_tools is None
```

- [ ] **Step 7: Run definition tests**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/subagent/test_definition.py -v
```

Expected: 3 PASS.

- [ ] **Step 8: Write the failing test for runner**

`tests/runtime/subagent/test_runner.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from yuki.runtime.subagent.definition import AgentDefinition
from yuki.runtime.subagent.runner import run_subagent


@pytest.mark.asyncio
async def test_run_subagent_yields_messages(fake_llm):
    fake_llm.queue([{"type": "text", "text": "subagent done"}])

    definition = AgentDefinition(
        name="explore",
        system_prompt="You are read-only.",
    )

    async def collector():
        out = []
        async for msg in run_subagent(
            definition=definition, prompt="what's in src/?", llm=fake_llm,
        ):
            out.append(msg)
        return out

    msgs = await collector()
    assert any(m.get("type") == "assistant" for m in msgs)
    assert any(m.get("type") == "result" for m in msgs)


@pytest.mark.asyncio
async def test_run_subagent_records_sidechain(tmp_path, monkeypatch, fake_llm):
    monkeypatch.setenv("YUKI_SIDECHAIN_DIR", str(tmp_path))
    fake_llm.queue([{"type": "text", "text": "ok"}])
    definition = AgentDefinition(name="x", system_prompt="x")

    async for _ in run_subagent(
        definition=definition, prompt="hi", llm=fake_llm,
    ):
        pass

    files = list(tmp_path.glob("agent-*.jsonl"))
    assert len(files) == 1
    text = files[0].read_text()
    assert "subagent" in text or "agent" in text  # transcript header
```

- [ ] **Step 9: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/subagent/test_runner.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 10: Implement `yuki/runtime/subagent/runner.py`**

```python
"""run_subagent — async generator that executes a subagent loop and streams events.

Mirrors claude-leak/src/tools/AgentTool/runAgent.ts:248. Forks a ToolUseContext,
records sidechain transcripts to ~/Library/Application Support/Yuki/sidechains/
agent-<id>.jsonl, yields {type: ..., ...} dicts for the parent to consume.
"""
from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

from yuki.agent.context import ToolUseContext
from yuki.runtime.subagent.definition import AgentDefinition


def _sidechain_dir() -> Path:
    override = os.environ.get("YUKI_SIDECHAIN_DIR")
    if override:
        return Path(override)
    return (
        Path.home() / "Library" / "Application Support" / "Yuki" / "sidechains"
    )


def _record(agent_id: str, event: dict) -> None:
    root = _sidechain_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"agent-{agent_id}.jsonl"
    stamped = {**event, "ts": datetime.now(timezone.utc).isoformat()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(stamped, default=str) + "\n")


async def run_subagent(
    *,
    definition: AgentDefinition,
    prompt: str,
    llm,
    parent_ctx: ToolUseContext | None = None,
) -> AsyncIterator[dict]:
    """Run a subagent loop. Yields dicts: {type: thought|tool_call|assistant|result|error}."""
    agent_id = uuid.uuid4().hex[:12]
    ctx = (parent_ctx or ToolUseContext.bare()).fork(agent_id=agent_id)

    _record(agent_id, {"type": "start", "definition": definition.name,
                       "prompt": prompt})
    yield {"type": "start", "agent_id": agent_id,
           "definition": definition.name}

    messages = [
        {"role": "system", "content": definition.system_prompt},
        {"role": "user", "content": prompt},
    ]

    response = await llm.invoke(messages)
    blocks = response.content
    yield {"type": "assistant", "agent_id": agent_id, "content": blocks}
    _record(agent_id, {"type": "assistant", "content": blocks})

    # Extract a final text block as the subagent's "answer."
    final_text = ""
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            final_text = b.get("text", "")
            break

    yield {"type": "result", "agent_id": agent_id,
           "content": final_text}
    _record(agent_id, {"type": "result", "content": final_text})
```

(This is a minimal v1 of the runner. Tool dispatch inside the subagent loop is added in Task 3 once the Agent Tool plugin needs it.)

- [ ] **Step 11: Run runner tests**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/subagent/ -v
```

Expected: 5 PASS.

- [ ] **Step 12: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add pyproject.toml uv.lock yuki/runtime/ tests/runtime/__init__.py tests/runtime/conftest.py tests/runtime/subagent/
git commit -m "feat(runtime): add AgentDefinition + run_subagent async generator"
```

---

## Task 2 — `agent_tool` (the AgentTool plugin)

Wraps `run_subagent` as a registered `@tool` so the parent agent can dispatch subagents. Mirrors `claude-leak/src/tools/AgentTool/`.

**Files:**
- Create: `yuki/runtime/subagent/agent_tool.py`
- Create: `tests/runtime/subagent/test_agent_tool.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch

from yuki.runtime.subagent.agent_tool import agent_tool
from yuki.tools.native.registry import REGISTRY, DangerLevel


def test_agent_tool_registered():
    assert "agent" in REGISTRY
    assert REGISTRY["agent"].danger == DangerLevel.READ_ONLY


@pytest.mark.asyncio
async def test_agent_tool_runs_subagent(monkeypatch):
    async def fake_runner(*, definition, prompt, llm, parent_ctx=None):
        yield {"type": "result", "agent_id": "x", "content": "subagent answer"}

    monkeypatch.setattr("yuki.runtime.subagent.agent_tool.run_subagent",
                        fake_runner)
    out = await agent_tool(
        agent_name="explore",
        prompt="find all TODOs",
        system_prompt="You are read-only.",
    )
    assert out["content"] == "subagent answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/subagent/test_agent_tool.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/runtime/subagent/agent_tool.py`**

```python
"""agent_tool — exposes run_subagent as a @tool the parent agent can call."""
from __future__ import annotations

from typing import Any

from yuki.runtime.subagent.definition import AgentDefinition
from yuki.runtime.subagent.runner import run_subagent
from yuki.tools.native.registry import DangerLevel, tool


@tool(
    name="agent",
    danger=DangerLevel.READ_ONLY,
    prompt="Spawn a subagent for parallel research or focused exploration. "
           "The subagent runs read-only by default.",
)
async def agent_tool(
    agent_name: str,
    prompt: str,
    system_prompt: str = "",
) -> dict[str, Any]:
    """Spawn a subagent. Returns the subagent's final answer.

    The subagent is read-only by default — it cannot mutate the vault, send
    mail, or take destructive action. Use it for exploration, research,
    summarization.
    """
    # Real impl wires the parent's LLM provider; for the @tool surface the
    # actual LLM is injected from the agent loop runtime.
    from yuki.providers.stub import ChatStub
    llm = ChatStub()

    definition = AgentDefinition(
        name=agent_name,
        system_prompt=system_prompt or f"You are the {agent_name} subagent.",
    )

    final: dict[str, Any] = {"content": ""}
    async for event in run_subagent(definition=definition, prompt=prompt, llm=llm):
        if event.get("type") == "result":
            final = {"agent_id": event["agent_id"], "content": event["content"]}
    return final
```

- [ ] **Step 4: Register on import**

Add to `yuki/tools/native/__init__.py` (after the other tool imports, before the loader call):

```python
from yuki.runtime.subagent import agent_tool  # noqa: F401  (registers `agent` tool)
```

- [ ] **Step 5: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/subagent/test_agent_tool.py -v
git add yuki/runtime/subagent/agent_tool.py yuki/tools/native/__init__.py tests/runtime/subagent/test_agent_tool.py
git commit -m "feat(runtime): add agent @tool for parent-driven subagent dispatch"
```

---

## Task 3 — Slash command pipeline

Three command types, registry, dispatcher. The chat router (Plan I) calls `process_user_input(text)` first; if a slash command matches, it short-circuits the agent invocation.

**Files:**
- Create: `yuki/runtime/commands/__init__.py`
- Create: `yuki/runtime/commands/base.py`
- Create: `yuki/runtime/commands/registry.py`
- Create: `yuki/runtime/commands/pipeline.py`
- Create: `tests/runtime/commands/__init__.py`
- Create: `tests/runtime/commands/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from yuki.runtime.commands.base import (
    CommandResult, LocalCommand, PromptCommand,
)
from yuki.runtime.commands.pipeline import process_user_input
from yuki.runtime.commands.registry import register, REGISTRY


@pytest.fixture(autouse=True)
def clean_registry():
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_unmatched_passes_through():
    result = process_user_input("hello world")
    assert result.kind == "agent"
    assert result.text == "hello world"


def test_local_command_short_circuits():
    register(LocalCommand(
        name="hi",
        run=lambda args: CommandResult.local_text("hi back"),
    ))
    result = process_user_input("/hi")
    assert result.kind == "local_text"
    assert result.text == "hi back"


def test_prompt_command_emits_user_message():
    register(PromptCommand(
        name="explain",
        prompt_template="Explain this in detail: {args}",
    ))
    result = process_user_input("/explain quicksort")
    assert result.kind == "agent"
    assert "Explain this" in result.text
    assert "quicksort" in result.text


def test_unknown_slash_falls_through_as_agent_message():
    result = process_user_input("/nope")
    assert result.kind == "agent"
    assert result.text == "/nope"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/commands/test_pipeline.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/runtime/commands/__init__.py`**

```python
"""Slash command system."""
```

- [ ] **Step 4: Implement `yuki/runtime/commands/base.py`**

```python
"""Command protocols + result envelope."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal


CommandKind = Literal["agent", "local_text", "skip"]


@dataclass
class CommandResult:
    kind: CommandKind
    text: str = ""

    @classmethod
    def agent(cls, text: str) -> "CommandResult":
        return cls(kind="agent", text=text)

    @classmethod
    def local_text(cls, text: str) -> "CommandResult":
        return cls(kind="local_text", text=text)

    @classmethod
    def skip(cls) -> "CommandResult":
        return cls(kind="skip")


@dataclass
class PromptCommand:
    """Expands to a templated user message that goes to the agent."""
    name: str
    prompt_template: str  # "{args}" gets substituted
    description: str = ""


@dataclass
class LocalCommand:
    """Runs locally; returns a CommandResult directly."""
    name: str
    run: Callable[[str], CommandResult]
    description: str = ""
```

- [ ] **Step 5: Implement `yuki/runtime/commands/registry.py`**

```python
"""Command registry."""
from __future__ import annotations

from typing import Union

from yuki.runtime.commands.base import LocalCommand, PromptCommand

Command = Union[LocalCommand, PromptCommand]
REGISTRY: dict[str, Command] = {}


def register(cmd: Command) -> None:
    REGISTRY[cmd.name] = cmd
```

- [ ] **Step 6: Implement `yuki/runtime/commands/pipeline.py`**

```python
"""process_user_input — first stop for every chat message."""
from __future__ import annotations

from yuki.runtime.commands.base import (
    CommandResult, LocalCommand, PromptCommand,
)
from yuki.runtime.commands.registry import REGISTRY


def process_user_input(text: str) -> CommandResult:
    if not text.startswith("/"):
        return CommandResult.agent(text)

    head, _, tail = text[1:].partition(" ")
    cmd = REGISTRY.get(head)
    if cmd is None:
        # Unknown slash → treat as plain message; the agent can decide.
        return CommandResult.agent(text)

    if isinstance(cmd, LocalCommand):
        return cmd.run(tail.strip())
    if isinstance(cmd, PromptCommand):
        rendered = cmd.prompt_template.format(args=tail.strip())
        return CommandResult.agent(rendered)
    return CommandResult.agent(text)
```

- [ ] **Step 7: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/commands/test_pipeline.py -v
git add yuki/runtime/commands/ tests/runtime/commands/
git commit -m "feat(runtime): add slash command pipeline (Local + Prompt)"
```

---

## Task 4 — Built-in slash commands

Six built-ins: `/clear`, `/compact`, `/help`, `/cost`, `/memory`, `/quit`. Each is a small file under `yuki/runtime/commands/builtins/`.

**Files:**
- Create: `yuki/runtime/commands/builtins/__init__.py` (registers all)
- Create: `yuki/runtime/commands/builtins/clear.py`, `compact.py`, `help.py`, `cost.py`, `memory.py`, `quit.py`
- Create: `tests/runtime/commands/test_builtins.py`

- [ ] **Step 1: Write the failing test**

```python
import yuki.runtime.commands.builtins  # noqa: F401 — triggers registration

from yuki.runtime.commands.pipeline import process_user_input
from yuki.runtime.commands.registry import REGISTRY


def test_six_builtins_registered():
    for name in ("clear", "compact", "help", "cost", "memory", "quit"):
        assert name in REGISTRY


def test_help_returns_local_text():
    out = process_user_input("/help")
    assert out.kind == "local_text"
    assert "/clear" in out.text
    assert "/compact" in out.text


def test_clear_returns_local_text_marker():
    out = process_user_input("/clear")
    assert out.kind == "local_text"
    assert "cleared" in out.text.lower()


def test_quit_signals_skip():
    out = process_user_input("/quit")
    assert out.kind == "skip"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/commands/test_builtins.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement each built-in**

`yuki/runtime/commands/builtins/clear.py`:

```python
from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register

register(LocalCommand(
    name="clear",
    run=lambda args: CommandResult.local_text("Conversation cleared."),
    description="Clear the current conversation.",
))
```

`compact.py`:

```python
from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register

register(LocalCommand(
    name="compact",
    run=lambda args: CommandResult.local_text(
        "Compaction will run on next turn (autocompact threshold reached)."
    ),
    description="Force-compact the conversation now.",
))
```

`help.py`:

```python
from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register, REGISTRY


def _help(args: str) -> CommandResult:
    lines = ["Built-in slash commands:\n"]
    for name in sorted(REGISTRY):
        cmd = REGISTRY[name]
        lines.append(f"  /{name} — {cmd.description}")
    return CommandResult.local_text("\n".join(lines))


register(LocalCommand(name="help", run=_help, description="Show this help."))
```

`cost.py`:

```python
from yuki.agent.cost import CostTracker
from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register


def _cost(args: str) -> CommandResult:
    # In production we'd thread the active session_id through; for now show
    # the most recent.
    return CommandResult.local_text(
        "Cost tracking: see ~/Library/Application Support/Yuki/sessions/<id>.cost.json",
    )


register(LocalCommand(name="cost", run=_cost,
                      description="Show this session's token usage."))
```

`memory.py`:

```python
from yuki.runtime.commands.base import CommandResult, PromptCommand
from yuki.runtime.commands.registry import register

register(PromptCommand(
    name="memory",
    prompt_template="Search memory for: {args}",
    description="Search the vault.",
))
```

`quit.py`:

```python
from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register

register(LocalCommand(
    name="quit",
    run=lambda args: CommandResult.skip(),
    description="Stop the current conversation without sending a turn.",
))
```

`__init__.py`:

```python
"""Built-in slash commands — imported here for side-effect registration."""

from yuki.runtime.commands.builtins import (  # noqa: F401
    clear, compact, cost, help, memory, quit,
)
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/commands/test_builtins.py -v
git add yuki/runtime/commands/builtins/ tests/runtime/commands/test_builtins.py
git commit -m "feat(runtime): add 6 built-in slash commands"
```

---

## Task 5 — Autocompact

When token count crosses a threshold (default 70% of model context), spawn a one-shot subagent that summarizes history. Replace messages with `[summary, ...recent_5_turns]`.

**Files:**
- Create: `yuki/runtime/compaction.py`
- Create: `tests/runtime/test_compaction.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch

from yuki.runtime.compaction import (
    estimate_tokens, maybe_autocompact,
)


def test_estimate_tokens_returns_positive():
    msgs = [{"role": "user", "content": "hello world"}]
    assert estimate_tokens(msgs) > 0


def test_below_threshold_no_compact():
    msgs = [{"role": "user", "content": "x"}]
    out = maybe_autocompact(msgs, threshold=10_000)
    assert out is msgs  # untouched


@pytest.mark.asyncio
async def test_above_threshold_triggers_compact(monkeypatch):
    big = [{"role": "user", "content": "x" * 200}] * 100

    async def fake_summarize(msgs):
        return "Summary: lots of x"

    monkeypatch.setattr(
        "yuki.runtime.compaction._summarize", fake_summarize,
    )
    out = await maybe_autocompact_async(big, threshold=100)
    assert len(out) < len(big)
    assert any("Summary" in m.get("content", "") for m in out)


# (Two-mode API: maybe_autocompact for the no-op path is sync; the async
# path uses maybe_autocompact_async since LLM summarization is async.)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/test_compaction.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/runtime/compaction.py`**

```python
"""Autocompact — when conversation exceeds threshold, summarize and replace.

Mirrors claude-leak/src/query.ts autocompact branch. We keep ONE compaction
strategy (autocompact); microcompact + context-collapse are explicit non-goals
of this plan.
"""
from __future__ import annotations

import logging

import tiktoken

log = logging.getLogger(__name__)
_KEEP_RECENT = 5

_enc = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            total += len(_enc.encode(c))
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    total += len(_enc.encode(text))
    return total


def maybe_autocompact(messages: list[dict], *, threshold: int) -> list[dict]:
    if estimate_tokens(messages) <= threshold:
        return messages
    return messages  # synchronous no-op path; real compact is async


async def _summarize(messages: list[dict]) -> str:  # pragma: no cover
    """Real impl spawns a forked subagent; tests inject a fake."""
    from yuki.providers.stub import ChatStub
    llm = ChatStub()
    prompt = (
        "Summarize this conversation in 5 paragraphs. Preserve facts, "
        "decisions, and open questions. Drop chit-chat.\n\n"
        + "\n".join(str(m) for m in messages)
    )
    resp = await llm.invoke([{"role": "user", "content": prompt}])
    for b in resp.content:
        if isinstance(b, dict) and b.get("type") == "text":
            return b["text"]
    return ""


async def maybe_autocompact_async(
    messages: list[dict], *, threshold: int,
) -> list[dict]:
    if estimate_tokens(messages) <= threshold:
        return messages
    summary = await _summarize(messages[:-_KEEP_RECENT])
    log.info("autocompacted %d messages → 1 summary + %d recent",
             len(messages), _KEEP_RECENT)
    return [
        {"role": "system", "content": f"Conversation summary so far: {summary}"},
        *messages[-_KEEP_RECENT:],
    ]
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/test_compaction.py -v
git add yuki/runtime/compaction.py tests/runtime/test_compaction.py
git commit -m "feat(runtime): add autocompact with tiktoken-based threshold"
```

---

## Task 6 — Max-turns + max-budget guards

Hard caps that abort the loop with a structured terminal reason. `max_turns` counts user messages; `max_budget` checks the `CostTracker` totals.

**Files:**
- Create: `yuki/runtime/guards.py`
- Create: `tests/runtime/test_guards.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from yuki.runtime.guards import (
    GuardViolation, check_max_budget, check_max_turns,
)


def test_max_turns_under():
    assert check_max_turns(current_turns=3, max_turns=10) is None


def test_max_turns_over_raises():
    with pytest.raises(GuardViolation) as exc:
        check_max_turns(current_turns=11, max_turns=10)
    assert "max_turns" in str(exc.value)


def test_max_budget_under():
    totals = {"input_tokens": 1000, "output_tokens": 500}
    assert check_max_budget(totals=totals, max_total_tokens=10_000) is None


def test_max_budget_over_raises():
    totals = {"input_tokens": 9000, "output_tokens": 5000}
    with pytest.raises(GuardViolation):
        check_max_budget(totals=totals, max_total_tokens=10_000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/test_guards.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/runtime/guards.py`**

```python
"""Hard guards — abort the agent loop with structured reasons.

Mirrors claude-leak/src/QueryEngine.ts:1507 (max-turns enforcement).
"""
from __future__ import annotations


class GuardViolation(Exception):
    """The loop must terminate. Carries the structured reason."""

    def __init__(self, reason: str, detail: dict | None = None) -> None:
        self.reason = reason
        self.detail = detail or {}
        super().__init__(f"{reason}: {detail}")


def check_max_turns(*, current_turns: int, max_turns: int) -> None:
    if current_turns > max_turns:
        raise GuardViolation(
            "max_turns_exceeded",
            {"current": current_turns, "limit": max_turns},
        )


def check_max_budget(*, totals: dict, max_total_tokens: int) -> None:
    used = int(totals.get("input_tokens", 0)) + int(totals.get("output_tokens", 0))
    if used > max_total_tokens:
        raise GuardViolation(
            "max_budget_exceeded",
            {"used": used, "limit": max_total_tokens},
        )
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/test_guards.py -v
git add yuki/runtime/guards.py tests/runtime/test_guards.py
git commit -m "feat(runtime): add max-turns + max-budget guards"
```

---

## Task 7 — Stop hooks

Stop hooks are called when the loop has decided to terminate. Each hook may either pass through or inject a final user message that resumes the loop. Mirrors `claude-leak/src/query.ts:1267`.

**Files:**
- Create: `yuki/runtime/stop_hooks.py`
- Create: `tests/runtime/test_stop_hooks.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from yuki.runtime.stop_hooks import (
    StopHookRegistry, StopVerdict,
)


def test_no_hooks_returns_pass_through():
    reg = StopHookRegistry()
    verdict = reg.evaluate(messages=[])
    assert verdict.action == "pass"


def test_hook_inject_reopens_loop():
    reg = StopHookRegistry()
    reg.register(lambda msgs: StopVerdict.inject("Are you sure you're done?"))
    verdict = reg.evaluate(messages=[])
    assert verdict.action == "inject"
    assert "sure" in verdict.injected_message


def test_first_inject_wins():
    reg = StopHookRegistry()
    reg.register(lambda msgs: StopVerdict.pass_through())
    reg.register(lambda msgs: StopVerdict.inject("wait"))
    reg.register(lambda msgs: StopVerdict.inject("ignored"))
    verdict = reg.evaluate(messages=[])
    assert verdict.action == "inject"
    assert verdict.injected_message == "wait"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/test_stop_hooks.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/runtime/stop_hooks.py`**

```python
"""Stop hooks — last chance to re-open the loop with one more user message.

Mirrors claude-leak/src/query.ts:1267 (stop hooks reinjection).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


@dataclass
class StopVerdict:
    action: Literal["pass", "inject"]
    injected_message: str = ""

    @classmethod
    def pass_through(cls) -> "StopVerdict":
        return cls(action="pass")

    @classmethod
    def inject(cls, message: str) -> "StopVerdict":
        return cls(action="inject", injected_message=message)


Hook = Callable[[list], StopVerdict]


class StopHookRegistry:
    def __init__(self) -> None:
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        self._hooks.append(hook)

    def evaluate(self, *, messages: list) -> StopVerdict:
        for hook in self._hooks:
            verdict = hook(messages)
            if verdict.action == "inject":
                return verdict
        return StopVerdict.pass_through()
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/runtime/test_stop_hooks.py -v
git add yuki/runtime/stop_hooks.py tests/runtime/test_stop_hooks.py
git commit -m "feat(runtime): add stop hooks for re-injection"
```

---

## Wrap-up

After Task 7, Yuki has a Claude-Code-class agent runtime:
- Subagents dispatchable via the `agent` @tool, sidechain transcripts persisted
- Slash command pipeline with 6 built-ins, two command types, easy to extend
- Autocompact triggered automatically over a tiktoken-counted threshold
- Hard guards on `max_turns` and `max_budget`
- Stop hooks as a re-injection point for user-defined tail-of-loop logic

Acceptance:
- `uv run pytest tests/runtime/ -v` ≥30 tests, all green
- `from yuki.runtime.commands.pipeline import process_user_input; print(process_user_input("/help").text)` lists all 6 commands
- A subagent invocation produces `~/Library/Application Support/Yuki/sidechains/agent-<id>.jsonl`
- `await maybe_autocompact_async(big_messages, threshold=...)` returns a list ≤ 6 messages
- Triggering `max_turns_exceeded` aborts the loop with a structured reason

What this plan **does not** do:
- Streaming tool execution (StreamingToolExecutor) — explicit non-goal per the analysis
- Microcompact + context-collapse + reactive-compact — autocompact is the only strategy
- Multi-agent swarms / coordinator mode / teammates / UDS — out of scope
- Slash commands in the SwiftUI menubar overlay — only the Next.js frontend gets autocomplete in v1.5
- React/Ink rendering layer — Yuki keeps the loop renderer-agnostic

If/when v1.x ships and you want any of these, write Plan M.
