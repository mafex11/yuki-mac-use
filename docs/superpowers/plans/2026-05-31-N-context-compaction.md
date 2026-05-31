# Plan N — Context tracking + compaction (Claude-Code-style)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Show the user how full their conversation context is, and let them (or
the system) compact stale history into a single summary message — same UX as
Claude Code's percentage badge + `/compact` command.

**Architecture:**

1. **Local token estimator** — char-based heuristic (`len(text) // 4`), uniform
   across providers (no API dependency).
2. **Context tracker** — small dataclass per conversation, holds the running
   token count and the model's effective context window.
3. **Auto + manual compaction** — auto-trigger when usage ≥ 80%; manual via
   `/compact` slash-command in chat_cli. Compaction calls the configured LLM
   to summarize the history, then replaces all but the system prompt with the
   summary as a synthetic user/assistant exchange.
4. **REPL badge** — `chat_cli` prints `[ctx 24% • 12k/50k]` on every assistant
   reply. Surfaces usage without being noisy.

**Tech Stack:** stdlib only for estimation. `make_llm()` for compaction calls.

**Spec reference:** Claude Code's `services/compact/` (~4500 lines for full
fidelity; we replicate the user-visible behaviour, not internal optimisations
like microcompact / sessionMemoryCompact).

---

## File structure

```
yuki/
├── runtime/
│   ├── compaction.py        # MODIFIED — add ContextTracker, run_compaction()
│   └── tokens.py            # NEW — local estimator
└── backend/
    ├── chat_cli.py          # MODIFIED — print badge, handle /compact
    └── routers/chat.py      # MODIFIED — track usage per turn
```

---

## Order of execution

1. Local token estimator
2. ContextTracker dataclass + window-size lookup
3. Compaction prompt + executor (uses make_llm())
4. /chat tracker wiring (multi-turn already returns one event per turn)
5. /control tracker wiring (estimate the framed task + system prompt + state)
6. chat_cli badge + /compact slash-command
7. Auto-compact at 80%

Total estimate: ~3 hours.

---

## Task 1 — Local token estimator

**File:** `yuki/runtime/tokens.py`

```python
"""Cheap char-based token estimator -- no provider deps.

OpenAI tiktoken averages ~4 chars/token for English. We round up to be
conservative when comparing against the context window threshold.
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN


def estimate_messages_tokens(messages) -> int:
    total = 0
    for m in messages:
        content = getattr(m, "content", "") or ""
        if isinstance(content, list):
            for part in content:
                total += estimate_tokens(str(part))
        else:
            total += estimate_tokens(str(content))
        # ~10 tokens overhead per message for role markers / formatting.
        total += 10
    return total
```

---

## Task 2 — ContextTracker + window lookup

**File:** `yuki/runtime/compaction.py` (modify existing)

Add at top of file:

```python
from dataclasses import dataclass, field
from yuki.runtime.tokens import estimate_messages_tokens

# Context window per model. Conservative defaults; override via env.
_DEFAULT_WINDOWS = {
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-7": 200_000,
    "claude-haiku-4-5": 200_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-pro": 2_000_000,
    # Local Ollama models -- conservative
    "qwen3-vl:8b": 32_000,
    "deepseek-r1:1.5b": 32_000,
}

_BUFFER_TOKENS = 8_000           # Reserve for output + summary
_AUTO_COMPACT_PCT = 0.80         # Trigger auto-compaction at 80% used


def context_window_for(model: str) -> int:
    return _DEFAULT_WINDOWS.get(model, 32_000)


def effective_context_window(model: str) -> int:
    return context_window_for(model) - _BUFFER_TOKENS


@dataclass
class ContextTracker:
    model: str
    used_tokens: int = 0
    last_messages_count: int = 0

    @property
    def window(self) -> int:
        return effective_context_window(self.model)

    @property
    def percent_used(self) -> float:
        return min(100.0, (self.used_tokens / self.window) * 100.0)

    @property
    def percent_left(self) -> float:
        return max(0.0, 100.0 - self.percent_used)

    @property
    def should_auto_compact(self) -> bool:
        return self.percent_used >= (_AUTO_COMPACT_PCT * 100.0)

    def update_from_messages(self, messages) -> None:
        self.used_tokens = estimate_messages_tokens(messages)
        self.last_messages_count = len(messages)

    def badge(self) -> str:
        return (
            f"[ctx {int(self.percent_used)}% "
            f"• {self.used_tokens // 1000}k/{self.window // 1000}k]"
        )
```

---

## Task 3 — Compaction executor

Append to `yuki/runtime/compaction.py`:

