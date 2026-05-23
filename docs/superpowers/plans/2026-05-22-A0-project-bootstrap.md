# Plan A0 — Project Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up an empty `Yuki/` repository with a working Python toolchain (`uv` + `pytest` + `ruff` + `mypy`), a CI skeleton, and the directory layout from the design spec, so every subsequent plan can assume the environment is ready.

**Architecture:** Single Python package `yuki/` at the repo root. Driven by `uv` for dependency management and virtualenv. Tests with `pytest`, lint with `ruff`, types with `mypy --strict`. GitHub Actions CI runs lint + types + tests on every push. No application code in this plan — only scaffolding and the smallest possible smoke test that proves the toolchain works end-to-end.

**Tech Stack:** Python 3.12, uv 0.5+, pytest 8+, pytest-asyncio, ruff 0.7+, mypy 1.11+, GitHub Actions. macOS 12+ as the target.

**Spec reference:** `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` §3.2 (module layout), §10 (packaging — `pyproject.toml`-driven build later), §15 (acceptance criteria). The spec lives **inside this project directory** at `Yuki/docs/superpowers/specs/`.

---

## Pre-flight

- Project root **already exists** at `/Users/mafex/code/personal/Yuki/` and contains `docs/superpowers/specs/` (the design spec) and `docs/superpowers/plans/` (this plan).
- Working tree currently has only `docs/` — no Python code, no git repo, no toolchain.
- Engineer should have `uv` installed: `brew install uv` (or `curl -LsSf https://astral.sh/uv/install.sh | sh`). Verify: `uv --version` returns ≥0.5.0.
- Engineer should have a GitHub account; CI assumes the repo will be pushed to `https://github.com/<user>/Yuki`.

---

## File Structure

After this plan, the project will look like:

```
Yuki/
├── .github/
│   └── workflows/
│       └── ci.yml                       # GitHub Actions: lint + types + tests
├── .gitignore
├── .python-version                      # pinned 3.12
├── pyproject.toml                       # uv-managed; deps + tool config
├── README.md                            # short, points at design spec
├── LICENSE                              # MIT
├── docs/                                # ALREADY EXISTS — do not create or modify
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-05-22-yuki-macos-design.md
│       └── plans/
│           └── 2026-05-22-A0-project-bootstrap.md
├── yuki/
│   ├── __init__.py                      # exports __version__
│   └── _smoke.py                        # tiny pure function used to prove tests run
└── tests/
    ├── __init__.py
    ├── conftest.py                      # empty for now, just a marker
    └── test_smoke.py                    # asserts _smoke works
```

The full module tree from spec §3.2 (`yuki/agent/`, `yuki/memory/`, `yuki/observer/`, etc.) is **NOT** created here — those directories are created by their owning subsystem plans (Plan A onwards). Creating empty dirs ahead of time invites import-path drift; let each subsystem own its layout.

Each subsystem plan will assume `pyproject.toml`, `tests/`, `.github/workflows/ci.yml`, lint, type-check, and the test runner already work.

The `docs/` directory is already populated and committed in the parent monorepo; this plan does not touch it.

---

## Task 1 — Initialize the git repo inside Yuki/

**Files:**
- The directory `/Users/mafex/code/personal/Yuki/` already exists and contains `docs/`.

- [ ] **Step 1: Confirm working tree state**

```bash
cd /Users/mafex/code/personal/Yuki
ls -A
```
Expected: only `docs`. If anything else is there, STOP — ask the user before proceeding.

- [ ] **Step 2: Initialize git repo (independent from any parent)**

```bash
cd /Users/mafex/code/personal/Yuki
git init -b main
```
Expected: `Initialized empty Git repository in /Users/mafex/code/personal/Yuki/.git/`

Note: `Yuki/` will become its own standalone repository. The parent `personal/` monorepo is unrelated and stays separate. The `docs/` directory inside `Yuki/` is currently tracked by the parent monorepo; once we commit it to `Yuki/`'s own git history, you have a duplicate — that's fine and intentional. The Yuki repo will be the canonical home for Yuki docs going forward; the parent's copy is just a snapshot of the brainstorm.

- [ ] **Step 3: Stage the existing docs/ as the first thing in the new repo**

We do this in Task 2 along with `.gitignore` and the rest of the scaffolding, so a single commit captures the initial repo state.

---

## Task 2 — Scaffold pyproject + lockfile + venv

