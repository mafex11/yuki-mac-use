# Plan M — Agent self-improvement via vault feedback loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the feedback loop between the agent's `/control` runs and the vault. After every task, record what worked and what failed. Daily, distill those records into per-app guidance the agent reads on its next run. In parallel, surface focus + canonical role tags for every interactive AX element so the model can disambiguate elements across all apps without per-app code.

**Architecture:** Three new layers stacked on top of the existing v1 design.

1. **Universal AX classifier** — pure-Python tags (`url_bar`, `search_field`, `submit_button`, `link`, `tab`, `primary_input`, …) for any interactive element. Runs inside `Tree.get_state` so the LLM-rendered desktop state gains a `canonical` column and a `<focused_input>` block at the top.
2. **Per-task structured recorder** — runs after every `/control` invocation. Emits one YAML record to `60-Episodes/control-YYYY-MM-DD.md` with task, app(s), outcome, action trace, structured failure mode. No LLM.
3. **Daily learner** — cron at 03:00 reads yesterday's `control-*.md`, runs one Haiku call per app, replaces the auto-managed `## Auto-learned` section in `40-Apps/<slug>.md` with confirmed-working coordinates and patterns plus failures to avoid.

A small **per-task injector** (`load_app_context`) reads `40-Apps/<slug>.md` plus matching routines and prepends them to the agent's task as a `<app_context>` block, parallel to the existing `<identity_context>` block.

The existing weekly compactor (Plan E) keeps its slow cadence but its prompt is narrowed: it no longer writes app guidance — that is the daily learner's job.

**Tech Stack:** stdlib `asyncio`, Pydantic (already a dep), `yaml` (via `pyyaml`, already a dep), `anthropic` SDK (already a dep). No new external packages.

**Spec reference:** §16 (full amendment text), §6.3-6.4 (existing episodist + compactor), §4.2 (vault note schemas), §4.4 (hot-context injection).

**Prerequisite:** Plans A (agent core), B (vault + retriever + hot-context), D (observer events table — for window/app metadata), E (episodist — for the daily/weekly cadence machinery), I (backend — for `/control` route).

---

## File Structure

```
Yuki/
├── yuki/
│   ├── agent/
│   │   └── tree/
│   │       ├── canonical.py                 # NEW — universal AX classifier
│   │       ├── service.py                   # MODIFIED — call classifier in get_state
│   │       └── views.py                     # MODIFIED — add canonical/is_focused, render new column + <focused_input> block
│   └── feedback/
│       ├── __init__.py                      # NEW — exports recorder, learner, injector
│       ├── recorder.py                      # NEW — append YAML record per /control task
│       ├── injector.py                      # NEW — load_app_context(bundle_id) → str
│       └── learner.py                       # NEW — daily Haiku pass over control log
├── yuki/episodist/
│   └── compactor.py                         # MODIFIED — narrow prompt, drop "apps" scope
├── yuki/backend/routers/
│   └── chat.py                              # MODIFIED — /control wraps agent.ainvoke with injector + recorder
└── tests/
    ├── agent/tree/
    │   └── test_canonical.py                # NEW
    └── feedback/
        ├── __init__.py
        ├── conftest.py
        ├── test_recorder.py
        ├── test_injector.py
        └── test_learner.py
```

---

## Order of execution

