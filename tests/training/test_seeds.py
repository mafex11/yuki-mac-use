"""Every hand-authored seed must be a valid training record."""

from __future__ import annotations

from training.schema import validate_record
from training.seeds import SEEDS


def test_seeds_nonempty() -> None:
    assert len(SEEDS) >= 30


def test_every_seed_is_valid() -> None:
    failures = [
        (s.get("task"), validate_record(s)) for s in SEEDS if validate_record(s)
    ]
    assert failures == [], f"invalid seeds: {failures}"


def test_seeds_cover_core_tools() -> None:
    used = {s["tool"] for s in SEEDS}
    # The high-frequency control surface must be represented.
    core = {"app_tool", "shortcut_tool", "shell_tool", "type_tool",
            "click_tool", "done_tool", "scroll_tool"}
    assert core <= used, f"missing core tools: {core - used}"


def test_reactive_seeds_have_screen() -> None:
    # type_tool / click_tool seeds act on screen elements → must carry a screen.
    for s in SEEDS:
        if s["tool"] in ("click_tool", "type_tool"):
            assert s["screen"].strip(), f"{s['task']!r} missing screen state"
