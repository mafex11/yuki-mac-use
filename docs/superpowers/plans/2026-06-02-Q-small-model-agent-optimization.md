# Small-Model Agent Optimization + Fine-Tuning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Yuki's desktop agent reliable on small local models — culminating in a fine-tuned llama3.2:1b that matches/beats cloud models on Yuki's tools — by first shrinking the per-step context every model receives (Tool RAG + AX-tree pruning), measuring the effect with an eval harness, conditionally restructuring the loop (planner/executor), then fine-tuning against the stabilized format.

**Architecture:** Phase A adds input-shaping filters to the *existing* agent loop and a graph-match eval harness; a decision gate then conditionally triggers a planner/executor restructure. Phase B is an offline LoRA pipeline (`training/`, outside the shipped package) validated by the same harness. The cloud path is protected by running the harness before/after each Phase-A change.

**Tech Stack:** Python 3.12, `uv`, pytest; local embeddings via Ollama `/api/embeddings`; existing Pydantic tool schemas + `canonical.py` AX classifier; LoRA fine-tuning + Ollama GGUF serving (Phase B).

---

## Conventions for every task (read once)

- **Run tests:** `uv run pytest <path> -q -p no:unraisableexception` (the flag suppresses benign socket/loop teardown warnings in this repo).
- **Commits:** NO Claude attribution, NO `Co-Authored-By` trailers (repo rule). Use the exact message given in each task.
- **Branch:** create `yuki/small-model-opt` off `main` before Task 1 (do not work on `main`). Do not switch branches mid-plan.
- **Spec reference:** `docs/superpowers/specs/2026-06-02-Q-small-model-agent-optimization.md`.
- **Pre-existing failures:** 2 tests in `tests/providers/test_factory.py` fail on this dev machine (real Google key in the login Keychain). They are unrelated — ignore them; everything else must stay green.
- **Phasing:** Tasks 1-9 are Phase A1 (build unconditionally). Task 10 is the DECISION GATE (a measurement, not code). Tasks 11-14 are Phase A2 (build only if the gate fails — but they are fully specified so execution continues with zero redesign). Tasks 15-19 are Phase B (offline ML).

---

## File Structure

**New — Phase A1:**
- `yuki/eval/__init__.py` — package marker
- `yuki/eval/cases.py` — `EvalCase`/`ExpectedStep` types + the ~10-case suite + AX fixtures loader
- `yuki/eval/fixtures/*.txt` — canned pruned AX-tree snapshots for state-dependent cases
- `yuki/eval/score.py` — `score_plan()` grader (toolset_score + graph_score)
- `yuki/eval/run.py` — runs the suite against any LLM; CLI entry
- `yuki/agent/toolrag.py` — `ToolSelector` (embed tools, select top-K per task)
- `tests/eval/test_score.py`, `tests/eval/test_run_with_stub.py`
- `tests/agent/test_toolrag.py`

**New — Phase A2 (conditional):**
- `yuki/agent/planner.py` — `Planner` + `Plan`/`PlanStep` schema
- `tests/agent/test_planner.py`

**New — Phase B:**
- `training/gen_dataset.py`, `training/train_lora.py`, `training/Modelfile`, `training/README.md`

**Modified — Phase A:**
- `yuki/memory/embeddings.py` — add `OllamaEmbedder` + register in `get_embedder()`
- `yuki/agent/tree/views.py` — `interactive_elements_to_string(verbosity=...)`
- `yuki/agent/context/service.py` — thread `verbosity` into the state prompt
- `yuki/agent/service.py` — Tool RAG hook in `tools`; (A2) planner/executor wrapping + `YUKI_AGENT_LOOP`
- `yuki/backend/routers/chat.py` — pass loop mode / verbosity when constructing the control Agent

---

## PHASE A1 — Foundation (build unconditionally)

### Task 1: Eval types + a hand-labeled case suite

**Files:**
- Create: `yuki/eval/__init__.py`, `yuki/eval/cases.py`
- Test: `tests/eval/test_cases.py`

Background: the harness grades a model's emitted tool-call plan against a hand-labeled expected plan. Cases carry an optional `ax_fixture` (path to a canned pruned AX-tree) for decisions that depend on screen state; `None` means the task is decidable from the instruction alone.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_cases.py
"""The eval case suite loads and is well-formed."""
from __future__ import annotations

from yuki.eval.cases import CASES, EvalCase, ExpectedStep


def test_cases_nonempty_and_typed() -> None:
    assert len(CASES) >= 10
    for c in CASES:
        assert isinstance(c, EvalCase)
        assert c.task.strip()
        assert len(c.expected_plan) >= 1
        for step in c.expected_plan:
            assert isinstance(step, ExpectedStep)
            assert step.tool  # non-empty tool name


def test_every_plan_ends_with_done_for_action_tasks() -> None:
    # Action tasks must terminate with done_tool; conversational ones too.
    for c in CASES:
        assert c.expected_plan[-1].tool == "done_tool", c.task


def test_tool_names_are_real() -> None:
    from yuki.agent.tools import BUILTIN_TOOLS
    valid = {t.name for t in BUILTIN_TOOLS}
    for c in CASES:
        for step in c.expected_plan:
            assert step.tool in valid, f"{c.task}: unknown tool {step.tool}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/eval/test_cases.py -q -p no:unraisableexception`
Expected: FAIL — `ModuleNotFoundError: No module named 'yuki.eval'`

- [ ] **Step 3: Create the package + types + suite**

```python
# yuki/eval/__init__.py
"""Plan-correctness eval harness for the desktop agent (graph-match scoring)."""
```

```python
# yuki/eval/cases.py
"""Hand-labeled evaluation cases for agent plan-correctness.

Each case is (task -> expected coordinate-free plan). args_matcher values are
regex patterns applied (case-insensitively) to the corresponding emitted arg.
ax_fixture optionally supplies a canned pruned AX-tree so state-dependent first
steps can be graded deterministically (no live Mac).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExpectedStep:
    tool: str
    # arg name -> regex the emitted arg value must match (case-insensitive).
    args_matcher: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCase:
    task: str
    expected_plan: list[ExpectedStep]
    reactive: bool = False          # if True, only the first step is graded
    ax_fixture: str | None = None   # filename under yuki/eval/fixtures/, or None


CASES: list[EvalCase] = [
    EvalCase(
        task="open calculator",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"calc"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="open the Notes app",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"notes"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="switch to Safari",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"safari"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="open calculator and type 5+5",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"calc"}),
            ExpectedStep("type_tool", {"text": r"5\+5"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="copy the selection",
        expected_plan=[
            ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+c"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="list the files in my Downloads folder",
        expected_plan=[
            ExpectedStep("shell_tool", {"command": r"(?i)ls.*downloads"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="scroll down on this page",
        expected_plan=[
            ExpectedStep("scroll_tool", {"direction": r"(?i)down"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="what is the capital of France?",
        expected_plan=[ExpectedStep("done_tool", {"answer": r"(?i)paris"})],
    ),
    EvalCase(
        task="say hello",
        expected_plan=[ExpectedStep("done_tool")],
    ),
    EvalCase(
        task="click the Submit button",
        expected_plan=[
            ExpectedStep("click_tool"),
            ExpectedStep("done_tool"),
        ],
        reactive=True,
        ax_fixture="submit_button.txt",
    ),
]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/eval/test_cases.py -q -p no:unraisableexception`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/eval/__init__.py yuki/eval/cases.py tests/eval/test_cases.py
git commit -m "feat(eval): plan-correctness eval case suite + types"
```

---

### Task 2: AX fixture for the reactive case

**Files:**
- Create: `yuki/eval/fixtures/submit_button.txt`
- Modify: `yuki/eval/cases.py` (add `load_fixture()` helper)
- Test: `tests/eval/test_cases.py` (add a fixture-loading test)

Background: the one reactive case (`click the Submit button`) needs a canned pruned AX-tree showing a Submit button, so the grader can feed it as screen state and check the model picks `click_tool`. The fixture mimics the `lean` AX format (Task 7) — a header row + node rows.

- [ ] **Step 1: Write the failing test (append)**

```python
def test_load_fixture_returns_text() -> None:
    from yuki.eval.cases import load_fixture
    text = load_fixture("submit_button.txt")
    assert "submit" in text.lower()
    assert "|" in text  # pipe-delimited node rows


def test_missing_fixture_raises() -> None:
    import pytest
    from yuki.eval.cases import load_fixture
    with pytest.raises(FileNotFoundError):
        load_fixture("does_not_exist.txt")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/eval/test_cases.py -q -p no:unraisableexception`
Expected: FAIL — `ImportError: cannot import name 'load_fixture'`

- [ ] **Step 3: Create the fixture + loader**

Create `yuki/eval/fixtures/submit_button.txt`:

```
# id|window|control_type|canonical|name|coords|focused|metadata
0|Form|AXButton|submit_button|Submit|(420,560)|-|{}
1|Form|AXButton|cancel_button|Cancel|(300,560)|-|{}
2|Form|AXTextField|text_input|Email|(360,400)|-|{"value":""}
```

Add to `yuki/eval/cases.py`:

```python
from importlib.resources import files