**Files:**
- Create: `/Users/mafex/code/personal/Yuki/.python-version`
- Create: `/Users/mafex/code/personal/Yuki/.gitignore`
- Create: `/Users/mafex/code/personal/Yuki/pyproject.toml`
- Create: `/Users/mafex/code/personal/Yuki/README.md`
- Create: `/Users/mafex/code/personal/Yuki/LICENSE`

- [ ] **Step 1: Pin Python version**

Create `/Users/mafex/code/personal/Yuki/.python-version`:

```
3.12
```

- [ ] **Step 2: Write `.gitignore`**

Create `/Users/mafex/code/personal/Yuki/.gitignore`:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.eggs/
build/
dist/
.venv/
venv/

# uv
.uv-cache/

# Test / coverage
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# macOS
.DS_Store

# Editors
.vscode/
.idea/
*.swp
*~

# Yuki runtime artifacts (when the app eventually runs)
/Yuki.app/
/dist-app/
~/Library/Application Support/Yuki/
~/Library/Caches/Yuki/
```

- [ ] **Step 3: Write `pyproject.toml`**

Create `/Users/mafex/code/personal/Yuki/pyproject.toml`:

```toml
[project]
name = "yuki"
version = "0.0.1"
description = "A macOS-native personal AI assistant that learns who you are"
readme = "README.md"
requires-python = ">=3.12,<3.13"
license = { text = "MIT" }
authors = [
    { name = "Sudhanshu Pandit" },
]
keywords = [
    "macos",
    "ai-agent",
    "personal-assistant",
    "computer-use",
    "memory",
]
classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Environment :: MacOS X",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Operating System :: MacOS :: MacOS X",
    "Programming Language :: Python :: 3.12",
]
dependencies = []

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.7.0",
    "mypy>=1.11.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["yuki"]

# ---------------------------------------------------------------------------
# pytest

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
]
asyncio_mode = "auto"
filterwarnings = [
    "error",
]

# ---------------------------------------------------------------------------
# ruff

[tool.ruff]
target-version = "py312"
line-length = 100
extend-exclude = ["build", "dist"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "F",    # pyflakes
    "W",    # pycodestyle warnings
    "I",    # isort
    "N",    # pep8-naming
    "B",    # flake8-bugbear
    "UP",   # pyupgrade
    "SIM",  # flake8-simplify
    "RUF",  # ruff-specific
]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

# ---------------------------------------------------------------------------
# mypy

