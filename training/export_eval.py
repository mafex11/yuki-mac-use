"""Export eval cases + tool descriptions to JSON (run in MAIN env, has yuki).

The training venv lacks Yuki's deps, so it reads cases from this JSON instead
of importing yuki.eval directly. See training/eval_mlx.py.
"""
from __future__ import annotations

import json


def main() -> None:
    from yuki.eval.cases import CASES, load_fixture
    from training.to_mlx import _descriptions

    cases = [{
        "task": c.task,
        "expected_tool": c.expected_plan[0].tool,
        "screen": load_fixture(c.ax_fixture) if c.ax_fixture else "",
    } for c in CASES]
    print(json.dumps({"cases": cases, "descriptions": _descriptions()}))


if __name__ == "__main__":
    main()