def load_fixture(name: str) -> str:
    """Read a canned AX-tree fixture from yuki/eval/fixtures/."""
    path = files("yuki.eval").joinpath("fixtures", name)
    if not path.is_file():
        raise FileNotFoundError(f"eval fixture not found: {name}")
    return path.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/eval/test_cases.py -q -p no:unraisableexception`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/eval/fixtures/submit_button.txt yuki/eval/cases.py tests/eval/test_cases.py
git commit -m "feat(eval): AX fixture + loader for reactive case grading"
```

---

### Task 3: The grader (`score.py`)

**Files:**
- Create: `yuki/eval/score.py`
- Test: `tests/eval/test_score.py`

Background: given an `EvalCase` and an *emitted plan* (list of `{tool, args}` dicts), compute `toolset_score` (right tools, order-independent) and `graph_score` (right tools, right order, args match — 1.0/0.0). For `reactive` cases, grade only the first step.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_score.py
"""score_plan grades an emitted plan against an EvalCase."""
from __future__ import annotations

from yuki.eval.cases import EvalCase, ExpectedStep
from yuki.eval.score import score_plan


def _case() -> EvalCase:
    return EvalCase(
        task="open calculator and type 5+5",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"calc"}),
            ExpectedStep("type_tool", {"text": r"5\+5"}),
            ExpectedStep("done_tool"),
        ],
    )


def test_perfect_plan_scores_one() -> None:
    emitted = [
        {"tool": "app_tool", "args": {"name": "Calculator"}},
        {"tool": "type_tool", "args": {"text": "5+5"}},
        {"tool": "done_tool", "args": {"answer": "done"}},
    ]
    r = score_plan(_case(), emitted)
    assert r["graph_score"] == 1.0
    assert r["toolset_score"] == 1.0


def test_wrong_order_fails_graph_passes_toolset() -> None:
    emitted = [
        {"tool": "type_tool", "args": {"text": "5+5"}},
        {"tool": "app_tool", "args": {"name": "Calculator"}},
        {"tool": "done_tool", "args": {}},
    ]
    r = score_plan(_case(), emitted)
    assert r["graph_score"] == 0.0
    assert r["toolset_score"] == 1.0  # same set, wrong order


def test_arg_mismatch_fails_graph() -> None:
    emitted = [
        {"tool": "app_tool", "args": {"name": "Safari"}},  # wrong app
        {"tool": "type_tool", "args": {"text": "5+5"}},
        {"tool": "done_tool", "args": {}},
    ]
    assert score_plan(_case(), emitted)["graph_score"] == 0.0


def test_reactive_grades_first_step_only() -> None:
    case = EvalCase(
        task="click submit",
        expected_plan=[ExpectedStep("click_tool"), ExpectedStep("done_tool")],
        reactive=True,
    )
    # Only the first emitted tool matters for reactive cases.
    emitted = [{"tool": "click_tool", "args": {"loc": [1, 2]}}]
    assert score_plan(case, emitted)["graph_score"] == 1.0


def test_empty_emitted_scores_zero() -> None:
    assert score_plan(_case(), [])["graph_score"] == 0.0
    assert score_plan(_case(), [])["toolset_score"] == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/eval/test_score.py -q -p no:unraisableexception`
Expected: FAIL — `ModuleNotFoundError: No module named 'yuki.eval.score'`

- [ ] **Step 3: Implement the grader**

```python
# yuki/eval/score.py
"""Grade an emitted tool-call plan against an EvalCase.

graph_score (strict): right tools, right order, args satisfy the matchers.
toolset_score (lenient): right set of tools, order-independent.
For reactive cases, only the first step is considered.
"""
from __future__ import annotations

import re
from typing import Any, TypedDict

from yuki.eval.cases import EvalCase, ExpectedStep


class ScoreResult(TypedDict):
    graph_score: float
    toolset_score: float


def _args_match(expected: ExpectedStep, emitted_args: dict[str, Any]) -> bool:
    for key, pattern in expected.args_matcher.items():
        val = emitted_args.get(key)
        if val is None:
            return False
        if re.search(pattern, str(val), re.IGNORECASE) is None:
            return False
    return True


def _step_match(expected: ExpectedStep, emitted: dict[str, Any]) -> bool:
    return (
        emitted.get("tool") == expected.tool
        and _args_match(expected, emitted.get("args") or {})
    )


def score_plan(case: EvalCase, emitted: list[dict[str, Any]]) -> ScoreResult:
    expected = case.expected_plan
    if case.reactive:
        # Only the first step is deterministic for reactive tasks.
        ok = bool(emitted) and _step_match(expected[0], emitted[0])
        return {"graph_score": 1.0 if ok else 0.0,
                "toolset_score": 1.0 if ok else 0.0}

    if not emitted:
        return {"graph_score": 0.0, "toolset_score": 0.0}

    # graph: same length, each position matches tool + args, in order.
    graph_ok = len(emitted) == len(expected) and all(
        _step_match(exp, emitted[i]) for i, exp in enumerate(expected)
    )

    # toolset: same multiset of tool names, order-independent.
    expected_tools = sorted(s.tool for s in expected)
    emitted_tools = sorted(str(e.get("tool")) for e in emitted)
    toolset_ok = expected_tools == emitted_tools

    return {"graph_score": 1.0 if graph_ok else 0.0,
            "toolset_score": 1.0 if toolset_ok else 0.0}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/eval/test_score.py -q -p no:unraisableexception`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/eval/score.py tests/eval/test_score.py
git commit -m "feat(eval): graph-match + toolset grader for emitted plans"
```

---

### Task 4: Eval runner (`run.py`) with a stub-LLM test

**Files:**
- Create: `yuki/eval/run.py`
- Test: `tests/eval/test_run_with_stub.py`

Background: `run.py` runs the suite against an LLM and aggregates scores. Pre-A2 (no planner), it extracts the model's **first tool call** as a one-step emitted plan; post-A2 it will parse a full plan (Task 13 updates the extractor). It must be testable with `ChatStub` (no real model). The runner calls the LLM with the task + tools and reads the resulting tool call.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_run_with_stub.py
"""run_case scores a single case against a stubbed LLM."""
from __future__ import annotations

from yuki.eval.cases import EvalCase, ExpectedStep
from yuki.eval.run import run_case
from yuki.providers.events import LLMEvent, LLMEventType, ToolCall
from yuki.providers.stub.llm import ChatStub


def _stub_emitting(tool: str, args: dict) -> ChatStub:
    ev = LLMEvent(
        type=LLMEventType.TOOL_CALL,
        tool_call=ToolCall(id="x", name=tool, params=args),
    )
    return ChatStub(events=[ev])


def test_run_case_scores_correct_first_tool() -> None:
    case = EvalCase(
        task="open calculator",
        expected_plan=[ExpectedStep("app_tool", {"name": r"calc"}),
                       ExpectedStep("done_tool")],
    )
    stub = _stub_emitting("app_tool", {"thought": "t", "name": "Calculator"})
    result = run_case(case, stub)
    # Pre-A2: graded on the first tool call. app_tool(Calculator) matches step 0.
    assert result["toolset_score"] == 1.0
    assert result["first_tool"] == "app_tool"


def test_run_case_wrong_tool_scores_zero() -> None:
    case = EvalCase(
        task="open calculator",
        expected_plan=[ExpectedStep("app_tool", {"name": r"calc"}),
                       ExpectedStep("done_tool")],
    )
    stub = _stub_emitting("done_tool", {"thought": "t", "answer": "hi"})
    result = run_case(case, stub)
    assert result["toolset_score"] == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/eval/test_run_with_stub.py -q -p no:unraisableexception`
Expected: FAIL — `ModuleNotFoundError: No module named 'yuki.eval.run'`

- [ ] **Step 3: Implement the runner**

```python
# yuki/eval/run.py
"""Run the plan-correctness eval suite against an LLM.

Pre-planner (Phase A1): we grade the model's FIRST tool call for the task,
treating it as a one-step emitted plan and scoring it against expected_plan[0].
Post-planner (Phase A2): extract_plan() is upgraded to parse a full plan.

CLI:  uv run python -m yuki.eval.run --model llama3.2:1b --mode flash
"""
from __future__ import annotations

import argparse
from typing import Any

from yuki.eval.cases import CASES, EvalCase, load_fixture
from yuki.eval.score import score_plan


