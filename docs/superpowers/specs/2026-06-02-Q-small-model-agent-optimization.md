# Plan Q: Small-Model Agent Optimization + Fine-Tuning — Design Spec

**Status:** Approved design — ready for implementation planning.
**Date:** 2026-06-02

**Goal:** Make Yuki's desktop-control agent reliable on small local models — target: a fine-tuned llama3.2:1b that matches or beats cloud models on Yuki's tools — by first optimizing the per-step context every model receives, then (if measurement shows it's needed) restructuring the agent loop, and finally fine-tuning a small model against the stabilized format.

**Architecture:** Two phases. Phase A adds *input-shaping filters* (Tool RAG + AX-tree pruning) to the existing agent loop for all models, measured by a small eval harness, with a decision gate that conditionally triggers a planner/executor restructure. Phase B is an offline fine-tuning pipeline built against Phase A's finalized format. The cloud-model path is protected throughout because the eval harness proves no regression at each step.

**Tech stack:** Python agent (`yuki/agent/`), local embeddings (Ollama `/api/embeddings`), the existing Pydantic tool schemas + `canonical.py` AX classifier, LoRA fine-tuning (`training/`, outside the shipped package), Ollama for serving the fine-tuned GGUF.

---

## Background: why this is needed (verified empirically)

On 2026-06-02 we observed qwen2.5:3b fail "open calculator": it emitted an empty/malformed `done_tool` and did nothing. Root causes, confirmed by testing:

1. **A `done_tool` bug** (already fixed on `main`, commit 92de94e): a malformed terminal call counted as success. Fixed independently of this plan.
2. **Context overload** (this plan): the real agent sends **16 tool schemas + a full accessibility-tree dump + history** on every step. A clean 2-tool probe showed qwen2.5:3b *can* pick `app_tool` correctly — but under the full runtime context it collapses to degenerate output. This is a capacity ceiling, not a bug.

The research basis (fetched 2026-06-02):
- **TinyAgent** (Berkeley) — a "local Siri-like" 16-function Mac agent; a fine-tuned **1.1B model went 12.71% → 80.35%, beating GPT-4-Turbo (79.08%)**. Two levers: **Tool RAG** (show ~4 of 16 tools, prompt 2762→1397 tokens, recall 0.998) and **fine-tuning** on synthetic function-calling data (the dominant lever). TinyAgent used a plain loop — *no planner/executor split*.
- **ReWOO** — decoupling reasoning from observation "offloaded reasoning from 175B GPT-3.5 into 7B LLaMA," 5× fewer tokens.
- **LLMCompiler** (ICML 2024) — planner / task-fetcher / executor over a tool DAG.
- **NVIDIA "SLMs are the Future of Agentic AI"** — agents do specialized repetitive tasks; heterogeneous (right-size-per-task) systems are the recommended direction.
- **Generative Agents** (Stanford) — memory stream + recency/importance/relevance retrieval + reflection (informs future memory work, not in scope here).

Key takeaway driving the phasing: TinyAgent hit 80% on a **plain loop** with Tool RAG + fine-tuning. The planner/executor split is primarily a latency/cost optimization, not the reliability fix — so it is made **conditional** on a measurement.

---

## Current-code grounding (where the hooks are)

- **Tools → LLM:** `yuki/agent/service.py` — the `tools` property (line ~153) returns `self.registry.get_tools()`; consumed at the LLM calls (lines ~229 sync, ~460 async). Tool RAG filters here.
- **AX-tree → text:** `yuki/agent/tree/views.py` `interactive_elements_to_string()` dumps every interactive node as `id|window|control_type|canonical|name|coords|focused|metadata` with full `json.dumps(metadata)`. AX-pruning changes this.
- **State prompt assembly:** `yuki/agent/context/service.py` `_build_state_prompt()` fills `human.md` with `interactive_elements` / `scrollable_elements`.
- **Prompt mode:** `Agent(mode="flash"|"normal")`; `agent_mode_for(llm)` (in `yuki/providers/factory.py`) already routes Ollama→flash. Plan Q builds on this.
- **Embedder infra:** `yuki/memory/embeddings.py` has an `Embedder` Protocol + Voyage/OpenAI/Stub. These are cloud; Tool RAG needs a **local** option.
- **No agent eval harness exists** — Plan Q creates it.
- **Loop:** single ReAct-style loop in `service.py` (sync `_run` + async `_arun`). Phase A2 wraps it with a planner; it is NOT rewritten.

---

## Phase A1 — Foundation (build unconditionally, all models)

### A1.1 — Eval harness (build FIRST)

Everything downstream is measured by this. Start **minimal (~10 cases)**; grow to ~30+ in Phase B.

**Files:** `yuki/eval/__init__.py`, `yuki/eval/cases.py`, `yuki/eval/score.py`, `yuki/eval/run.py`; tests in `tests/eval/`.

- `cases.py` — `EvalCase{task: str, expected_plan: list[ExpectedStep], reactive: bool, ax_fixture: str | None}` where `ExpectedStep{tool: str, args_matcher: dict[str, str]}`. Args matchers are regexes/predicates, not literals (e.g. `app_tool` name matches `(?i)calc`), so casing/paraphrase doesn't false-fail. `ax_fixture` is an optional path to a canned (pruned) AX-tree snapshot fed as the step's screen state for cases where the correct first tool depends on what's on screen; `None` for tasks decidable from the instruction alone (e.g. "open calculator"). This keeps the harness deterministic (no live Mac) while still exercising state-dependent decisions. ~10 cases spanning: open-app, type, click, shortcut, shell, a 2-step task, and a conversational/done-only task.
- `score.py` — two metrics per case:
  - **toolset_score**: did the emitted plan use the right set of tools (order-independent)? Lenient signal.
  - **graph_score**: right tools, right order, args satisfy matchers — 1.0/0.0 per case (TinyAgent's strict metric).
  - For `reactive=True` cases, only the **first step** is scored (later steps legitimately depend on observation).
- `run.py` — runs the suite against any LLM. Pre-A2 (no planner yet) it scores the **first tool call** the model emits given task + tools; post-A2 it scores the full emitted plan. Same harness, richer input. Returns `{model, mode, toolset_score, graph_score, per_case}`. CLI: `python -m yuki.eval.run --model llama3.2:1b --mode flash`.
- **Self-test:** `tests/eval/` drives the grader with a stub LLM emitting a known plan and asserts correct scoring — trust the ruler before measuring with it.

### A1.2 — Tool RAG

**Files:** `yuki/agent/toolrag.py` (new); hook in `yuki/agent/service.py` `tools` property.

- **Local embedder:** add `OllamaEmbedder` to `yuki/memory/embeddings.py` (calls Ollama `/api/embeddings`, default model `nomic-embed-text`), conforming to the existing `Embedder` Protocol. Falls back to a configured cloud embedder, then to a keyword heuristic if no embedder is reachable (so Tool RAG degrades gracefully, never hard-fails).
- **Index:** at agent start, embed each tool's `name + ". " + description` once.
- **Select(task) → tools:** embed the task, cosine-rank, take **top-K (default 5)** ∪ **always-include** (`done_tool`, `app_tool`, `shell_tool`).
- The `tools` property returns the filtered set. **Fallback:** if execution needs a tool not selected, widen to the full set for that step and log it (RAG can never block a task).
- **Config:** `YUKI_TOOLRAG=1|0` (default on for Ollama, decided for cloud by the eval harness), `YUKI_TOOLRAG_K` (default 5).

### A1.3 — AX-tree pruning

**Files:** `yuki/agent/tree/views.py` `interactive_elements_to_string()` (+ a `verbosity` param threaded from `context/service.py`).

- Add `verbosity: Literal["full", "lean"]` (default preserves today's `full` behavior).
- `lean` mode:
  - Keep the `<focused_input>` block verbatim (already high-signal).
  - Rank nodes: focused first, then interactive controls by canonical priority (`url_bar`/`search_field`/`primary_input`/`submit_button` before generic), drop pure-decorative.
  - Cap at **top-N (default 25)**.
  - **Trim metadata** to `{value, placeholder, role}` (or the subset present) instead of `json.dumps(everything)`.
- `context.state(...)` / `_build_state_prompt(...)` pass `verbosity="lean"` for small/local models, `"full"` otherwise (driven by the same model-tier signal as `agent_mode_for`). Cloud default stays `full` unless the eval harness shows `lean` is neutral-or-better for them.

### A1 → DECISION GATE

Run `yuki/eval/run.py` on llama3.2:1b and qwen2.5:3b, `mode=flash`, with A1.2+A1.3 active.

- **PASS** (graph_score clears an agreed bar, e.g. simple cases reliably correct): **skip/defer Phase A2.** Proceed to Phase B.
- **FAIL:** proceed to Phase A2, now justified by data, on the already-pruned foundation.

Record the gate result in the plan's execution notes either way.

---

## Phase A2 — Planner/executor loop (CONDITIONAL on the gate)

Fully specified so execution continues with zero re-design if the gate fails. **All models** use it; the existing single loop remains as a fallback mode.

**Files:** `yuki/agent/planner.py` (new — planner call + plan schema); executor logic extends the loop in `yuki/agent/service.py` (wraps, does not replace, the existing observe→act machinery).

**Shape — "plan high-level, observe per step":**
1. **Planner** (one LLM call): input = task + RAG-selected tool *menu* (names + one-line descriptions, **no screen state**). Output = a coordinate-free ordered step list, each `{tool, intent}` (e.g. `1. app_tool: open Calculator / 2. type_tool: "5+5" / 3. done_tool`). Pydantic schema validates it (valid tool names, ≥1 step, ends with `done_tool` for action tasks).
2. **Executor** (loop, one LLM call per step): for each step, input = **only** `{this step's intent + freshly-pruned AX-tree (lean)}` — not the whole task, not full history, not all 16 tools. It resolves the concrete action (coords from the live tree) and runs it via the existing registry.
3. **Re-plan trigger:** if a step fails, or the observed screen diverges from the plan's expectation, return to the planner with the current state to revise *remaining* steps. Bounded: **max 2 replans** per task, then fail honestly.

**Reactive honesty:** the plan is a sketch, not a contract. "message Saran on WhatsApp" plans as `[open app, search, click result, type, done]`; the executor resolves "which result" by observing. This is why high-level-plan beats TinyAgent's full-DAG-with-placeholders — GUI coordinates can't be placeholdered.

**Fallback mode:** `YUKI_AGENT_LOOP=planner|single` (default decided by the gate). `single` = today's behavior, retained so a planner regression can be flipped off instantly.

**Eval:** harness re-run on cloud models confirms no regression; on small models confirms the gain.

---

## Phase B — Fine-tuning pipeline (depends on A's format being stable)

Offline ML. Lives in `training/` (outside the shipped `yuki/` package). Target: **llama3.2:1b**, model-agnostic enough to also try 3b if 1b plateaus.

### B.1 — Dataset generation (`training/gen_dataset.py`)
- A frontier model (Claude/GPT-4/Gemini) synthesizes `(task, expected_plan)` pairs over Yuki's **real 16 tools** and representative AX states, in the **exact plan format Phase A finalized**.
- Coverage: single-action, multi-step, conversational/done-only, failure/recovery. Start ~10-20k pairs; scale if eval plateaus.
- **Automated validation before inclusion:** valid tool names, args type-check against the Pydantic tool schemas, valid step ordering — the same graph-validity checks the eval harness uses. Invalid pairs discarded.
- Output: JSONL train/val/test splits.

### B.2 — Training (`training/train_lora.py`)
- LoRA fine-tune llama3.2:1b (start from TinyAgent's hyperparams: LoRA, ~3 epochs, lr ~7e-5).
- Include **negative samples** (irrelevant tools in the prompt) so the model learns tool *selection*, per TinyAgent's key finding.
- Output: LoRA adapter → merged GGUF → Ollama `Modelfile` so it loads as a normal Ollama model.

### B.3 — Validation (reuses the eval harness, grown to ~30+ cases)
- Ship gate: fine-tuned 1b's **graph_score ≥ off-the-shelf baseline**, compared against Gemini as the high-water mark.
- The harness is both the training signal and the acceptance test — same ruler throughout.

### B.4 — Distribution
- The fine-tuned model registers like any other Ollama model; Yuki's existing Provider tab lists it. Optionally add to the curated "Yuki-ready" download list (e.g. as `yuki-1b`).

**Dependency note:** Phase B is last because the dataset must match Phase A's final tool/plan/pruning format; generating it earlier would train against a format we then changed.

---

## File structure summary

**New (Phase A):**
- `yuki/eval/{__init__,cases,score,run}.py` — eval harness
- `yuki/agent/toolrag.py` — Tool RAG selector
- `yuki/agent/planner.py` — planner (A2, conditional)
- `tests/eval/`, `tests/agent/test_toolrag.py`, (A2) `tests/agent/test_planner.py`

**Modified (Phase A):**
- `yuki/memory/embeddings.py` — add `OllamaEmbedder`
- `yuki/agent/service.py` — Tool RAG hook in `tools` property; (A2) planner/executor wrapping + `YUKI_AGENT_LOOP` fallback
- `yuki/agent/tree/views.py` — `interactive_elements_to_string(verbosity=...)`
- `yuki/agent/context/service.py` — thread `verbosity` into the state prompt

**New (Phase B):**
- `training/gen_dataset.py`, `training/train_lora.py`, `training/Modelfile`, `training/README.md`
- eval cases expanded in `yuki/eval/cases.py`

---

## Testing strategy

- **Eval harness:** self-tested with a stub LLM (grader correctness). It is itself the primary measurement instrument for the feature.
- **Tool RAG:** unit tests — given a task, asserts expected tools are selected (e.g. "open calculator" → `app_tool` ∈ selection; core tools always present; fallback widens on miss).
- **AX-pruning:** unit tests — `lean` mode caps node count, trims metadata, preserves `<focused_input>` and focused/interactive nodes; `full` mode byte-identical to today.
- **Planner (A2):** unit tests with a stub LLM — valid plan parses; invalid plan (bad tool name / empty) rejected; replan triggers on step failure; bounded replan count.
- **Cloud-regression guard:** eval harness run on Gemini/Claude before+after each Phase A layer — graph_score must not drop.
- **Fine-tuning (B):** eval harness is the acceptance test (graph_score ≥ baseline).
- Python throughout; no Swift changes in this plan (the fine-tuned model surfaces via the already-built Provider tab).

---

## Decisions locked during brainstorming

- **Scope:** one spec, Phase A then Phase B, executed in dependency order.
- **Applies to:** all models use the optimized pipeline (not small-only).
- **Eval metric:** plan-correctness via graph-match, no execution.
- **Eval harness sizing:** minimal (~10 cases) up front for the gate; grown to ~30+ for Phase B (it's mandatory for fine-tuning regardless).
- **Tool RAG:** local embedding similarity (Ollama embeddings), top-K ∪ core, graceful fallback.
- **Reactive planning:** plan high-level (coordinate-free), observe per step, bounded re-plan.
- **Planner/executor:** CONDITIONAL on the A1 decision gate; fully specified regardless.
- **Fine-tune base model:** llama3.2:1b (TinyAgent-style), model-agnostic pipeline.
- **Dataset gen:** frontier model synthesizes validated pairs against the finalized format.
- **Commits:** no Claude attribution / Co-Authored-By (repo convention).

## Out of scope (future specs)

- Shared-memory / reflection architecture (Generative-Agents style) — separate concern.
- A trained tool-selection classifier (TinyAgent's DeBERTa) — embedding RAG first; upgrade only if recall is insufficient.
- Multi-model "brain/mouth/hands" parallel orchestration — the research showed context-shaping + fine-tuning on a single model is the higher-leverage path; revisit only if Phase A+B fall short.
