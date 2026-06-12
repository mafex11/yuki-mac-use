# Spec R — Make Yuki think: reasoning, autonomy, and perception

**Status:** approved (user confirmed implementation)
**Date:** 2026-06-13
**Goal owner:** Sudhanshu

## Problem

Yuki behaves like a robot, not an intelligent agent. The user must spell every
task out step-by-step ("open Chrome, open a new tab, type youtube.com, go to
home page") instead of stating a goal ("open a MrBeast video on YouTube in
Chrome") and letting the agent figure out the steps.

The user hypothesized the cause is a too-high temperature (2–3). **That
hypothesis is wrong** and is explicitly ruled out by the code:

- `make_llm` (`yuki/providers/factory.py:73`) passes **no temperature** to any
  provider → each uses its default (~1.0). There is no temperature 2/3 anywhere.
- Temperature is token randomness, not reasoning depth. Higher temperature would
  make Yuki *more* chaotic (hallucinated coords, malformed tool calls), not more
  thoughtful.

## Root causes (code-level diagnosis)

Three real causes, in order of impact:

1. **Extended thinking is OFF.** `ChatAnthropic` (`thinking_budget`,
   `anthropic/llm.py:28,47-87`), `ChatGoogle` (`thinking_budget`,
   `google/llm.py:36,212-214`), and `ChatOpenAI` (o-series reasoning,
   `openai/llm.py:77-79`) all fully support reasoning. The agent loop already
   captures and replays thinking blocks across tool turns
   (`agent/service.py:252,484`). But `make_llm` never enables it → the model
   gets a 1-3 sentence `thought` field and must immediately emit a tool call.
   It is structurally denied room to think before acting. **Biggest lever.**

2. **Default model/prompt mismatch.** `agent_mode_for` (`factory.py:131-140`)
   gives Ollama the lean `system_flash.md`, which **strips the entire `plan`
   field** — no decomposition scaffold at all. Cloud models (Claude/Gemini) get
   `system.md`, which *does* have a DONE/ACTIVE/TODO `plan` field. So a local 7B
   default genuinely cannot plan; cloud models can but aren't told to act
   autonomously.

3. **Prompt rewards literal obedience.** `system.md` is a ~200-line mechanical
   rulebook ("do X, never Y, wait here"). It never frames Yuki as an autonomous
   goal-pursuer who infers unstated steps. It optimizes compliance over judgment.

A fourth, enabling factor: **perception gaps.** Good reasoning needs good eyes.
The AX classifier tags ~8 of 29+ interactive roles; element *state*
(checked/expanded/selected/enabled) is not captured; many controls reach the
model with empty names; the screen is a flat list with no container context;
lean mode caps at 25 nodes and can silently drop meaningful controls.

## Scope

Three workstreams, sequenced by impact. Temperature is explicitly **not**
changed (it is correct as-is).

### Workstream 1 — Enable reasoning for cloud models (highest impact)

Turn on extended thinking by default for the control agent on cloud providers.

- Add a thinking budget to the control-agent LLM construction
  (`yuki/backend/routers/chat.py` `_stream_control`, and a shared helper in the
  factory) for `anthropic` and `google`; pass o-series reasoning for `openai`.
- Default budget: a moderate value (e.g. 2048 tokens) — enough to plan a
  multi-step GUI task, small enough to keep latency/cost sane. Configurable.
- **Do not** enable thinking for Ollama by default (local small models thinking
  is slow and unreliable; revisit later).
- Verify thinking blocks survive multi-turn tool-call sequences (the loop
  already threads `thinking`/`thinking_signature` — confirm with a test).
- Anthropic requires `temperature=1` when thinking is on; the provider already
  handles that (`anthropic/llm.py:83-87`). Honor it.

**Acceptance:** with a cloud model, a single goal prompt ("open a MrBeast video
on YouTube in Chrome") drives a multi-step run to completion without the user
enumerating steps. The agent's `thought`/thinking shows it decomposed the goal.

### Workstream 2 — Reframe the prompt for autonomous goal decomposition

- Rewrite the framing of `system.md` so Yuki treats the user's input as a
  **goal to be decomposed**, not a literal one-step instruction. Add an explicit
  principle: *"The user states a goal; you infer and execute the steps. Do not
  require the user to spell out each action."* Add a worked example mirroring the
  MrBeast/YouTube/Chrome case (launch → new tab → navigate → search → click).
- Keep all the hard-won mechanical rules (coords from current state, wait policy,
  AX-blindness fallbacks) — those are correct. Only the *framing/altitude*
  changes from "obey literally" to "pursue the goal autonomously."
- Strengthen `system_flash.md`: reintroduce a minimal one-line plan field so even
  flash mode decomposes (without bloating it back to 200 lines).

**Acceptance:** prompt review + a live run showing decomposition; flash-mode
local model still passes the existing eval suite (no regression).

### Workstream 3 — Deepen AX perception (the eyes)

Make Yuki deterministically perceive every interactive element. AX-only — no
vision-fusion layer, no perception benchmark this round.

1. **Full classifier coverage** (`canonical.py`): tag every interactive role
   currently returning `None` — `button` (generic), `checkbox`, `radio_button`,
   `toggle`, `slider`, `popup_button`, `menu_item`, `disclosure`, `stepper`,
   `segmented_control`, `image`.
2. **Capture state** (`ax/core.py` + `tree/service.py`): read `AXValue`,
   `kAXExpandedAttribute`, `AXSelected`, `AXEnabled` → fold `checked`,
   `expanded`, `selected`, `enabled`, `value` into node metadata.
3. **Resolve labels** (`ax/core.py` + `tree/service.py`): when a control lacks
   `AXTitle`, resolve `kAXTitleUIElementAttribute` / nearest static-text sibling
   to recover its visible label.
4. **Container context** (`tree/service.py` + `views.py`): tag each node with the
   nearest meaningful container (dialog/sheet/group); render a `context` column.
5. **Render + smarter lean cap** (`views.py`): show new state in the table; never
   let the 25-node cap drop a stateful or focused element — drop decoration first.

**Acceptance:** TDD unit tests (mirroring `test_canonical.py`) for each new role
and state attribute; one manual smoke on perception-dense screens (System
Settings toggles, a Save dialog with checkboxes, a slider).

## Non-goals (this round)

- No temperature change (it's correct).
- No vision-fusion layer (AX-only).
- No perception benchmark.
- No action *verification* layer (fire-and-forget stays; flagged as next phase).
- No local-model thinking, no fine-tuning loop, no self-improvement loop (later).

## Testing strategy

- TDD for perception (Workstream 3) and the thinking-config plumbing
  (Workstream 1), mirroring existing test style in `tests/agent/tree/` and
  `tests/providers/`.
- Prompt changes (Workstream 2) verified by review + a live control run.
- Full suite (`uv run pytest -q`) stays green except the 2 known
  `test_factory.py` keychain failures on this dev machine.
- Commits carry NO Claude attribution (repo rule).

## Order of execution

1. Workstream 1 (thinking) — biggest, smallest, lowest-risk. Ship first.
2. Workstream 2 (prompt) — pairs with 1; together they deliver "it thinks."
3. Workstream 3 (perception) — strengthens the eyes; larger, independent.