def _extract_first_tool_call(llm: Any, case: EvalCase) -> list[dict[str, Any]]:
    """Ask the LLM for the task and return [{tool, args}] from its tool call."""
    from yuki.agent.tools import BUILTIN_TOOLS
    from yuki.messages import HumanMessage, SystemMessage

    sys = SystemMessage(content=(
        "You are a macOS control agent. Choose the single best tool to begin "
        "the user's task. Always emit a tool call."
    ))
    parts = [f"Task: {case.task}"]
    if case.ax_fixture:
        parts.append("Screen state:\n" + load_fixture(case.ax_fixture))
    user = HumanMessage(content="\n\n".join(parts))
    event = llm.invoke(messages=[sys, user], tools=BUILTIN_TOOLS)
    tc = getattr(event, "tool_call", None)
    if tc is None:
        return []
    return [{"tool": tc.name, "args": dict(tc.params or {})}]


def run_case(case: EvalCase, llm: Any) -> dict[str, Any]:
    emitted = _extract_first_tool_call(llm, case)
    scores = score_plan(case, emitted)
    return {
        "task": case.task,
        "first_tool": emitted[0]["tool"] if emitted else None,
        **scores,
    }


def run_suite(llm: Any, cases: list[EvalCase] = CASES) -> dict[str, Any]:
    per_case = [run_case(c, llm) for c in cases]
    n = len(per_case) or 1
    return {
        "graph_score": sum(r["graph_score"] for r in per_case) / n,
        "toolset_score": sum(r["toolset_score"] for r in per_case) / n,
        "per_case": per_case,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Ollama model name")
    parser.add_argument("--mode", default="flash", choices=["flash", "normal"])
    args = parser.parse_args()

    if args.model:
        from yuki.providers.ollama.llm import ChatOllama
        llm = ChatOllama(model=args.model)
    else:
        from yuki.providers.factory import make_llm
        llm = make_llm()

    result = run_suite(llm)
    print(f"model={args.model or 'default'} mode={args.mode}")
    print(f"  graph_score:   {result['graph_score']:.2f}")
    print(f"  toolset_score: {result['toolset_score']:.2f}")
    for r in result["per_case"]:
        mark = "✓" if r["graph_score"] == 1.0 else ("~" if r["toolset_score"] == 1.0 else "✗")
        print(f"  {mark} {r['task'][:48]:48} first={r['first_tool']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/eval/test_run_with_stub.py -q -p no:unraisableexception`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/eval/run.py tests/eval/test_run_with_stub.py
git commit -m "feat(eval): suite runner + CLI (first-tool grading pre-planner)"
```

---

### Task 5: Local Ollama embedder

**Files:**
- Modify: `yuki/memory/embeddings.py` (add `OllamaEmbedder`, register in `get_embedder()`)
- Test: `tests/memory/test_ollama_embedder.py`

Background: Tool RAG needs embeddings that work offline alongside local models. The `ollama` Python client exposes `embeddings(model, prompt)`. We conform to the existing `Embedder` Protocol (`dim`, `embed_one`, `embed_batch`). Default model `nomic-embed-text` (768-dim). Tests must not require a running Ollama, so we monkeypatch the client.

- [ ] **Step 1: Write the failing test**

```python
# tests/memory/test_ollama_embedder.py
"""OllamaEmbedder conforms to the Embedder protocol (client mocked)."""
from __future__ import annotations

import pytest

from yuki.memory.embeddings import OllamaEmbedder


class _FakeClient:
    def embeddings(self, model: str, prompt: str):  # noqa: ANN001
        # Return a fixed-length vector derived from text length.
        v = float(len(prompt) % 7) + 1.0
        return {"embedding": [v, v + 1.0, v + 2.0]}


def test_embed_one_returns_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    e = OllamaEmbedder(client=_FakeClient(), dim=3)
    vec = e.embed_one("hello")
    assert len(vec) == 3
    assert e.dim == 3


def test_embed_batch_matches_one(monkeypatch: pytest.MonkeyPatch) -> None:
    e = OllamaEmbedder(client=_FakeClient(), dim=3)
    batch = e.embed_batch(["a", "bb"])
    assert len(batch) == 2
    assert batch[0] == e.embed_one("a")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/memory/test_ollama_embedder.py -q -p no:unraisableexception`
Expected: FAIL — `ImportError: cannot import name 'OllamaEmbedder'`

- [ ] **Step 3: Implement `OllamaEmbedder`**

Add to `yuki/memory/embeddings.py` (after `OpenAIEmbedder`):

```python
class OllamaEmbedder:
    """Local embeddings via Ollama. Works offline. Requires the embed model
    pulled (default 'nomic-embed-text'). `client` is injectable for tests."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        dim: int = 768,
        client: object | None = None,
    ) -> None:
        if client is None:
            import ollama

            client = ollama.Client()
        self._client = client
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        resp = self._client.embeddings(model=self._model, prompt=text)
        vec = resp["embedding"] if isinstance(resp, dict) else resp.embedding
        return list(vec)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]
```

Register it in `get_embedder()` — add this branch before the final `raise`:

```python
    if name == "ollama":
        return OllamaEmbedder()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/memory/test_ollama_embedder.py -q -p no:unraisableexception`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/memory/embeddings.py tests/memory/test_ollama_embedder.py
git commit -m "feat(memory): OllamaEmbedder for local offline embeddings"
```

---

### Task 6: Tool RAG selector

**Files:**
- Create: `yuki/agent/toolrag.py`
- Test: `tests/agent/test_toolrag.py`

Background: `ToolSelector` embeds each tool's `name + ". " + description` once, then for a task returns the top-K most-similar tools UNION an always-include core set (`done_tool`, `app_tool`, `shell_tool`). It uses cosine similarity. The embedder is injected (use `StubEmbedder` in tests — it's deterministic). If embedding fails, it falls back to returning all tools (never blocks). The `Tool` objects have `.name` and `.description`.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_toolrag.py
"""ToolSelector picks task-relevant tools + always-include core."""
from __future__ import annotations

from yuki.agent.toolrag import ToolSelector
from yuki.memory.embeddings import StubEmbedder
from yuki.tools import Tool


def _tools() -> list[Tool]:
    def mk(name: str, desc: str) -> Tool:
        t = Tool(name=name, description=desc)
        return t
    return [
        mk("app_tool", "Open or switch to a macOS application by name"),
        mk("type_tool", "Type text into a focused input field"),
        mk("click_tool", "Click a UI element at coordinates"),
        mk("shell_tool", "Run a shell command or AppleScript"),
        mk("done_tool", "Finish and answer the user"),
        mk("scroll_tool", "Scroll the screen up or down"),
        mk("shortcut_tool", "Press a keyboard shortcut"),
    ]


def test_core_tools_always_included() -> None:
    sel = ToolSelector(_tools(), embedder=StubEmbedder(dim=32), top_k=2)
    chosen = {t.name for t in sel.select("open calculator")}
    # core set is always present regardless of similarity
    assert {"done_tool", "app_tool", "shell_tool"} <= chosen


def test_select_returns_subset_not_all() -> None:
    tools = _tools()
    sel = ToolSelector(tools, embedder=StubEmbedder(dim=32), top_k=2)
    chosen = sel.select("type some text")
    assert len(chosen) < len(tools)  # it actually filters


def test_select_is_capped_by_k_plus_core() -> None:
    tools = _tools()
    sel = ToolSelector(tools, embedder=StubEmbedder(dim=32), top_k=2)
    chosen = sel.select("anything")
    # at most top_k similarity picks + 3 core (deduped)
    assert len(chosen) <= 2 + 3


def test_empty_task_returns_core_only() -> None:
    sel = ToolSelector(_tools(), embedder=StubEmbedder(dim=32), top_k=2)
    chosen = {t.name for t in sel.select("")}
    assert {"done_tool", "app_tool", "shell_tool"} <= chosen
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agent/test_toolrag.py -q -p no:unraisableexception`
Expected: FAIL — `ModuleNotFoundError: No module named 'yuki.agent.toolrag'`

- [ ] **Step 3: Implement `ToolSelector`**

```python
# yuki/agent/toolrag.py
"""Tool RAG: select the few task-relevant tools to show the model.

Showing all 16 tools every step overwhelms small models. We embed each tool's
description once, then per task return the top-K by cosine similarity plus an
always-include core set so essentials are never filtered out. Degrades to "all
tools" if embedding fails — it can never block a task.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yuki.memory.embeddings import Embedder
    from yuki.tools import Tool

log = logging.getLogger("yuki")

# Essentials that must always be available regardless of similarity.
_CORE = ("done_tool", "app_tool", "shell_tool")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class ToolSelector:
    def __init__(
        self,
        tools: list["Tool"],
        embedder: "Embedder",
        top_k: int = 5,
    ) -> None:
        self._tools = tools
        self._by_name = {t.name: t for t in tools}
        self._embedder = embedder
        self._top_k = top_k
        self._vectors: dict[str, list[float]] | None = None

    def _ensure_index(self) -> bool:
        """Embed tool descriptions once. Returns False if embedding is unavailable."""
        if self._vectors is not None:
            return True
        try:
            texts = [f"{t.name}. {t.description or ''}" for t in self._tools]
            vecs = self._embedder.embed_batch(texts)
            self._vectors = {t.name: v for t, v in zip(self._tools, vecs)}
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("ToolRAG indexing failed (%s); using all tools", type(e).__name__)
            self._vectors = None
            return False

    def select(self, task: str) -> list["Tool"]:
        if not self._ensure_index() or not task.strip():
            chosen = self._core_only() if not task.strip() else None
            if chosen is not None:
                return chosen
            return list(self._tools)  # embedding unavailable → don't block
        try:
            q = self._embedder.embed_one(task)
        except Exception as e:  # noqa: BLE001
            log.warning("ToolRAG query embed failed (%s); using all tools", type(e).__name__)
            return list(self._tools)

        ranked = sorted(
            self._tools,
            key=lambda t: _cosine(q, self._vectors[t.name]),  # type: ignore[index]
            reverse=True,
        )
        names = {t.name for t in ranked[: self._top_k]}
        names.update(n for n in _CORE if n in self._by_name)
        # Preserve original tool order for determinism.
        return [t for t in self._tools if t.name in names]

    def _core_only(self) -> list["Tool"]:
        return [self._by_name[n] for n in _CORE if n in self._by_name]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/agent/test_toolrag.py -q -p no:unraisableexception`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/agent/toolrag.py tests/agent/test_toolrag.py
git commit -m "feat(agent): Tool RAG selector (top-K similarity + always-include core)"
```

---

### Task 7: AX-tree `lean` verbosity mode

**Files:**
- Modify: `yuki/agent/tree/views.py` (`interactive_elements_to_string`)
- Test: `tests/agent/test_ax_pruning.py`

Background: today `interactive_elements_to_string()` dumps every node with full `json.dumps(metadata)`. Add `verbosity: Literal["full","lean"]` (default `"full"` — byte-identical to today). `lean` caps node count at `max_nodes` (default 25), trims metadata to `{value, placeholder}`, and preserves the `<focused_input>` block. Read the current method (lines ~20-60) before editing.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_ax_pruning.py
"""interactive_elements_to_string lean mode caps nodes + trims metadata."""
from __future__ import annotations

from yuki.agent.tree.views import TreeState, TreeElementNode, Center, BoundingBox


def _bbox(idx: int) -> BoundingBox:
    return BoundingBox(left=idx, top=idx, right=idx + 10, bottom=idx + 10,
                       width=10, height=10)


def _node(idx: int, focused: bool = False) -> TreeElementNode:
    # NOTE: TreeElementNode requires bounding_box (first field) + center.
    return TreeElementNode(
        bounding_box=_bbox(idx),
        center=Center(x=idx, y=idx),
        name=f"node{idx}",
        control_type="AXButton",
        window_name="Win",
        canonical="submit_button",
        is_focused=focused,
        metadata={"value": "v", "placeholder": "p", "noise": "x" * 50},
    )


def test_full_mode_unchanged_includes_all_nodes() -> None:
    nodes = [_node(i) for i in range(40)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="full")
    # full mode keeps every node row
    assert out.count("AXButton") == 40


def test_lean_mode_caps_nodes() -> None:
    nodes = [_node(i) for i in range(40)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="lean", max_nodes=25)
    assert out.count("AXButton") <= 25


def test_lean_mode_trims_noise_metadata() -> None:
    nodes = [_node(0)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="lean")
    assert "noise" not in out         # trimmed
    assert "v" in out                 # value kept


def test_lean_mode_keeps_focused_block() -> None:
    nodes = [_node(0, focused=True)]
    ts = TreeState(interactive_nodes=nodes, status=True)
    out = ts.interactive_elements_to_string(verbosity="lean")
    assert "<focused_input>" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agent/test_ax_pruning.py -q -p no:unraisableexception`
Expected: FAIL — `TypeError: interactive_elements_to_string() got an unexpected keyword argument 'verbosity'`
(If `TreeElementNode`/`Center` constructor args differ from the test, FIRST read `yuki/agent/tree/views.py` and adjust the test's node construction to match the real dataclass — then proceed. The behavior asserted stays the same.)

- [ ] **Step 3: Implement lean mode**

Replace the body of `interactive_elements_to_string` in `yuki/agent/tree/views.py` with a `verbosity`-aware version. Keep the `full` path identical to the current implementation:

```python
    def interactive_elements_to_string(
        self,
        verbosity: str = "full",
        max_nodes: int = 25,
    ) -> str:
        parts = []
        if not self.status:
            parts.append(WARNING_MESSAGE)
            return "\n".join(parts)
        if not self.interactive_nodes and self.status:
            parts.append(EMPTY_MESSAGE)
            return "\n".join(parts)

        focused = next(
            (n for n in self.interactive_nodes
             if n.is_focused and n.canonical in {
                 "primary_input", "url_bar", "search_field", "text_input"
             }),
            None,
        )
        if focused is not None:
            value = focused.metadata.get("value") or ""
            placeholder = focused.metadata.get("placeholder") or ""
            parts.append(
                "<focused_input>\n"
                f"canonical={focused.canonical} window={focused.window_name} "
                f"role={focused.control_type} name={focused.name!r} "
                f"coords={focused.center.to_string()} "
                f"value={value!r} placeholder={placeholder!r}\n"
                "</focused_input>"
            )

        lean = verbosity == "lean"
        nodes = self.interactive_nodes
        if lean:
            # Rank: focused first, then by canonical priority, drop the rest past cap.
            priority = {
                "url_bar": 0, "search_field": 1, "primary_input": 2,
                "text_input": 3, "submit_button": 4,
            }
            nodes = sorted(
                self.interactive_nodes,
                key=lambda n: (not n.is_focused, priority.get(n.canonical or "", 9)),
            )[:max_nodes]

        header = "# id|window|control_type|canonical|name|coords|focused|metadata"
        rows = [header]
        for idx, node in enumerate(nodes):
            canonical = node.canonical or "-"
            focused_mark = "YES" if node.is_focused else "-"
            if lean:
                meta = {k: node.metadata[k] for k in ("value", "placeholder")
                        if k in node.metadata}
            else:
                meta = node.metadata
            row = (
                f"{idx}|{node.window_name}|{node.control_type}|{canonical}|"
                f"{node.name}|{node.center.to_string()}|{focused_mark}|"
                f"{json.dumps(meta)}"
            )
            rows.append(row)
        parts.append("\n".join(rows))
        return "\n".join(parts)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/agent/test_ax_pruning.py -q -p no:unraisableexception`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/agent/tree/views.py tests/agent/test_ax_pruning.py
git commit -m "feat(agent): lean AX-tree verbosity (cap nodes + trim metadata)"
```

---

### Task 8: Wire Tool RAG into the Agent + verbosity into the state prompt

**Files:**
- Modify: `yuki/agent/service.py` (`tools` property + `__init__`)
- Modify: `yuki/agent/context/service.py` (`state` / `_build_state_prompt` — pass verbosity)
- Test: `tests/agent/test_toolrag_integration.py`

Background: the agent currently does `tools = registry.get_tools()` (returns all). We add an optional `ToolSelector` that, when present, filters by the current task. The selector is built lazily from a model-tier signal: small/local models get it, cloud models keep all tools (driven by `agent_mode_for`-style logic). Verbosity for the AX tree is threaded the same way: `lean` for local, `full` for cloud.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_toolrag_integration.py
"""Agent.tools filters via ToolSelector when one is set."""
from __future__ import annotations

from yuki import Agent
from yuki.agent.toolrag import ToolSelector
from yuki.memory.embeddings import StubEmbedder
from yuki.providers.stub.llm import ChatStub


def test_tools_unfiltered_by_default() -> None:
    agent = Agent(llm=ChatStub(), log_to_console=False, auto_minimize=False)
    # No selector → all builtin tools.
    assert len(agent.tools) >= 14


def test_tools_filtered_when_selector_set() -> None:
    agent = Agent(llm=ChatStub(), log_to_console=False, auto_minimize=False)
    agent.tool_selector = ToolSelector(
        agent.registry.get_tools(), embedder=StubEmbedder(dim=32), top_k=2
    )
    agent.state.task = "open calculator"
    filtered = agent.tools
    assert len(filtered) < len(agent.registry.get_tools())
    assert any(t.name == "done_tool" for t in filtered)  # core always present
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agent/test_toolrag_integration.py -q -p no:unraisableexception`
Expected: FAIL — `AttributeError: 'Agent' object has no attribute 'tool_selector'` (the filtered test fails)

- [ ] **Step 3: Add the selector hook**

In `yuki/agent/service.py` `__init__`, after `self._loop_guard = LoopGuard()`, add:

```python
        # Optional Tool RAG selector. When set, `tools` returns a task-relevant
        # subset instead of all tools (helps small models). Built by the caller
        # (e.g. the control endpoint) for local models; None = all tools.
        self.tool_selector = None
```

Replace the `tools` property:

```python
    @property
    def tools(self):
        all_tools = self.registry.get_tools()
        selector = getattr(self, "tool_selector", None)
        task = getattr(self.state, "task", "") or ""
        if selector is None or not task:
            return all_tools
        return selector.select(task)
```

In `yuki/agent/context/service.py`, thread verbosity. Change `state(...)` to accept `verbosity` and pass it down, and have `_build_state_prompt` call `interactive_elements_to_string(verbosity=verbosity)`:

```python
    def state(
        self,
        query: str,
        step: int,
        max_steps: int,
        desktop: Desktop,
        nudge: str = "",
        verbosity: str = "full",
    ) -> HumanMessage | ImageMessage:
        desktop_state = desktop.get_state()
        content = self._build_state_prompt(
            query=query, step=step, max_steps=max_steps,
            desktop=desktop, nudge=nudge, verbosity=verbosity,
        )
        if desktop.use_vision and desktop_state.screenshot:
            return ImageMessage(images=[desktop_state.screenshot], content=content)
        return HumanMessage(content=content)
```

And in `_build_state_prompt`, add the `verbosity: str = "full"` param and change the `interactive_elements` line to:

```python
            "interactive_elements": (
                desktop_state.tree_state.interactive_elements_to_string(verbosity=verbosity)
                if desktop.use_accessibility and desktop_state and desktop_state.tree_state
                else "No accessibility data is available"
            ),
```

Then in `service.py`, both loop variants call `self.context.state(...)` — add `verbosity=self._ax_verbosity()` to those calls, and add the helper + an `__init__` field:

```python
        # AX-tree verbosity: "lean" for small/local models, "full" otherwise.
        self.ax_verbosity = "full"
```

```python
    def _ax_verbosity(self) -> str:
        return getattr(self, "ax_verbosity", "full")
```

(Find each `self.context.state(` call in `loop`/`_arun` and append `verbosity=self._ax_verbosity()`.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/agent/test_toolrag_integration.py -q -p no:unraisableexception`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the agent regression suite**

Run: `uv run pytest tests/agent/ -q -p no:unraisableexception`
Expected: PASS (all agent tests, incl. the existing loop tests)

- [ ] **Step 6: Commit**

```bash
git add yuki/agent/service.py yuki/agent/context/service.py tests/agent/test_toolrag_integration.py
git commit -m "feat(agent): wire Tool RAG selector + AX verbosity into the loop"
```

---

### Task 9: Activate Tool RAG + lean AX for local models in the control endpoint

**Files:**
- Modify: `yuki/backend/routers/chat.py` (control path — construct Agent with selector + lean verbosity for Ollama)
- Test: `tests/backend/test_control_smallmodel_wiring.py`

Background: Task 8 added the *hooks*; this turns them ON for local models. In `_stream_control`, after building the Agent, if the LLM is Ollama, attach a `ToolSelector` (using `OllamaEmbedder`, falling back to all-tools if unavailable) and set `ax_verbosity = "lean"`. Cloud models are untouched. Read the current Agent construction (around line 210, where `agent_mode_for` is used).

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_control_smallmodel_wiring.py
"""_configure_agent_for_model attaches Tool RAG + lean AX for Ollama only."""
from __future__ import annotations

from yuki import Agent
from yuki.backend.routers.chat import _configure_agent_for_model
from yuki.providers.stub.llm import ChatStub


class _Ollamaish(ChatStub):
    @property
    def provider(self) -> str:
        return "ollama"


def test_ollama_gets_selector_and_lean() -> None:
    agent = Agent(llm=_Ollamaish(), log_to_console=False, auto_minimize=False)
    _configure_agent_for_model(agent, _Ollamaish())
    assert agent.tool_selector is not None
    assert agent.ax_verbosity == "lean"


def test_cloud_model_untouched() -> None:
    agent = Agent(llm=ChatStub(), log_to_console=False, auto_minimize=False)
    _configure_agent_for_model(agent, ChatStub())  # provider == "stub"
    assert agent.tool_selector is None
    assert agent.ax_verbosity == "full"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/backend/test_control_smallmodel_wiring.py -q -p no:unraisableexception`
Expected: FAIL — `ImportError: cannot import name '_configure_agent_for_model'`

- [ ] **Step 3: Implement the configurator + call it**

Add to `yuki/backend/routers/chat.py` (module level):

```python
def _configure_agent_for_model(agent, llm) -> None:
    """Turn on Tool RAG + lean AX-tree for small/local (Ollama) models.
    Cloud models keep full tools + full AX context (they handle it fine)."""
    provider = getattr(llm, "provider", "") or ""
    if provider != "ollama":
        return
    try:
        from yuki.agent.toolrag import ToolSelector
        from yuki.memory.embeddings import OllamaEmbedder

        agent.tool_selector = ToolSelector(
            agent.registry.get_tools(), embedder=OllamaEmbedder()
        )
    except Exception:
        agent.tool_selector = None  # degrade to all-tools; never block
    agent.ax_verbosity = "lean"
```

In `_stream_control`, right after the Agent is constructed (the `agent = Agent(llm=llm, mode=agent_mode_for(llm), ...)` line), add:

```python
    _configure_agent_for_model(agent, llm)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/backend/test_control_smallmodel_wiring.py -q -p no:unraisableexception`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/backend/routers/chat.py tests/backend/test_control_smallmodel_wiring.py
git commit -m "feat(backend): enable Tool RAG + lean AX for Ollama control tasks"
```

---

## DECISION GATE

### Task 10: Measure small models with Phase A1 active (no new code)

**This task is a measurement, not an implementation.** Its output decides whether Tasks 11-14 (planner/executor) are built.

- [ ] **Step 1: Pull the local embed model** (one-time):

Run: `ollama pull nomic-embed-text`
Expected: download completes; `ollama list` shows `nomic-embed-text`.

- [ ] **Step 2: Run the eval harness on the small models**

Run:
```bash
uv run python -m yuki.eval.run --model llama3.2:1b --mode flash
uv run python -m yuki.eval.run --model qwen2.5:3b --mode flash
```
Record `graph_score` and `toolset_score` for each.

- [ ] **Step 3: Run it on a cloud model as the high-water mark + regression check**

Run: `uv run python -m yuki.eval.run` (uses configured default, e.g. Gemini)
Record its scores. (If no cloud key is configured, skip — the small-model numbers still decide the gate.)

- [ ] **Step 4: Record the gate decision in this plan file**

Append a short "Gate Result" note under this task: the measured scores and the decision.

**GATE CRITERION:**
- **PASS** if small models reach **graph_score ≥ 0.6 on non-reactive cases** (i.e. they reliably pick the right first tool for simple tasks — the failure we set out to fix). → **Skip Tasks 11-14**, jump to Phase B (Task 15).
- **FAIL** otherwise → proceed to Task 11 (build the planner/executor), then re-run this measurement after Task 14.

### ⮕ GATE RESULT (measured 2026-06-02, Phase A1 active: Tool RAG + lean AX)

**IMPORTANT — first measurement was invalid (harness bug).** The initial run scored every model 0.00 because the eval runner passed all 16 `BUILTIN_TOOLS` to the model instead of applying Tool RAG (the feature under test). Even a capable 7B is overwhelmed by 16 raw tool schemas and emits no/wrong tool call. Fixed in commit `60f1256` (runner now applies the `ToolSelector` the agent actually uses). The corrected measurement:

| Model | mode | graph_score | toolset_score | Verdict |
|---|---|---|---|---|
| **qwen2.5:7b** | flash, Tool RAG on | **0.90** | 0.90 | ✅ **PASS** — clears the 0.60 bar. Correct tool on 9/10 (only miss: "capital of France" → shell_tool instead of direct done_tool answer). |
| qwen2.5:3b | flash, Tool RAG on | 0.40 | 0.40 | Below bar — usable for some tasks, unreliable. Fine-tuning (Phase B) candidate. |
| llama3.2:1b | flash, Tool RAG on | 0.10 | 0.10 | Below bar — too small off-the-shelf. Fine-tuning (Phase B) candidate. |

Proof Tool RAG is the lever (qwen2.5:7b, "open calculator"): with all 16 tools → empty TEXT (no tool call); with only {app_tool, done_tool} → perfect `app_tool{mode:launch, name:Calculator}`.

**DECISION: GATE PASSED for qwen2.5:7b.** A fully-local model selects tools reliably (0.90) with Phase A1's Tool RAG + lean AX — **no cloud API, no fine-tuning needed** for the 7B. This satisfies the local-first product requirement today. 

**Phase A2 (planner/executor) is therefore NOT required** to ship a working local default — its purpose (simplify per-step decisions) is already achieved for the 7B by Tool RAG. A2 / Phase B fine-tuning remain optional future work to make the SMALLER (1-3B, faster) models clear the bar too. Recommended next step: make qwen2.5:7b the default/recommended local model + add per-task-type provider routing, rather than building A2.

- [ ] **Step 5: Commit the recorded result**

```bash
git add docs/superpowers/plans/2026-06-02-Q-small-model-agent-optimization.md
git commit -m "docs(plan): record Phase A1 decision-gate eval results"
```

---

## PHASE A2 — Planner/executor (CONDITIONAL: build only if Task 10 gate FAILED)

> If the gate PASSED, skip to Phase B (Task 15). These tasks are fully specified so that, if needed, execution proceeds with zero redesign.

### Task 11: Plan schema + Planner

**Files:**
- Create: `yuki/agent/planner.py`
- Test: `tests/agent/test_planner.py`

Background: the Planner makes ONE LLM call with the task + the RAG-selected tool *menu* (names + one-line descriptions, NO screen state) and returns a coordinate-free ordered `Plan`. We validate it (known tool names, ≥1 step, action tasks end with `done_tool`). The LLM is injected (`ChatStub` in tests). The planner asks for JSON and parses it; on parse failure it returns a single-step "fallback" plan that defers to the normal loop.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_planner.py
"""Planner turns a task into a validated coordinate-free Plan."""
from __future__ import annotations

import json

from yuki.agent.planner import Plan, PlanStep, Planner
from yuki.providers.events import LLMEvent, LLMEventType
from yuki.providers.stub.llm import ChatStub


def _stub_text(payload: dict) -> ChatStub:
    ev = LLMEvent(type=LLMEventType.TEXT, content=json.dumps(payload))
    return ChatStub(events=[ev])


def _tool_names() -> list[str]:
    return ["app_tool", "type_tool", "done_tool"]


def test_parses_valid_plan() -> None:
    payload = {"steps": [
        {"tool": "app_tool", "intent": "open Calculator"},
        {"tool": "type_tool", "intent": "type 5+5"},
        {"tool": "done_tool", "intent": "report done"},
    ]}
    planner = Planner(llm=_stub_text(payload))
    plan = planner.plan("open calculator and type 5+5", _tool_names())
    assert isinstance(plan, Plan)
    assert [s.tool for s in plan.steps] == ["app_tool", "type_tool", "done_tool"]


def test_unknown_tool_is_dropped() -> None:
    payload = {"steps": [
        {"tool": "teleport_tool", "intent": "nope"},
        {"tool": "app_tool", "intent": "open Calculator"},
        {"tool": "done_tool", "intent": "done"},
    ]}
    planner = Planner(llm=_stub_text(payload))
    plan = planner.plan("open calculator", _tool_names())
    assert all(s.tool in _tool_names() for s in plan.steps)


def test_malformed_json_yields_fallback_plan() -> None:
    ev = LLMEvent(type=LLMEventType.TEXT, content="not json at all")
    planner = Planner(llm=ChatStub(events=[ev]))
    plan = planner.plan("do something", _tool_names())
    assert plan.is_fallback is True
    assert len(plan.steps) >= 1  # never empty
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agent/test_planner.py -q -p no:unraisableexception`
Expected: FAIL — `ModuleNotFoundError: No module named 'yuki.agent.planner'`

- [ ] **Step 3: Implement the Planner**

```python
# yuki/agent/planner.py
"""Planner: task -> coordinate-free step plan (one LLM call, no screen state).

Decouples high-level reasoning from per-step observation. The executor resolves
each step's concrete action against the live (pruned) AX-tree. Plans are sketches,
not contracts — the executor and a bounded re-plan handle reality diverging.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("yuki")


@dataclass(frozen=True)
class PlanStep:
    tool: str
    intent: str


@dataclass(frozen=True)
class Plan:
    steps: list[PlanStep]
    is_fallback: bool = False


_PROMPT = """You are planning a macOS task. Output ONLY JSON of the form:
{{"steps": [{{"tool": "<tool_name>", "intent": "<what this step does>"}}, ...]}}

Rules:
- Use ONLY these tools: {tools}
- Do NOT include coordinates or screen details — those are resolved at execution.
- End an action task with a "done_tool" step. A pure question is a single done_tool step.

Task: {task}
JSON:"""


class Planner:
    def __init__(self, llm) -> None:
        self._llm = llm

    def plan(self, task: str, tool_names: list[str]) -> Plan:
        from yuki.messages import HumanMessage

        prompt = _PROMPT.format(tools=", ".join(tool_names), task=task)
        try:
            event = self._llm.invoke(messages=[HumanMessage(content=prompt)], tools=[])
            text = getattr(event, "content", "") or ""
        except Exception as e:  # noqa: BLE001
            log.warning("planner LLM call failed (%s); fallback", type(e).__name__)
            return self._fallback()

        parsed = self._extract_json(text)
        if parsed is None:
            return self._fallback()

        valid = set(tool_names)
        steps = [
            PlanStep(tool=s["tool"], intent=str(s.get("intent", "")))
            for s in parsed.get("steps", [])
            if isinstance(s, dict) and s.get("tool") in valid
        ]
        if not steps:
            return self._fallback()
        return Plan(steps=steps)

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", text, re.DOTALL)  # tolerate prose around JSON
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _fallback() -> Plan:
        # A single done_tool step lets the executor fall back to the normal loop
        # behavior rather than failing the task outright.
        return Plan(steps=[PlanStep(tool="done_tool", intent="(fallback)")],
                    is_fallback=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/agent/test_planner.py -q -p no:unraisableexception`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/agent/planner.py tests/agent/test_planner.py
git commit -m "feat(agent): Planner — task to coordinate-free step plan"
```

---

### Task 12: Executor loop mode in the Agent (with `single` fallback)

**Files:**
- Modify: `yuki/agent/service.py` (add a planner-driven loop path + `YUKI_AGENT_LOOP` switch)
- Test: `tests/agent/test_executor_loop.py`

Background: add `loop_mode: "single"|"planner"` to the Agent (default `"single"` = today's behavior, fully preserved). In `"planner"` mode, the agent first calls the Planner, then for each plan step runs the existing observe→act machinery but with the step's `intent` injected as the immediate goal and only that step's pruned context. Re-plan on step failure, bounded to `max_replans=2`. Because the per-step observe→act code already exists, this WRAPS it. This test verifies mode selection + that planner mode terminates via the existing done handling.

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_executor_loop.py
"""Agent honors loop_mode and planner mode terminates correctly."""
from __future__ import annotations

import json

from yuki import Agent
from yuki.providers.events import LLMEvent, LLMEventType, ToolCall
from yuki.providers.stub.llm import ChatStub


def test_default_loop_mode_is_single() -> None:
    agent = Agent(llm=ChatStub(), log_to_console=False, auto_minimize=False)
    assert agent.loop_mode == "single"


def test_planner_mode_runs_plan_then_done() -> None:
    # Stub script: 1) planner returns a 1-step done plan (TEXT json),
    #              2) executor emits done_tool (TOOL_CALL).
    plan_ev = LLMEvent(type=LLMEventType.TEXT,
                       content=json.dumps({"steps": [
                           {"tool": "done_tool", "intent": "answer"}]}))
    done_ev = LLMEvent(type=LLMEventType.TOOL_CALL,
                       tool_call=ToolCall(id="d", name="done_tool",
                                          params={"thought": "t", "answer": "hi"}))
    agent = Agent(llm=ChatStub(events=[plan_ev, done_ev]),
                  loop_mode="planner", log_to_console=False, auto_minimize=False)
    result = agent.invoke(task="say hi")
    assert result.is_done is True
    assert result.content == "hi"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/agent/test_executor_loop.py -q -p no:unraisableexception`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'loop_mode'`

- [ ] **Step 3: Implement loop_mode + planner path**

In `service.py` `__init__` signature, add `loop_mode: Literal["single", "planner"] = "single"`, and store it (respecting an env override):

```python
        import os
        self.loop_mode = os.environ.get("YUKI_AGENT_LOOP", loop_mode)
```

Add a planner-driven entry that reuses the existing per-step machinery. The cleanest seam: a `_plan_for_task()` helper that produces an ordered list of step-intents, and have the existing loop, when `loop_mode == "planner"`, inject the current step's intent into the state query. Concretely, add:

```python
    def _maybe_build_plan(self) -> list[str]:
        """Return a list of step-intent strings for planner mode, else []."""
        if self.loop_mode != "planner":
            return []
        from yuki.agent.planner import Planner
        names = [t.name for t in self.registry.get_tools()]
        plan = Planner(self._planner_llm()).plan(self.state.task, names)
        if plan.is_fallback:
            self.loop_mode = "single"  # degrade gracefully
            return []
        return [s.intent for s in plan.steps]

    def _planner_llm(self):
        return self.llm
```

Then, in BOTH loop variants (`loop`/`_arun`), near the top after the system+task messages are appended, compute the plan once and feed each step's intent as a guidance line appended to the state query. Minimal integration: build `self._plan_intents = self._maybe_build_plan()` and, when non-empty, prepend `f"[Current plan step: {self._plan_intents[min(step, len-1)]}]"` to the `query` passed to `self.context.state(...)`. Re-plan: if a step fails and `self._replans < 2`, rebuild the plan from the remaining task and increment `self._replans`.

(The implementer should keep `single` mode byte-for-byte identical — the planner path is purely additive, gated on `loop_mode == "planner"`. The existing done/failure handling from `service.py` is reused unchanged, which is what makes the stub test terminate.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/agent/test_executor_loop.py -q -p no:unraisableexception`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full agent suite (no regression in single mode)**

Run: `uv run pytest tests/agent/ -q -p no:unraisableexception`
Expected: PASS (all, including the original single-mode loop tests)

- [ ] **Step 6: Commit**

```bash
git add yuki/agent/service.py tests/agent/test_executor_loop.py
git commit -m "feat(agent): planner-driven loop mode with single-mode fallback"
```

---

### Task 13: Teach the eval runner to grade full plans (post-planner)

**Files:**
- Modify: `yuki/eval/run.py` (add full-plan extraction for planner-capable models)
- Test: `tests/eval/test_run_full_plan.py`

Background: pre-A2 the runner graded the first tool call. Now add `run_case_planner()` that uses the `Planner` to get a full `Plan` and grades it against the whole `expected_plan` (mapping plan steps → `{tool, args}` shape; intents don't carry args, so this grades the **tool sequence** via `toolset_score` + ordered tool match). This is what fine-tuning (Phase B) optimizes.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/test_run_full_plan.py
"""run_case_planner grades a full planned tool sequence."""
from __future__ import annotations

import json

from yuki.eval.cases import EvalCase, ExpectedStep
from yuki.eval.run import run_case_planner
from yuki.providers.events import LLMEvent, LLMEventType
from yuki.providers.stub.llm import ChatStub


def test_full_plan_graph_match() -> None:
    case = EvalCase(
        task="open calculator and type 5+5",
        expected_plan=[ExpectedStep("app_tool"), ExpectedStep("type_tool"),
                       ExpectedStep("done_tool")],
    )
    plan_json = {"steps": [
        {"tool": "app_tool", "intent": "open"},
        {"tool": "type_tool", "intent": "type"},
        {"tool": "done_tool", "intent": "done"},
    ]}
    stub = ChatStub(events=[LLMEvent(type=LLMEventType.TEXT, content=json.dumps(plan_json))])
    r = run_case_planner(case, stub)
    assert r["graph_score"] == 1.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/eval/test_run_full_plan.py -q -p no:unraisableexception`
Expected: FAIL — `ImportError: cannot import name 'run_case_planner'`

- [ ] **Step 3: Implement full-plan grading**

Add to `yuki/eval/run.py`:

```python
def run_case_planner(case: EvalCase, llm: Any) -> dict[str, Any]:
    """Grade a full planned tool SEQUENCE (used post-A2 / for fine-tuning).

    Plan steps carry tool + intent (no args), so we grade the ordered tool
    sequence. Args matchers are ignored here — the executor resolves args at
    run time; plan-correctness is about choosing the right tools in order.
    """
    from yuki.agent.planner import Planner
    from yuki.agent.tools import BUILTIN_TOOLS

    names = [t.name for t in BUILTIN_TOOLS]
    plan = Planner(llm).plan(case.task, names)
    emitted = [{"tool": s.tool, "args": {}} for s in plan.steps]
    # Reuse score_plan but with args matchers stripped (sequence-only grading).
    seq_case = EvalCase(
        task=case.task,
        expected_plan=[ExpectedStep(s.tool) for s in case.expected_plan],
        reactive=case.reactive,
    )
    scores = score_plan(seq_case, emitted)
    return {"task": case.task, "is_fallback": plan.is_fallback, **scores}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/eval/test_run_full_plan.py -q -p no:unraisableexception`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add yuki/eval/run.py tests/eval/test_run_full_plan.py
git commit -m "feat(eval): full-plan (tool-sequence) grading for planner mode"
```

---

### Task 14: Re-run the gate measurement with planner mode

**Files:** none (measurement). Mirrors Task 10 but with `YUKI_AGENT_LOOP=planner`.

- [ ] **Step 1: Measure small models in planner mode**

Run:
```bash
YUKI_AGENT_LOOP=planner uv run python -m yuki.eval.run --model llama3.2:1b --mode flash
YUKI_AGENT_LOOP=planner uv run python -m yuki.eval.run --model qwen2.5:3b --mode flash
```
(The runner's `run_suite` should call `run_case_planner` when `YUKI_AGENT_LOOP=planner` — add that conditional in `main()`.)

- [ ] **Step 2: Compare to the Task-10 baseline**

Record whether planner mode improved `graph_score` for small models, and confirm cloud models didn't regress (`uv run python -m yuki.eval.run` with planner env).

- [ ] **Step 3: Record the result + decide whether to proceed to Phase B**

Append a "Phase A2 Result" note to this plan: scores before/after, and the decision (proceed to fine-tuning if Phase A got small models "close but not enough," or ship Phase A as the win if it cleared the bar).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-06-02-Q-small-model-agent-optimization.md
git commit -m "docs(plan): record Phase A2 planner-mode eval results"
```

---

## PHASE B — Fine-tuning pipeline (offline ML; depends on A's format being stable)

> Phase B lives in `training/` (outside the shipped `yuki/` package). It is NOT unit-TDD'd like Phase A — its acceptance test IS the eval harness (graph_score ≥ baseline). Tasks here are script-granularity with validation gates.

### Task 15: Grow the eval suite to ~30 cases

**Files:**
- Modify: `yuki/eval/cases.py` (expand `CASES` to ~30, more AX fixtures)
- Test: existing `tests/eval/test_cases.py` (bump the `>= 10` assertion to `>= 28`)

- [ ] **Step 1: Update the count assertion**

In `tests/eval/test_cases.py`, change `assert len(CASES) >= 10` to `assert len(CASES) >= 28`. Run it; it FAILS.

Run: `uv run pytest tests/eval/test_cases.py::test_cases_nonempty_and_typed -q -p no:unraisableexception`
Expected: FAIL (only ~10 cases).

- [ ] **Step 2: Add ~20 more cases**

Extend `CASES` in `yuki/eval/cases.py` with additional realistic tasks covering: more apps (Messages, Mail, Spotify, Chrome, WhatsApp), multi-step flows (open app → search → act), shell/osascript tasks, conversational/Q&A, and 3-4 more reactive cases with new fixtures under `yuki/eval/fixtures/`. Each follows the exact `EvalCase(...)` shape from Task 1. (The implementer writes concrete cases mirroring Task 1's style — e.g. `EvalCase(task="play music on Spotify", expected_plan=[ExpectedStep("app_tool", {"name": r"spotify"}), ExpectedStep("done_tool")])`.)

- [ ] **Step 3: Run to verify it passes**

Run: `uv run pytest tests/eval/test_cases.py -q -p no:unraisableexception`
Expected: PASS (all 3 case tests, now with ≥28 cases).

- [ ] **Step 4: Commit**

```bash
git add yuki/eval/cases.py yuki/eval/fixtures/ tests/eval/test_cases.py
git commit -m "feat(eval): expand suite to ~30 cases for fine-tuning validation"
```

---

### Task 16: Dataset generation script

**Files:**
- Create: `training/README.md`, `training/gen_dataset.py`
- Test: `tests/training/test_gen_dataset_validation.py` (validation logic only — not the API calls)

Background: `gen_dataset.py` calls a frontier model (Claude/GPT-4/Gemini via the existing provider factory) to synthesize `(task, plan)` pairs over Yuki's 16 real tools, then VALIDATES each pair (known tools, valid step ordering, ends with done_tool) before writing JSONL. The validation function is pure and IS unit-tested; the API-calling part is a script run manually (it costs money). Output: `training/data/{train,val,test}.jsonl`.

- [ ] **Step 1: Write the failing test (validation only)**

```python
# tests/training/test_gen_dataset_validation.py
"""Dataset pair validation rejects malformed plans."""
from __future__ import annotations

from training.gen_dataset import validate_pair


def _tools() -> set[str]:
    return {"app_tool", "type_tool", "done_tool"}


def test_valid_pair_accepted() -> None:
    pair = {"task": "open calc", "steps": [
        {"tool": "app_tool", "intent": "open"},
        {"tool": "done_tool", "intent": "done"}]}
    assert validate_pair(pair, _tools()) is True


def test_unknown_tool_rejected() -> None:
    pair = {"task": "x", "steps": [{"tool": "warp_tool", "intent": "no"}]}
    assert validate_pair(pair, _tools()) is False


def test_missing_done_rejected() -> None:
    pair = {"task": "open calc", "steps": [{"tool": "app_tool", "intent": "open"}]}
    assert validate_pair(pair, _tools()) is False


def test_empty_steps_rejected() -> None:
    assert validate_pair({"task": "x", "steps": []}, _tools()) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/training/test_gen_dataset_validation.py -q -p no:unraisableexception`
Expected: FAIL — `ModuleNotFoundError: No module named 'training'` (add `training/__init__.py` and `tests/training/__init__.py`).

- [ ] **Step 3: Implement `gen_dataset.py` (+ package markers)**

Create `training/__init__.py`, `tests/training/__init__.py` (empty), and `training/gen_dataset.py`:

```python
# training/gen_dataset.py
"""Synthesize a function-calling dataset for Yuki's tools using a frontier model.

Run manually (costs API credits):
    uv run python -m training.gen_dataset --n 12000 --out training/data

Each emitted line: {"task": str, "steps": [{"tool","intent"}, ...]}.
validate_pair() is pure and unit-tested; the generation loop calls a frontier
LLM and keeps only valid pairs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate_pair(pair: dict, valid_tools: set[str]) -> bool:
    steps = pair.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    for s in steps:
        if not isinstance(s, dict) or s.get("tool") not in valid_tools:
            return False
    if steps[-1].get("tool") != "done_tool":
        return False
    return bool(str(pair.get("task", "")).strip())


def _generate(n: int, valid_tools: set[str]) -> list[dict]:  # pragma: no cover
    """Call a frontier model to synthesize n validated pairs. Manual-run only."""
    from yuki.messages import HumanMessage
    from yuki.providers.factory import make_llm

    llm = make_llm()  # use a strong configured model (Claude/GPT-4/Gemini)
    out: list[dict] = []
    prompt_tmpl = (
        "Generate ONE realistic macOS task and its correct tool plan as JSON: "
        '{{"task": "...", "steps": [{{"tool": "...", "intent": "..."}}]}}. '
        "Valid tools: " + ", ".join(sorted(valid_tools)) + ". "
        "End action tasks with done_tool. Vary apps and difficulty. Output ONLY JSON."
    )
    while len(out) < n:
        ev = llm.invoke(messages=[HumanMessage(content=prompt_tmpl)], tools=[])
        try:
            pair = json.loads(getattr(ev, "content", "") or "")
        except json.JSONDecodeError:
            continue
        if validate_pair(pair, valid_tools):
            out.append(pair)
    return out


def main() -> None:  # pragma: no cover
    from yuki.agent.tools import BUILTIN_TOOLS

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12000)
    ap.add_argument("--out", default="training/data")
    args = ap.parse_args()

    valid = {t.name for t in BUILTIN_TOOLS}
    pairs = _generate(args.n, valid)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n = len(pairs)
    splits = {"train": pairs[: int(n * 0.9)],
              "val": pairs[int(n * 0.9): int(n * 0.95)],
              "test": pairs[int(n * 0.95):]}
    for name, rows in splits.items():
        (out / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    print(f"wrote {n} pairs to {out}")


if __name__ == "__main__":
    main()
```

Write `training/README.md` documenting: cost (~$500), how to run, where data lands, and that it must be regenerated if Yuki's tool/plan format changes.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/training/test_gen_dataset_validation.py -q -p no:unraisableexception`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add training/__init__.py training/gen_dataset.py training/README.md tests/training/
git commit -m "feat(training): dataset generation script + pair validation"
```

---

### Task 17: Generate the dataset (manual run, gated)

**Files:** produces `training/data/{train,val,test}.jsonl` (gitignored — large).

- [ ] **Step 1: Gitignore the data dir**

Add `training/data/` to `.gitignore`. Commit that line:
```bash
git add .gitignore && git commit -m "chore: gitignore training/data"
```

- [ ] **Step 2: Run generation** (manual, costs credits — confirm with the user first):

Run: `uv run python -m training.gen_dataset --n 12000 --out training/data`
Expected: `wrote ~12000 pairs to training/data`, three JSONL files present.

- [ ] **Step 3: Sanity-check the data**

Run a quick check that every line validates and tool distribution is sane (a few lines of `python -c` counting tools per file). Record the counts in `training/README.md`.

- [ ] **Step 4: Commit the README update** (data itself stays untracked):
```bash
git add training/README.md && git commit -m "docs(training): record generated dataset stats"
```

---

### Task 18: LoRA fine-tune llama3.2:1b

**Files:**
- Create: `training/train_lora.py`, `training/Modelfile`

Background: fine-tune llama3.2:1b on the JSONL via LoRA (TinyAgent hyperparams: LoRA, ~3 epochs, lr 7e-5, include negative samples — irrelevant tools in the prompt — to teach selection). Output a LoRA adapter, merge to GGUF, and write an Ollama `Modelfile` so it loads as `yuki-1b`. This is a manual GPU run; the script is provided complete but executed by the user.

- [ ] **Step 1: Write `training/train_lora.py`**

Provide a complete LoRA training script using HuggingFace `peft` + `transformers` (or `mlx-lm` for Apple Silicon — note both in comments). It: loads `train.jsonl`, formats each pair as a chat-style `(system with tools incl. negatives, user task, assistant JSON plan)`, runs LoRA, saves the adapter to `training/out/`. Include the exact hyperparameters as named constants (`EPOCHS=3`, `LR=7e-5`, `LORA_R=16`, `LORA_ALPHA=32`). (Full script body written by the implementer following this spec — it's standard `peft` boilerplate; the key Yuki-specific part is the prompt formatting that mirrors `Planner._PROMPT` from Task 11 so train/inference formats match.)

- [ ] **Step 2: Write `training/Modelfile`**

```
FROM ./out/yuki-1b-merged.gguf
PARAMETER temperature 0.2
SYSTEM """You are Yuki's local control planner. Given a task and a tool list, output ONLY a JSON plan of tool steps."""
```

- [ ] **Step 3: Run training** (manual, GPU/Apple-Silicon — confirm with user):

Run: `uv run python -m training.train_lora --data training/data --out training/out`
Expected: adapter + merged GGUF in `training/out/`.

- [ ] **Step 4: Register with Ollama**

Run: `ollama create yuki-1b -f training/Modelfile`
Expected: `ollama list` shows `yuki-1b`.

- [ ] **Step 5: Commit the scripts** (not the weights):

Add `training/out/` to `.gitignore`.
```bash
git add training/train_lora.py training/Modelfile .gitignore
git commit -m "feat(training): LoRA fine-tune script + Ollama Modelfile for yuki-1b"
```

---

### Task 19: Validate the fine-tuned model against the eval harness

**Files:** none (measurement + acceptance gate).

- [ ] **Step 1: Run the full eval suite on yuki-1b**

Run:
```bash
YUKI_AGENT_LOOP=planner uv run python -m yuki.eval.run --model yuki-1b --mode flash
```
Record `graph_score` and `toolset_score`.

- [ ] **Step 2: Compare against baselines**

Compare yuki-1b vs (a) off-the-shelf llama3.2:1b (Task 10/14 numbers) and (b) a cloud model. **Ship gate:** `yuki-1b graph_score ≥ off-the-shelf baseline` (target: ≥ cloud high-water mark).

- [ ] **Step 3: If it passes — add to the curated download list**

If shipping: add `yuki-1b` to the recommended-models list in `yuki/backend/routers/provider.py` (`_RECOMMENDED_OLLAMA`) so it appears in the Provider tab. Commit:
```bash
git add yuki/backend/routers/provider.py
git commit -m "feat(provider): offer fine-tuned yuki-1b in the model download list"
```

- [ ] **Step 4: Record final results** in `training/README.md` + the plan, and commit.

---

## Final verification (after the chosen phases complete)

- [ ] `uv run pytest tests/ -q -p no:unraisableexception` → green except the 2 known `test_factory.py` keychain failures.
- [ ] `uv run python -m yuki.eval.run` on a cloud model → graph_score unchanged from pre-Phase-A baseline (no regression).
- [ ] Manual QA: a control task ("open calculator") on the best small model actually opens Calculator.
- [ ] If shipping a new build: `./release.sh <version>` + cask update (separate from this plan).

## Phasing recap

- **Tasks 1-9** (Phase A1): always built. Eval harness + Tool RAG + AX-pruning + wiring.
- **Task 10** (gate): measure. PASS → skip to Task 15. FAIL → Tasks 11-14.
- **Tasks 11-14** (Phase A2, conditional): planner/executor + re-measure.
- **Tasks 15-19** (Phase B): fine-tuning, validated by the eval harness.