[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_configs = true
warn_unreachable = true
show_error_codes = true
files = ["yuki", "tests"]
```

- [ ] **Step 4: Write a minimal `README.md`**

Create `/Users/mafex/code/personal/Yuki/README.md`:

```markdown
# Yuki

A macOS-native personal AI assistant that learns who you are.

**Status:** Pre-alpha. See `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` for the full design and `docs/superpowers/plans/` for implementation plans.

## Develop

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy
```
```

- [ ] **Step 5: Write `LICENSE` (MIT)**

Create `/Users/mafex/code/personal/Yuki/LICENSE`:

```
MIT License

Copyright (c) 2026 Sudhanshu Pandit

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 6: Sync env via uv**

```bash
cd /Users/mafex/code/personal/Yuki
uv sync --all-extras
```

Expected: `uv` creates `.venv/`, installs pytest/ruff/mypy, generates `uv.lock`. Last line: `Installed N packages in Xms`.

- [ ] **Step 7: Stage and commit the scaffolding (including pre-existing docs/)**

```bash
cd /Users/mafex/code/personal/Yuki
git add .python-version .gitignore pyproject.toml README.md LICENSE uv.lock docs
git commit -m "$(cat <<'EOF'
chore: scaffold project with uv, pytest, ruff, mypy

Sets up Python 3.12 toolchain, package metadata, and lint/type/test
configuration. Also captures the pre-existing docs/ tree (design spec
and plan A0) as the canonical home for Yuki documentation going
forward. No application code yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: a single commit on `main` containing 6 scaffolding files plus the entire `docs/` tree. Run `git log --oneline` and `git ls-files | head -20` to confirm.

---

## Task 3 — Add a smoke test (TDD: red → green)

The toolchain is configured but unproven. We add the smallest possible test to verify pytest collects, runs, and the package imports.

**Files:**
- Create: `/Users/mafex/code/personal/Yuki/yuki/__init__.py`
- Create: `/Users/mafex/code/personal/Yuki/yuki/_smoke.py`
- Create: `/Users/mafex/code/personal/Yuki/tests/__init__.py`
- Create: `/Users/mafex/code/personal/Yuki/tests/conftest.py`
- Create: `/Users/mafex/code/personal/Yuki/tests/test_smoke.py`

- [ ] **Step 1: Write the failing test FIRST**

Create `/Users/mafex/code/personal/Yuki/tests/__init__.py` (empty file):

```python
```

Create `/Users/mafex/code/personal/Yuki/tests/conftest.py`:

```python
"""Pytest configuration. Currently a marker file; we'll add fixtures here later."""
```

Create `/Users/mafex/code/personal/Yuki/tests/test_smoke.py`:

```python
"""Smoke test that proves the toolchain end-to-end:
imports work, pytest runs, ruff/mypy will see real code."""

from yuki import __version__
from yuki._smoke import echo


def test_version_is_a_string() -> None:
    assert isinstance(__version__, str)
    assert __version__ == "0.0.1"


def test_echo_returns_input() -> None:
    assert echo("hello") == "hello"
    assert echo("") == ""


def test_echo_rejects_non_string() -> None:
    import pytest

    with pytest.raises(TypeError):
        echo(123)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the test to verify it fails (RED)**

```bash
cd /Users/mafex/code/personal/Yuki
uv run pytest tests/test_smoke.py -v
```

Expected: collection error or `ModuleNotFoundError: No module named 'yuki'`. This is the red state — we haven't written `yuki/` yet.

- [ ] **Step 3: Implement the minimal package to make it pass (GREEN)**

Create `/Users/mafex/code/personal/Yuki/yuki/__init__.py`:

```python
"""Yuki — a macOS-native personal AI assistant that learns who you are."""

__version__ = "0.0.1"
```

Create `/Users/mafex/code/personal/Yuki/yuki/_smoke.py`:

```python
"""Internal smoke-test helper. Will be removed once real code lands."""


def echo(value: str) -> str:
    """Return *value* unchanged. Used to prove the toolchain works."""
    if not isinstance(value, str):
        raise TypeError(f"echo expects str, got {type(value).__name__}")
    return value
```

- [ ] **Step 4: Run the test to verify it passes (GREEN)**

```bash
cd /Users/mafex/code/personal/Yuki
uv run pytest tests/test_smoke.py -v
```

Expected: 3 passed in ~0.1s.

- [ ] **Step 5: Run lint and types to make sure they're happy**

```bash
cd /Users/mafex/code/personal/Yuki
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Expected for each: clean exit (0). If `ruff format --check` reports diffs, run `uv run ruff format .` and re-check.

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add yuki tests
git commit -m "$(cat <<'EOF'
test: add smoke test proving toolchain works end-to-end

Tiny echo function in yuki/_smoke.py with a 3-case pytest covering
import, value passthrough, and TypeError on non-str. Exists only to
prove pytest collects from tests/, mypy sees yuki/, and ruff is happy.
Will be deleted once real code arrives in Plan A.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — Add CI workflow (lint + types + tests on every push)

**Files:**
- Create: `/Users/mafex/code/personal/Yuki/.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

Create `/Users/mafex/code/personal/Yuki/.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: lint + types + tests (Python 3.12, ${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [macos-14]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "0.5.x"
          enable-cache: true

      - name: Set up Python
        run: uv python install 3.12

      - name: Sync dependencies
        run: uv sync --all-extras

      - name: Ruff lint
        run: uv run ruff check .

      - name: Ruff format check
        run: uv run ruff format --check .

      - name: Mypy
        run: uv run mypy

      - name: Pytest
        run: uv run pytest -v --cov=yuki --cov-report=term-missing
```

Note: we run only on `macos-14` because the entire product is macOS-only. Adding `ubuntu-latest` would let us catch some pure-Python issues faster but masks the macOS reality and isn't worth the false-positive risk on PyObjC code arriving in later plans.

- [ ] **Step 2: Verify the workflow file parses (locally)**

GitHub Actions doesn't expose a CLI validator, but we can at least sanity-check YAML:

```bash
cd /Users/mafex/code/personal/Yuki
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add .github
git commit -m "$(cat <<'EOF'
ci: add GitHub Actions workflow for lint + types + tests

Runs on every push and PR to main. macOS-14 only — Yuki is macOS-only,
so testing on other runners would mask platform reality.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Optional — push to GitHub if remote is configured**

If the engineer has a GitHub remote ready:

```bash
cd /Users/mafex/code/personal/Yuki
git remote add origin https://github.com/<user>/Yuki.git
git push -u origin main
```

Then watch the first CI run: `gh run watch` (if `gh` CLI is installed).

If no remote yet, skip — the workflow file just sits and waits until the repo is pushed.

---

## Task 5 — Verify the bootstrap end-to-end and document the dev loop

**Files:**
- Modify: `/Users/mafex/code/personal/Yuki/README.md`

- [ ] **Step 1: Run the full local check pipeline**

```bash
cd /Users/mafex/code/personal/Yuki
uv sync --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -v
```

Expected: every command exits 0. `pytest` shows 3 passed.

- [ ] **Step 2: Expand `README.md` with the dev loop**

Replace `/Users/mafex/code/personal/Yuki/README.md` entirely with:

```markdown
# Yuki

A macOS-native personal AI assistant that learns who you are.

**Status:** Pre-alpha. See `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` in the parent monorepo for the full design.

## Requirements

- macOS 12+
- Python 3.12 (managed via `uv python install 3.12`)
- [uv](https://docs.astral.sh/uv/) 0.5+ (`brew install uv`)

## Development

```bash
# install or sync deps
uv sync --all-extras

# run all checks the way CI does
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -v

# auto-format
uv run ruff format .

# add a runtime dep
uv add some-package

# add a dev dep
uv add --dev some-package
```

## Layout

```
yuki/                  # main package; subsystems land here in later plans
tests/                 # pytest tests, mirrors yuki/ structure
.github/workflows/     # CI
pyproject.toml         # deps + tool config (ruff, mypy, pytest)
```

## License

MIT — see `LICENSE`.
```

- [ ] **Step 3: Re-run lint to make sure README didn't trip ruff**

```bash
cd /Users/mafex/code/personal/Yuki
uv run ruff check .
```

Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add README.md
git commit -m "$(cat <<'EOF'
docs: expand README with dev-loop instructions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Final repo state check**

```bash
cd /Users/mafex/code/personal/Yuki
git log --oneline
git status
```

Expected: 4 commits on main (scaffold, smoke test, CI, README); working tree clean.

---

## Acceptance criteria for this plan

The plan is done when **all** of the following are true:

1. `/Users/mafex/code/personal/Yuki/` is a git repo on `main` with ≥4 commits.
2. `git ls-files | grep docs/` shows the design spec and plan A0 tracked inside the repo.
3. `uv sync --all-extras` works from a fresh clone.
4. `uv run pytest -v` passes (3 tests).
5. `uv run ruff check .` exits 0.
6. `uv run ruff format --check .` exits 0.
7. `uv run mypy` exits 0 in strict mode.
8. `.github/workflows/ci.yml` parses as valid YAML and references the same commands as the local dev loop.

The smoke test (`yuki/_smoke.py`, `tests/test_smoke.py`) is intentionally throwaway — it gets deleted in Plan A as soon as real agent code lands.

---

## Out of scope for this plan (handled by later plans)

- Any application code under `yuki/agent/`, `yuki/memory/`, etc. — Plan A onwards
- Vendoring of MacOS-Use's `ax/` layer — Plan A
- LLM SDK dependencies (`anthropic`, `openai`, etc.) — Plan A
- PyObjC dependencies — Plan D (observer is the first place we need them; Plan A's agent fork brings them in if needed)
- Briefcase / packaging config — Plan K
- Frontend / Next.js setup — Plan I
- Swift / Xcode project — Plan J

---

## Notes for the executing engineer

- **Commit hygiene:** four commits in this plan, each with a descriptive Co-Authored-By trailer. Don't squash — having a clean per-task history makes it easier for later plans to point at exact baseline commits.
- **Why uv and not pip/poetry/pdm:** uv is the fastest of the modern Python managers (orders of magnitude over pip), bundles its own resolver, handles Python version installation, and is the same toolchain used by the wider Python community in 2026. Briefcase (Plan K) plays nicely with `pyproject.toml`-driven projects, so we're aligned.
- **Why mypy strict from day one:** retrofitting types is painful. `strict` on an empty repo costs zero; on a 5,000-line repo costs weeks.
- **Why filterwarnings = error in pytest:** any deprecation warning crashes a test. We catch upstream changes immediately instead of letting them silently rot.