```python
import asyncio
import logging
from yuki.messages import HumanMessage, SystemMessage
from yuki.providers.factory import make_llm

log = logging.getLogger(__name__)

_COMPACT_PROMPT = """You are summarizing the conversation so far so it can fit
back into a smaller context window. Preserve:

1. The user's original goals / tasks (what they asked for, in order).
2. Decisions made and their reasoning.
3. Concrete state: file paths edited, commands run, URLs visited, app
   coordinates discovered, error messages encountered.
4. Outstanding TODOs or unresolved questions.

Drop:
- Redundant tool-call output (raw AX trees, repeated state captures)
- Polite scaffolding ("I'll now...", "Let me check...")
- Filler thoughts that don't carry forward state.

Output format: one tight markdown summary, ~500-1500 tokens. Use bullet
sections. No preamble, no apology.

Conversation to summarize:

"""


def compact_messages(messages: list, model: str | None = None) -> list:
    """Replace the message list with a single SystemMessage holding a summary
    plus a compact synthetic exchange. Keeps the original SystemMessage if any.
    """
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    body = []
    for m in messages:
        if isinstance(m, SystemMessage):
            continue
        role = m.__class__.__name__.replace("Message", "").lower()
        content = getattr(m, "content", "") or ""
        body.append(f"### {role}\n{content}")
    transcript = "\n\n".join(body)

    llm = make_llm(model=model) if model else make_llm()
    prompt = _COMPACT_PROMPT + transcript
    try:
        event = asyncio.run(
            llm.ainvoke(messages=[HumanMessage(content=prompt)], tools=[])
        )
        summary = (event.content or "").strip() if event else ""
    except Exception as e:
        log.warning("compaction failed: %s -- skipping", e)
        return messages  # Don't lose anything if compaction errors.

    if not summary:
        return messages

    summary_msg = HumanMessage(
        content=f"<conversation_summary>\n{summary}\n</conversation_summary>"
    )
    return [*system_msgs, summary_msg]
```

---

## Task 4 — Wire into /chat (multi-turn)

`yuki/backend/routers/chat.py` -- add tracker per conversation_id:

```python
from yuki.runtime.compaction import ContextTracker, compact_messages

_TRACKERS: dict[str, ContextTracker] = {}

def _tracker_for(conv_id: str | None, model: str) -> ContextTracker:
    key = conv_id or "default"
    t = _TRACKERS.get(key)
    if t is None or t.model != model:
        t = ContextTracker(model=model)
        _TRACKERS[key] = t
    return t
```

In `_stream_chat`, after building `messages`:

```python
tracker = _tracker_for(conversation_id, getattr(llm, "model_name", "?"))
tracker.update_from_messages(messages)
if tracker.should_auto_compact:
    log.info(f"auto-compacting at {int(tracker.percent_used)}%")
    messages = compact_messages(messages, model=tracker.model)
    tracker.update_from_messages(messages)
```

Emit the badge on the final event:

```python
final = {"type": "done", "content": text, "ctx_badge": tracker.badge()}
```

---

## Task 5 — Wire into /control (per-step)

In `yuki/agent/service.py:aloop`, after each turn updates `state.messages`:

```python
# Pseudo -- do once per loop iteration, not per substep retry
if step % 3 == 0:  # check every 3 steps to avoid overhead
    tracker.update_from_messages(self.state.messages)
    if tracker.should_auto_compact:
        self.state.messages = compact_messages(
            self.state.messages, model=tracker.model
        )
```

---

## Task 6 — chat_cli badge + /compact command

`yuki/backend/chat_cli.py`:

```python
def _print_badge(ev: dict) -> None:
    badge = ev.get("ctx_badge")
    if badge:
        print(f"  {badge}", flush=True)

# In the SSE-event loop, on "done": call _print_badge(ev) after printing content.

# In the input loop, before sending:
if user_input.strip().lower() == "/compact":
    print("compacting...", flush=True)
    requests.post(
        f"{base}/chat/compact",
        json={"conversation_id": conv_id},
        headers=auth,
    )
    continue
```

Add a new endpoint `POST /chat/compact` in `routers/chat.py` that calls
`compact_messages` on the tracker for that conversation and resets state.

---

## Task 7 — Auto-compact at 80%

Already covered in Tasks 4 + 5 via `tracker.should_auto_compact`. Add a single
`log.info` line so the user sees it happen.

---

## Acceptance

1. `chat_cli` shows `[ctx 24% • 12k/50k]` after every assistant reply.
2. Typing `/compact` summarizes the conversation; badge drops to single digits.
3. After 80% usage, auto-compact fires once; subsequent turns use the summary.
4. Works across providers (Anthropic, Gemini, Ollama) — uniform local estimator.
5. `/control` long runs (15+ steps) trigger auto-compact mid-run instead of
   blowing the window.

---

## Non-goals

- No microcompact (per-tool-result trimming) — adds complexity Claude Code only
  needs because of how aggressive its agentic loops get.
- No SessionMemoryCompact (cross-session persistence) — we have the vault for
  that long-term.
- No per-token billing display — we don't pay-per-token in self-hosted Ollama
  and don't want to fake numbers for cloud providers.
- No prompt-cache breakpoint hints — provider-specific, defer until Anthropic
  caching is wired.
