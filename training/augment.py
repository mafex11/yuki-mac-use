"""Augment hand-authored seeds into a full training set.

Strategy (see module note in the plan): seeds carry semantic correctness;
this script multiplies SURFACE variety while preserving the (intent -> tool +
args) invariant. Transforms are tool-aware so we never relabel:

  - app_tool seeds: swap the app name across a roster of real macOS apps.
  - verb rephrasing: "open X" / "launch X" / "fire up X" / "start X".
  - shortcut/shell/etc. seeds: light phrasing variants only (args fixed).

Every generated row is re-validated against the real tool schema; invalid
rows are dropped. Output: train/val/test JSONL under training/data/.

Run:  uv run python -m training.augment --out training/data --per-seed 12
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from training.schema import valid_tool_names, validate_record
from training.seeds import SEEDS

# Real macOS apps to rotate app_tool examples across. Names match how the app
# appears in /Applications (what app_tool's `name` expects).
_APPS = [
    "Calculator", "Notes", "Safari", "Spotify", "Terminal", "Finder",
    "Mail", "Messages", "Calendar", "Reminders", "Music", "Preview",
    "System Settings", "Photos", "Maps", "Visual Studio Code", "Chrome",
    "Slack", "Discord", "Notion", "Obsidian", "Arc",
]

# Verb templates for app-launch phrasing. {app} is filled with the app name.
_LAUNCH_PHRASINGS = [
    "open {app}", "launch {app}", "open the {app} app", "start {app}",
    "fire up {app}", "can you open {app}", "i want to use {app}",
    "get {app} open", "bring up {app}",
]
_SWITCH_PHRASINGS = [
    "switch to {app}", "go to {app}", "bring {app} to the front",
    "focus {app}", "show me {app}",
]

# Light phrasing variants for non-app tasks (args stay identical).
_REPHRASE_PREFIXES = ["", "please ", "could you ", "hey, ", "now "]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _augment_app_seed(seed: dict[str, Any], n: int, rng: random.Random) -> list[dict[str, Any]]:
    """app_tool seeds → rotate app name + launch/switch phrasing."""
    mode = seed["args"].get("mode", "launch")
    phrasings = _SWITCH_PHRASINGS if mode == "switch" else _LAUNCH_PHRASINGS
    verb = "Bring {app} to the foreground." if mode == "switch" else "Launch {app}."
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempts = 0
    while len(out) < n and attempts < n * 6:
        attempts += 1
        app = rng.choice(_APPS)
        phrasing = rng.choice(phrasings).format(app=app)
        key = (app, phrasing)
        if key in seen:
            continue
        seen.add(key)  # type: ignore[arg-type]
        out.append({
            "task": phrasing,
            "screen": "",
            "tool": "app_tool",
            "args": {"thought": verb.format(app=app), "mode": mode, "name": app},
        })
    return out


def _augment_generic_seed(seed: dict[str, Any], n: int, rng: random.Random) -> list[dict[str, Any]]:
    """Non-app seeds → light phrasing prefixes; args unchanged."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    base = seed["task"]
    attempts = 0
    while len(out) < n and attempts < n * 6:
        attempts += 1
        prefix = rng.choice(_REPHRASE_PREFIXES)
        task = (prefix + base).strip()
        # Capitalize naturally after a prefix like "please ".
        task = task[0].upper() + task[1:] if task else task
        if task in seen:
            continue
        seen.add(task)
        row = {**seed, "task": task, "args": dict(seed["args"])}
        out.append(row)
    return out


def augment(per_seed: int, rng: random.Random) -> list[dict[str, Any]]:
    """Expand all seeds. app_tool seeds get richer (name+verb) variety."""
    rows: list[dict[str, Any]] = []
    for seed in SEEDS:
        if seed["tool"] == "app_tool":
            rows.extend(_augment_app_seed(seed, per_seed, rng))
        else:
            rows.extend(_augment_generic_seed(seed, per_seed, rng))
    return rows


# Plausible-but-wrong distractors per correct tool. Front-loaded with the
# ACTUAL wrong picks observed during the gate (e.g. base models chose type_tool
# for "open calculator", desktop_tool for "switch to Safari", list_app_notes
# for factual questions) so the fine-tune sharpens exactly those confusions.
_HARD_DISTRACTORS: dict[str, list[str]] = {
    "app_tool": ["type_tool", "desktop_tool", "click_tool", "shell_tool"],
    "shortcut_tool": ["click_tool", "type_tool", "multi_select_tool"],
    "shell_tool": ["app_tool", "list_app_notes", "type_tool"],
    "scroll_tool": ["move_tool", "desktop_tool", "click_tool"],
    "type_tool": ["click_tool", "shortcut_tool", "multi_edit_tool"],
    "click_tool": ["type_tool", "move_tool", "multi_select_tool"],
    "done_tool": ["shell_tool", "list_app_notes", "type_tool"],
    "wait_tool": ["scroll_tool", "shell_tool"],
    "desktop_tool": ["app_tool", "scroll_tool"],
    "list_app_notes": ["read_app_note", "shell_tool", "done_tool"],
}

_N_DISTRACTORS = 3  # distractors presented alongside the correct tool


def add_negative_samples(rows: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    """Annotate each row with `present_tools`: the correct tool + N plausible
    distractors, shuffled. At training time the model sees this set and must
    pick the right one — teaching discrimination, not single-tool memorization.

    Distractors are drawn first from the hard list (real observed mis-picks),
    topped up with random other tools if needed. `done_tool` is always present
    as an option (the agent can always choose to answer/finish), mirroring the
    always-include core at inference.
    """
    all_names = sorted(valid_tool_names())
    for row in rows:
        correct = row["tool"]
        hard = [t for t in _HARD_DISTRACTORS.get(correct, []) if t in all_names]
        rng.shuffle(hard)
        present = {correct, "done_tool"}
        for d in hard:
            if len(present) >= _N_DISTRACTORS + 1:
                break
            present.add(d)
        # Top up with random tools if we still need more distractors.
        while len(present) < _N_DISTRACTORS + 1:
            present.add(rng.choice(all_names))
        present_list = list(present)
        rng.shuffle(present_list)
        row["present_tools"] = present_list
    return rows


def _validate_and_split(
    rows: list[dict[str, Any]], rng: random.Random
) -> dict[str, list[dict[str, Any]]]:
    valid = [r for r in rows if not validate_record(r)]
    rng.shuffle(valid)
    n = len(valid)
    return {
        "train": valid[: int(n * 0.9)],
        "val": valid[int(n * 0.9): int(n * 0.95)],
        "test": valid[int(n * 0.95):],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="training/data")
    ap.add_argument("--per-seed", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = _rng(args.seed)
    rows = augment(args.per_seed, rng)
    rows = add_negative_samples(rows, rng)
    splits = _validate_and_split(rows, rng)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, recs in splits.items():
        (out / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    total = sum(len(v) for v in splits.values())
    dropped = len(rows) - total
    print(f"generated {len(rows)} rows, {total} valid ({dropped} dropped)")
    for name, recs in splits.items():
        print(f"  {name}: {len(recs)}")
    print(f"valid tools in use: {len({r['tool'] for v in splits.values() for r in v})}"
          f" / {len(valid_tool_names())}")


if __name__ == "__main__":
    main()