1. **Task 1** — Universal AX classifier (the cold-start fix; helps every app on day 1).
2. **Task 2** — Tree renderer changes (`canonical`, `is_focused`, `<focused_input>` block).
3. **Task 3** — Per-task recorder (deterministic, no LLM; starts capturing data immediately).
4. **Task 4** — `/control` injector (`load_app_context`; agent starts reading existing app notes today).
5. **Task 5** — Daily learner (Haiku pass; turns recorder output into guidance the injector picks up).
6. **Task 6** — Narrow weekly compactor's prompt (stop writing app guidance).
7. **Task 7** — Wire scheduler entry for the daily learner (launchd plist, mirrors Plan E's cadence).
8. **Task 8** — End-to-end smoke test (re-run the YouTube task; capture a `control-*.md` record; confirm the next run sees `<app_context>`).

Total estimate: ~9 hours.

---

## Task 1 — Universal AX classifier

**Files:**
- Create: `yuki/agent/tree/canonical.py`
- Create: `tests/agent/tree/test_canonical.py`

The classifier is a pure function: given a `TreeElementNode` + (optional) the focused-element id, return a stable canonical role string or `None`. Rules use AX attributes only — no app-specific code, no bundle-id checks.

- [ ] **Step 1: Write the failing test**

`tests/agent/tree/test_canonical.py`:

```python
"""Universal AX classifier — canonical role tagging."""

from __future__ import annotations

from yuki.agent.tree.canonical import classify
from yuki.agent.tree.views import BoundingBox, Center, TreeElementNode


def _node(role="AXTextField", name="", role_description="", subrole="",
          metadata=None, window="", focused=False):
    md = {"role_description": role_description, "subrole": subrole}
    if metadata:
        md.update(metadata)
    return TreeElementNode(
        bounding_box=BoundingBox(0, 0, 100, 30, 100, 30),
        center=Center(50, 15),
        name=name,
        control_type=role,
        window_name=window,
        metadata={k: v for k, v in md.items() if v},
    ), focused


def test_url_bar_by_role_description() -> None:
    n, focused = _node(role="AXTextField",
                       role_description="address and search bar",
                       window="Chrome")
    assert classify(n, is_focused=focused) == "url_bar"


def test_url_bar_by_value_pattern() -> None:
    n, _ = _node(role="AXTextField",
                 metadata={"value": "https://example.com"},
                 window="Safari")
    assert classify(n, is_focused=False) == "url_bar"


def test_search_field_by_subrole() -> None:
    n, _ = _node(role="AXTextField", subrole="AXSearchField",
                 window="Finder")
    assert classify(n, is_focused=False) == "search_field"


def test_search_field_by_placeholder() -> None:
    n, _ = _node(role="AXTextField",
                 metadata={"placeholder": "Search files..."},
                 window="Cursor")
    assert classify(n, is_focused=False) == "search_field"


def test_text_input_catchall() -> None:
    n, _ = _node(role="AXTextField", name="Note body",
                 window="Notes")
    assert classify(n, is_focused=False) == "text_input"


def test_submit_button() -> None:
    n, _ = _node(role="AXButton", name="Send", window="Mail")
    assert classify(n, is_focused=False) == "submit_button"


def test_cancel_button() -> None:
    n, _ = _node(role="AXButton", name="Cancel", window="Mail")
    assert classify(n, is_focused=False) == "cancel_button"


def test_link() -> None:
    n, _ = _node(role="AXLink", name="example.com",
                 metadata={"url": "https://example.com"})
    assert classify(n, is_focused=False) == "link"


def test_tab_inside_tab_group() -> None:
    n, _ = _node(role="AXRadioButton", name="Inbox",
                 metadata={"in_tab_group": True})
    assert classify(n, is_focused=False) == "tab"


def test_primary_input_when_focused() -> None:
    n, _ = _node(role="AXTextField",
                 metadata={"placeholder": "Type a message"},
                 window="Slack")
    assert classify(n, is_focused=True) == "primary_input"


def test_no_match_returns_none() -> None:
    n, _ = _node(role="AXImage", name="logo")
    assert classify(n, is_focused=False) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/tree/test_canonical.py -v`
Expected: ModuleNotFoundError on `yuki.agent.tree.canonical`.

- [ ] **Step 3: Implement `yuki/agent/tree/canonical.py`**

```python
"""Universal AX element classifier.

For every interactive node returned by the AX walk, assign a stable canonical
role string the LLM can rely on across apps. Rules use AX attributes only —
no app-specific code, no bundle-id checks. Apps that follow the macOS AX
spec (which Apple requires) get classified; apps that don't get None and
fall back to generic AX info.
"""

from __future__ import annotations

import re

from yuki.agent.tree.views import TreeElementNode

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_SEARCH_RE = re.compile(r"\bsearch\b", re.IGNORECASE)
_ADDR_RE = re.compile(r"\b(address|url|location)\b", re.IGNORECASE)

_SUBMIT_NAMES = {"submit", "send", "go", "ok", "confirm", "search", "post"}
_CANCEL_NAMES = {"cancel", "close", "dismiss", "back"}

_TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox"}


def _meta(node: TreeElementNode, key: str) -> str:
    return str(node.metadata.get(key) or "")


def classify(node: TreeElementNode, *, is_focused: bool) -> str | None:
    """Return canonical role tag, or None if no rule matches.

    The single focused text-like element gets `primary_input`. Other matches
    fall through to the most specific rule.
    """
    role = node.control_type or ""
    name = (node.name or "").strip().lower()
    subrole = _meta(node, "subrole")
    role_desc = _meta(node, "role_description").lower()
    placeholder = _meta(node, "placeholder").lower()
    value = _meta(node, "value")

    # url_bar: address-bar text field in any browser
    if role == "AXTextField":
        if _ADDR_RE.search(role_desc):
            return "url_bar"
        if value and _URL_RE.match(value.strip()):
            return "url_bar"

    # search_field: dedicated search input (Spotlight, Finder, app search)
    if role == "AXTextField":
        if subrole == "AXSearchField":
            return "search_field"
        if _SEARCH_RE.search(placeholder):
            return "search_field"

    # primary_input: the focused text-like field — model's default type target
    if is_focused and role in _TEXT_ROLES:
        return "primary_input"

    # text_input: catch-all for editable text
    if role in _TEXT_ROLES:
        return "text_input"

    # submit / cancel buttons by canonical name set
    if role == "AXButton":
        if name in _SUBMIT_NAMES:
            return "submit_button"
        if name in _CANCEL_NAMES:
            return "cancel_button"

    # link: AXLink with a URL attribute
    if role == "AXLink":
        return "link"

    # tab: radio button or button inside an AXTabGroup
    if node.metadata.get("in_tab_group") and role in ("AXRadioButton", "AXButton"):
        return "tab"

    return None
```

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/tree/test_canonical.py -v
git add yuki/agent/tree/canonical.py tests/agent/tree/test_canonical.py
git commit -m "feat(agent): universal AX element classifier (Plan M Task 1)"
```

Expected: 11 PASS.

---

## Task 2 — Tree renderer changes

**Files:**
- Modify: `yuki/agent/tree/views.py`
- Modify: `yuki/agent/tree/service.py`

Three changes:

(a) Add `is_focused: bool = False` and `canonical: str | None = None` to `TreeElementNode`.
(b) `Tree.get_state` reads the per-window focused element (via `kAXFocusedUIElement` on the window's process), tags every interactive node with `is_focused`, then runs `classify(node, is_focused=...)` to fill `canonical`.
(c) `interactive_elements_to_string` adds two columns and a `<focused_input>` block prefix.

- [ ] **Step 1: Write the failing tests**

Append to `tests/agent/tree/test_canonical.py` (or in a new sibling file `test_tree_render.py`):

```python
"""TreeState renders new canonical + focused columns; emits <focused_input>."""

from __future__ import annotations

from yuki.agent.tree.views import (
    BoundingBox, Center, TreeElementNode, TreeState,
)


def _node(role, name, x=10, y=20, **md):
    return TreeElementNode(
        bounding_box=BoundingBox(0, 0, 100, 30, 100, 30),
        center=Center(x, y),
        name=name,
        control_type=role,
        window_name="App",
        metadata=md,
    )


def test_render_includes_focused_and_canonical_columns() -> None:
    a = _node("AXTextField", "Address bar", role_description="address and search bar")
    a.is_focused = True
    a.canonical = "url_bar"
    b = _node("AXButton", "Reload")
    state = TreeState(interactive_nodes=[a, b])
    out = state.interactive_elements_to_string()
    # Header now lists focused + canonical columns
    assert "focused" in out
    assert "canonical" in out
    # The focused row carries YES + url_bar
    assert "YES" in out
    assert "url_bar" in out


def test_focused_input_block_when_text_focused() -> None:
    a = _node("AXTextField", "Address bar")
    a.is_focused = True
    a.canonical = "primary_input"
    state = TreeState(interactive_nodes=[a])
    out = state.interactive_elements_to_string()
    assert out.startswith("<focused_input>")
    assert "primary_input" in out
    assert "(10,20)" in out


def test_no_focused_input_block_when_focus_is_not_text() -> None:
    a = _node("AXButton", "Reload")
    a.is_focused = True
    a.canonical = None
    state = TreeState(interactive_nodes=[a])
    out = state.interactive_elements_to_string()
    assert not out.startswith("<focused_input>")
```

- [ ] **Step 2: Modify `yuki/agent/tree/views.py`**

Add fields to `TreeElementNode`:

```python
@dataclass
class TreeElementNode:
    bounding_box: BoundingBox
    center: Center
    name: str = ''
    control_type: str = ''
    window_name: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
    is_focused: bool = False           # NEW
    canonical: str | None = None       # NEW
```

Update `interactive_elements_to_string` on `TreeState`:

```python
def interactive_elements_to_string(self) -> str:
    parts: list[str] = []
    if not self.status:
        parts.append(WARNING_MESSAGE)
        return "\n".join(parts)
    if not self.interactive_nodes and self.status:
        parts.append(EMPTY_MESSAGE)
        return "\n".join(parts)

    # Surface the focused text-like element at the top so the LLM can't miss it.
    focused = next(
        (n for n in self.interactive_nodes
         if n.is_focused and n.canonical in {"primary_input", "url_bar",
                                              "search_field", "text_input"}),
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

    header = "# id|window|role|canonical|name|coords|focused|value"
    rows = [header]
    for idx, node in enumerate(self.interactive_nodes):
        canonical = node.canonical or "-"
        focused_mark = "YES" if node.is_focused else "-"
        value = node.metadata.get("value") or "-"
        rows.append(
            f"{idx}|{node.window_name}|{node.control_type}|{canonical}|"
            f"{node.name}|{node.center.to_string()}|{focused_mark}|{value}"
        )
    parts.append("\n".join(rows))
    return "\n".join(parts)
```

- [ ] **Step 3: Modify `yuki/agent/tree/service.py`**

After the AX walk produces `interactive_nodes`, capture the focused element id and run the classifier:

```python
# Inside Tree.get_state, after interactive_nodes is built:
from yuki.agent.tree.canonical import classify

focused_id = None
if active_window:
    try:
        win_el = ax.GetFocusedElementForWindow(active_window)  # see step 4
        focused_id = id(win_el) if win_el else None
    except Exception:
        focused_id = None

for node in interactive_nodes:
    node.is_focused = (
        getattr(node, "_ax_id", None) is not None
        and node._ax_id == focused_id
    )
    node.canonical = classify(node, is_focused=node.is_focused)
```

- [ ] **Step 4: Add `GetFocusedElementForWindow` to `yuki/ax/core.py`**

If not already present, add a thin helper that reads `kAXFocusedUIElement` from a window's parent application. The AX walker already collects per-element ids during traversal; surface them as `_ax_id` on `TreeElementNode` so the focus check is a single comparison.

If exposing per-element AXUIElementRef equality is too invasive, a fallback is to compare bounding boxes: any interactive node whose center is inside the focused element's frame counts as focused. Implement whichever is simpler in the existing AX module.

- [ ] **Step 5: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/agent/tree/ -v
git add yuki/agent/tree/views.py yuki/agent/tree/service.py yuki/ax/core.py tests/agent/tree/test_tree_render.py
git commit -m "feat(agent): tree render adds canonical + focused; <focused_input> block (Plan M Task 2)"
```

Expected: 3 PASS in `test_tree_render.py`; full project still green.

---

## Task 3 — Per-task structured recorder

**Files:**
- Create: `yuki/feedback/__init__.py`
- Create: `yuki/feedback/recorder.py`
- Create: `tests/feedback/__init__.py`
- Create: `tests/feedback/conftest.py`
- Create: `tests/feedback/test_recorder.py`

The recorder is a deterministic Python pass — no LLM. It accepts a list of `(action, observation)` pairs the agent loop already collects and emits one YAML record into `~/YukiVault/60-Episodes/control-YYYY-MM-DD.md`. Records are append-only.

- [ ] **Step 1: Add fixtures**

`tests/feedback/__init__.py` (empty) and `tests/feedback/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault_for_feedback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    (vault / "60-Episodes").mkdir(parents=True)
    (vault / "40-Apps").mkdir(parents=True)
    return vault
```

- [ ] **Step 2: Write the failing test**

`tests/feedback/test_recorder.py`:

```python
"""Per-task recorder: appends one YAML record to control-YYYY-MM-DD.md."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from yuki.feedback.recorder import (
    ActionTrace, FailureMode, TaskRecord, append_task_record,
)


def _record(outcome="success", failure=FailureMode.NONE):
    base = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)
    return TaskRecord(
        task="open chrome and open new tab and open youtube in it",
        conversation_id="abc123",
        started_at=base,
        duration_s=8.2,
        steps_used=4,
        outcome=outcome,
        apps_involved=["com.google.Chrome"],
        actions=[
            ActionTrace(
                tool="shortcut_tool",
                params={"shortcut": "command+t"},
                ax_window_after="Chrome - New Tab",
                ax_focused_after="url_bar (Chrome)",
                result="success",
            ),
            ActionTrace(
                tool="type_tool",
                params={"loc": [820, 180], "text": "youtube.com",
                        "press_enter": True},
                ax_focused_before="url_bar (Chrome)",
                ax_value_after="youtube.com",
                result="success",
            ),
        ],
        failure_mode=failure,
        recovery_attempts=0,
    )


def test_writes_yaml_file_with_dated_name(tmp_vault_for_feedback: Path) -> None:
    append_task_record(_record())
    out = tmp_vault_for_feedback / "60-Episodes" / "control-2026-05-28.md"
    assert out.exists()


def test_record_round_trips_through_yaml(tmp_vault_for_feedback: Path) -> None:
    append_task_record(_record())
    out = (tmp_vault_for_feedback / "60-Episodes" / "control-2026-05-28.md").read_text()
    # File starts with a header then a YAML list block.
    body = out.split("```yaml", 1)[1].split("```", 1)[0]
    parsed = yaml.safe_load(body)
    assert isinstance(parsed, list)
    assert parsed[0]["task"].startswith("open chrome")
    assert parsed[0]["apps_involved"] == ["com.google.Chrome"]


def test_appends_multiple_records_to_same_file(tmp_vault_for_feedback: Path) -> None:
    append_task_record(_record())
    append_task_record(_record(outcome="failure",
                                failure=FailureMode.WRONG_COORDS))
    out = (tmp_vault_for_feedback / "60-Episodes" / "control-2026-05-28.md").read_text()
    body = out.split("```yaml", 1)[1].split("```", 1)[0]
    parsed = yaml.safe_load(body)
    assert len(parsed) == 2
    assert parsed[1]["outcome"] == "failure"
    assert parsed[1]["failure_mode"] == "wrong_coords"


def test_secrets_are_redacted(tmp_vault_for_feedback: Path) -> None:
    base = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)
    rec = TaskRecord(
        task="sign in to API console",
        conversation_id="x",
        started_at=base,
        duration_s=1.0,
        steps_used=1,
        outcome="success",
        apps_involved=["com.apple.Safari"],
        actions=[
            ActionTrace(
                tool="type_tool",
                params={"loc": [100, 200],
                        "text": "sk-real-secret",
                        "press_enter": True,
                        "api_key": "sk-real-secret"},
                ax_focused_before="primary_input",
                ax_value_after="<redacted>",
                result="success",
            )
        ],
        failure_mode=FailureMode.NONE,
        recovery_attempts=0,
    )
    append_task_record(rec)
    out = (tmp_vault_for_feedback / "60-Episodes" / "control-2026-05-28.md").read_text()
    assert "sk-real-secret" not in out
    assert "<redacted>" in out
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/feedback/test_recorder.py -v`
Expected: ModuleNotFoundError on `yuki.feedback.recorder`.

- [ ] **Step 4: Implement `yuki/feedback/__init__.py`**

```python
"""Agent self-improvement feedback loop (Plan M)."""
```

- [ ] **Step 5: Implement `yuki/feedback/recorder.py`**

```python
"""Per-task structured recorder. Appends YAML records to 60-Episodes/control-YYYY-MM-DD.md.

Pure deterministic Python — no LLM. Reuses the trajectory redactor (Plan I)
to scrub secrets before writing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from yuki.backend.trajectory import _redact  # internal; intentional reuse
from yuki.memory import paths


class FailureMode(StrEnum):
    NONE = "null"
    WRONG_COORDS = "wrong_coords"
    ELEMENT_NOT_FOCUSED = "element_not_focused"
    TOOL_VALIDATION_ERROR = "tool_validation_error"
    LOOP_3_STRIKES = "loop_3_strikes"
    AGENT_STEP_LIMIT = "agent_step_limit"
    PROVIDER_ERROR = "provider_error"


@dataclass
class ActionTrace:
    tool: str
    params: dict[str, Any]
    result: str  # "success" | "failure"
    ax_window_before: str | None = None
    ax_window_after: str | None = None
    ax_focused_before: str | None = None
    ax_focused_after: str | None = None
    ax_value_after: str | None = None


@dataclass
class TaskRecord:
    task: str
    conversation_id: str
    started_at: datetime
    duration_s: float
    steps_used: int
    outcome: str  # "success" | "failure" | "partial"
    apps_involved: list[str]
    actions: list[ActionTrace] = field(default_factory=list)
    failure_mode: FailureMode = FailureMode.NONE
    recovery_attempts: int = 0


def _path_for(day: datetime) -> Path:
    return paths.vault_dir() / "60-Episodes" / f"control-{day.date().isoformat()}.md"


def _existing_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "```yaml" not in text:
        return []
    body = text.split("```yaml", 1)[1].split("```", 1)[0]
    parsed = yaml.safe_load(body) or []
    return list(parsed) if isinstance(parsed, list) else []


def _to_dict(rec: TaskRecord) -> dict[str, Any]:
    d = asdict(rec)
    d["started_at"] = rec.started_at.isoformat()
    d["failure_mode"] = rec.failure_mode.value
    # Redact secrets in action params before persisting.
    d["actions"] = [_redact(a) for a in d["actions"]]
    return d


def append_task_record(record: TaskRecord) -> Path:
    """Append one record to the day's control-*.md file. Idempotent on path."""
    path = _path_for(record.started_at)
    existing = _existing_records(path)
    existing.append(_to_dict(record))

    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(existing, sort_keys=False, allow_unicode=True)
    text = (
        f"# /control task records — {record.started_at.date().isoformat()}\n\n"
        "```yaml\n"
        f"{body}"
        "```\n"
    )
    path.write_text(text, encoding="utf-8")
    return path
```

- [ ] **Step 6: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/feedback/test_recorder.py -v
git add yuki/feedback/__init__.py yuki/feedback/recorder.py tests/feedback/
git commit -m "feat(feedback): per-task structured recorder for /control (Plan M Task 3)"
```

Expected: 4 PASS.

---

## Task 4 — Per-task injector (`load_app_context`)

**Files:**
- Create: `yuki/feedback/injector.py`
- Create: `tests/feedback/test_injector.py`
- Modify: `yuki/backend/routers/chat.py` — `/control` calls injector + recorder

`load_app_context(bundle_id)` reads the matching `40-Apps/<slug>.md` plus any `30-Routines/*.md` whose frontmatter `apps:` list contains the bundle id. Output is a single string suitable for an `<app_context>` system-prompt block.

- [ ] **Step 1: Write the failing test**

`tests/feedback/test_injector.py`:

```python
"""Per-task injector: load_app_context concatenates app + matching routines."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.feedback.injector import load_app_context
from yuki.memory.frontmatter import write_file


def _now() -> str:
    return datetime(2026, 5, 28, tzinfo=UTC).isoformat()


def test_returns_empty_when_no_app_note(tmp_vault_for_feedback: Path) -> None:
    assert load_app_context("com.example.unknown") == ""


def test_loads_matching_app_note(tmp_vault_for_feedback: Path) -> None:
    p = tmp_vault_for_feedback / "40-Apps" / "Chrome.md"
    write_file(
        p,
        {
            "id": "app-chrome", "type": "app", "name": "Chrome",
            "bundle_id": "com.google.Chrome", "importance": "primary",
            "created_at": _now(), "updated_at": _now(),
            "confidence": 0.9, "source": ["scan"],
        },
        "## Auto-learned\n\n- URL bar coords: (820, 180)\n",
    )
    out = load_app_context("com.google.Chrome")
    assert "Chrome" in out
    assert "URL bar coords: (820, 180)" in out


def test_includes_matching_routine(tmp_vault_for_feedback: Path) -> None:
    app_path = tmp_vault_for_feedback / "40-Apps" / "Chrome.md"
    write_file(
        app_path,
        {
            "id": "app-chrome", "type": "app", "name": "Chrome",
            "bundle_id": "com.google.Chrome", "importance": "primary",
            "created_at": _now(), "updated_at": _now(),
            "confidence": 0.9, "source": ["scan"],
        },
        "App body.\n",
    )
    routine_path = tmp_vault_for_feedback / "30-Routines" / "morning.md"
    routine_path.parent.mkdir(parents=True, exist_ok=True)
    write_file(
        routine_path,
        {
            "id": "routine-morning", "type": "routine", "name": "Morning",
            "schedule": "weekdays 9am", "steps": [],
            "trusted": False, "apps": ["com.google.Chrome"],
            "created_at": _now(), "updated_at": _now(),
            "confidence": 0.9, "source": ["scan"],
        },
        "Open Gmail and triage inbox.",
    )
    out = load_app_context("com.google.Chrome")
    assert "Open Gmail" in out


def test_max_chars_caps_output(tmp_vault_for_feedback: Path) -> None:
    p = tmp_vault_for_feedback / "40-Apps" / "Chrome.md"
    write_file(
        p,
        {
            "id": "app-chrome", "type": "app", "name": "Chrome",
            "bundle_id": "com.google.Chrome", "importance": "primary",
            "created_at": _now(), "updated_at": _now(),
            "confidence": 0.9, "source": ["scan"],
        },
        "x" * 20000,
    )
    out = load_app_context("com.google.Chrome", max_chars=2000)
    assert len(out) <= 2000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/feedback/test_injector.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/feedback/injector.py`**

```python
"""Per-task app-context injector. Reads 40-Apps/<slug>.md plus matching routines."""

from __future__ import annotations

from yuki.memory.schemas import AppNote, RoutineNote
from yuki.memory.vault import Vault


def _resolve_app_note(vault: Vault, bundle_id: str) -> tuple[AppNote, str] | None:
    for note, body in vault.list_section("40-Apps"):
        if isinstance(note, AppNote) and note.bundle_id == bundle_id:
            return note, body
    return None


def _matching_routines(vault: Vault, bundle_id: str) -> list[tuple[RoutineNote, str]]:
    out: list[tuple[RoutineNote, str]] = []
    for note, body in vault.list_section("30-Routines"):
        if not isinstance(note, RoutineNote):
            continue
        # `apps` is in extra metadata on RoutineNote; default to empty.
        apps = getattr(note, "apps", None) or note.model_extra.get("apps", []) if hasattr(note, "model_extra") else []
        if bundle_id in apps:
            out.append((note, body))
    return out


def load_app_context(bundle_id: str, *, max_chars: int = 4000) -> str:
    """Return concatenated app note + matching routines for the foreground app.

    Empty string when no matching app note exists. Output is bounded by
    max_chars so prompt sizes stay predictable.
    """
    if not bundle_id:
        return ""
    vault = Vault()
    parts: list[str] = []

    pair = _resolve_app_note(vault, bundle_id)
    if pair is not None:
        note, body = pair
        parts.append(f"## App: {note.name} ({note.bundle_id})\n\n{body.strip()}\n")

    for routine, body in _matching_routines(vault, bundle_id):
        parts.append(f"## Routine: {routine.name}\n\n{body.strip()}\n")

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
```

- [ ] **Step 4: Wire into `/control`**

In `yuki/backend/routers/chat.py`, inside `_stream_control`, before `agent.ainvoke`:

```python
from yuki.feedback.injector import load_app_context

# Try to identify the foreground app via the desktop service.
foreground_bundle = ""
try:
    rt2 = get_runtime()
    desktop_state = rt2.vault  # placeholder; the agent's Desktop is internal
    # Real impl: ask Agent or Desktop for active_window.bundle_id BEFORE start.
    # For now, leave foreground_bundle empty until the desktop service exposes
    # a synchronous current_app() helper.
except Exception:
    foreground_bundle = ""

app_context = load_app_context(foreground_bundle) if foreground_bundle else ""
if app_context:
    framed = f"{framed}\n\n<app_context>\n{app_context}\n</app_context>"
```

The cleanest version reads `desktop.get_state().active_window.bundle_id` after the agent's desktop is initialized. The exact wiring depends on whether `Agent.ainvoke` exposes a hook before the loop starts; if not, add one (`Agent.preflight() → bundle_id`). Either route is fine — the test surface is `load_app_context` itself.

- [ ] **Step 5: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/feedback/test_injector.py -v
git add yuki/feedback/injector.py yuki/backend/routers/chat.py tests/feedback/test_injector.py
git commit -m "feat(feedback): load_app_context injector for /control (Plan M Task 4)"
```

Expected: 4 PASS.

---

## Task 5 — Daily learner

**Files:**
- Create: `yuki/feedback/learner.py`
- Create: `tests/feedback/test_learner.py`

The learner reads yesterday's `control-*.md`, groups records by `apps_involved`, and runs one Haiku call per app. Output replaces the auto-managed `## Auto-learned` section in `40-Apps/<slug>.md`. The handwritten part of the file (sections above `## Auto-learned`) is never touched.

- [ ] **Step 1: Write the failing test**

`tests/feedback/test_learner.py`: covers four cases — replaces existing `## Auto-learned`, no-op on empty day, skip apps without a note, preserve existing section on malformed Haiku response. Mock the Anthropic client via `patch("yuki.feedback.learner._client", return_value=fake_client)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/feedback/test_learner.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `yuki/feedback/learner.py`**

Public surface:

```python
def run_for_date(day: date) -> int:
    """Read control-<day>.md, group by apps_involved, run one Haiku call per
    app, replace the ## Auto-learned section in 40-Apps/<slug>.md.
    Returns the count of app notes updated."""
```

Internals:

- `_read_records(day)` — parse the YAML block from `60-Episodes/control-YYYY-MM-DD.md`.
- `_by_bundle(records)` — group by `apps_involved`.
- `_resolve_app_note_path(vault, bundle_id)` — walk `40-Apps/`, find the note whose `bundle_id` matches.
- `_summarize_via_haiku(app_name, bundle_id, records)` — single Haiku call with the bounded prompt below; returns `None` on failure to avoid wiping existing guidance.
- `_replace_auto_section(body, new_block, today)` — regex-based replacement that finds `\n## Auto-learned.*?(?=\n## |\Z)` and substitutes; appends if not present.

Prompt template:

```
You are reviewing yesterday's recorded /control task outcomes for the macOS
application `{app_name}` (bundle id `{bundle_id}`).

For each successful action, identify any reusable coordinate or pattern.
For each failure, identify the failure mode and propose specific guidance
the agent should follow next time.

Output ONLY two markdown subsections, no narrative:

### Confirmed working
- bullet 1
- bullet 2

### Avoid
- bullet 1
- bullet 2

If there are no items under a heading, write `- (none)` under it. Be
concrete: include exact coordinates, exact AX role names, exact placeholder
strings.
```

Append the YAML records below the prompt as the user message body. Use `claude-haiku-4-5`, `max_tokens=1500`.

On failure (empty content, JSON error, network exception): log a warning and **do not modify the existing app note**. Yesterday's guidance survives.

- [ ] **Step 4: Run tests + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/feedback/test_learner.py -v
git add yuki/feedback/learner.py tests/feedback/test_learner.py
git commit -m "feat(feedback): daily Haiku learner replaces ## Auto-learned in 40-Apps (Plan M Task 5)"
```

Expected: 4 PASS.

---

## Task 6 — Narrow weekly compactor scope

**Files:**
- Modify: `yuki/episodist/compactor.py`
- Modify: `tests/episodist/test_compactor.py` (existing) — assert it no longer proposes app entries

The compactor currently asks Haiku for *"recurring patterns worth capturing as routines, important people, or apps"*. After Plan M ships, apps are the daily learner's responsibility. Narrow the prompt to drop the apps clause and add an explicit forbid:

- [ ] **Step 1: Edit the prompt**

In `yuki/episodist/compactor.py`, change the `_PROMPT` constant from:

```
You are inspecting a user's recent computer activity to identify
recurring patterns worth capturing as routines, important people, or apps.
```

to:

```
You are inspecting a user's recent computer activity to identify
recurring patterns worth capturing as routines or important people.

DO NOT propose `type: app` entries — application guidance is managed by
a separate daily process.
```

Leave the rest of the prompt untouched.

- [ ] **Step 2: Update the existing test**

Add a case to `tests/episodist/test_compactor.py` that asserts: when Haiku returns a `type: app` entry, `apply()` skips it (or the prompt narrowing prevents it being proposed in the first place — easiest is a unit test on the prompt string).

```python
def test_compactor_prompt_forbids_app_entries():
    from yuki.episodist.compactor import _PROMPT
    assert "type: app" in _PROMPT
    assert "DO NOT propose" in _PROMPT
```

- [ ] **Step 3: Run + commit**

```bash
uv run pytest tests/episodist/ -v
git add yuki/episodist/compactor.py tests/episodist/test_compactor.py
git commit -m "feat(episodist): weekly compactor no longer writes app guidance (Plan M Task 6)"
```

Expected: existing tests still pass; new prompt assertion passes.

---

## Task 7 — Scheduler entry for daily learner

**Files:**
- Create: `packaging/launchd/com.yuki.feedback.learner.plist`
- Create: `yuki/feedback/cli.py`
- Modify: `pyproject.toml` (optional: add console script)

The learner runs once a day at 03:00 local. Mirrors the existing `com.yuki.scheduler.plist` pattern (Plan K). Each cycle invokes a CLI entry point that calls `run_for_date(date.today() - timedelta(days=1))`.

- [ ] **Step 1: Implement `yuki/feedback/cli.py`**

```python
"""CLI: `python -m yuki.feedback.cli` runs the daily learner for yesterday."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from yuki.feedback.learner import run_for_date


def main() -> None:
    for env in (Path.cwd() / ".env",
                Path(__file__).resolve().parents[2] / ".env"):
        if env.exists():
            load_dotenv(env, override=False)
            break

    yesterday = date.today() - timedelta(days=1)
    updated = run_for_date(yesterday)
    print(f"yuki: feedback learner updated {updated} app note(s) for {yesterday}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement the launchd plist**

`packaging/launchd/com.yuki.feedback.learner.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.yuki.feedback.learner</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>uv</string>
    <string>run</string>
    <string>python</string>
    <string>-m</string>
    <string>yuki.feedback.cli</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/yuki.feedback.out.log</string>
  <key>StandardErrorPath</key><string>/tmp/yuki.feedback.err.log</string>
  <key>WorkingDirectory</key><string>HOME_PLACEHOLDER</string>
</dict>
</plist>
```

The packaging step (Plan K) substitutes `HOME_PLACEHOLDER` and copies the file to `~/Library/LaunchAgents/` on install.

- [ ] **Step 3: Commit**

```bash
git add yuki/feedback/cli.py packaging/launchd/com.yuki.feedback.learner.plist
git commit -m "feat(feedback): daily learner CLI + launchd entry (Plan M Task 7)"
```

No automated test for the launchd plist itself; manual verification via `launchctl load`.

---

## Task 8 — End-to-end smoke test

**Files:**
- Create: `tests/feedback/test_e2e.py`

A single end-to-end test verifies the loop closes:

1. Seed `40-Apps/Chrome.md` with handwritten body (no `## Auto-learned`).
2. Build a fake `TaskRecord` representing a successful Chrome run, write it via `append_task_record`.
3. Mock the Anthropic client to return canned `### Confirmed working` / `### Avoid` content.
4. Run `learner.run_for_date(today)`.
5. Read `40-Apps/Chrome.md`; assert handwritten body intact AND auto-learned section present AND its content is what the mocked client returned.
6. Call `injector.load_app_context("com.google.Chrome")`.
7. Assert the injector output contains the mocked `### Confirmed working` bullet text — proving the loop closed.

This is a tighter integration test than the unit tests in Tasks 3-5 — it walks the entire path the production system will follow. Implement after Tasks 1-7 land.

- [ ] **Step 1: Write the test, run it, commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/feedback/test_e2e.py -v
git add tests/feedback/test_e2e.py
git commit -m "test(feedback): end-to-end record→learn→inject smoke (Plan M Task 8)"
```

Expected: 1 test, passes.

---

## Acceptance for Plan M

After all 8 tasks land:

1. `uv run pytest -q` is green; mypy strict + ruff clean.
2. The full project test count rises by ≥20 (`tests/agent/tree/test_canonical.py` ≥11, `tests/agent/tree/test_tree_render.py` ≥3, `tests/feedback/` ≥13).
3. A `/control` task against Chrome produces `60-Episodes/control-YYYY-MM-DD.md` with at least one parseable YAML record.
4. Re-running the same task on day N+1 — after the learner has run on day N's record — shows the agent's task being prepended with `<app_context>` containing the auto-learned guidance from day N.
5. The weekly compactor no longer writes `type: app` entries.
6. The end-to-end YouTube task (`/control open chrome and open new tab and open youtube in it`) succeeds on a fresh vault, then succeeds with fewer fallback steps after one day of recorded successes.

---

## What this plan does not do (intentional non-goals)

- **No vision / screenshots.** Same constraint as the rest of v1.
- **No auto-execution of learned recipes.** The learner writes natural-language guidance; the agent reads it as part of its prompt. We do not bypass the LLM.
- **No cross-user learning.** Each user's vault is private.
- **Does not replace the universal classifier with per-app detectors.** The classifier is rule-based and AX-only by design.
- **Does not touch the existing trigger engine, episodist daily builder, or weekly compactor's narrative output.** Only the compactor's *prompt scope* narrows.
