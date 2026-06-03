"""Augmentation must multiply surface variety while preserving correctness."""

from __future__ import annotations

import random

from training.augment import add_negative_samples, augment
from training.schema import validate_record


def _rng() -> random.Random:
    return random.Random(0)


def test_augment_expands_and_stays_valid() -> None:
    rows = augment(per_seed=10, rng=_rng())
    assert len(rows) > 100  # 34 seeds * up-to-10
    # The invariant that matters most: no augmented row is mislabeled/invalid.
    invalid = [(r["task"], validate_record(r)) for r in rows if validate_record(r)]
    assert invalid == [], f"augmentation produced invalid rows: {invalid[:3]}"


def test_app_augmentation_swaps_names_keeps_tool() -> None:
    rows = augment(per_seed=10, rng=_rng())
    app_rows = [r for r in rows if r["tool"] == "app_tool"]
    names = {r["args"]["name"] for r in app_rows}
    assert len(names) > 3, "app name should vary across many apps"
    # Every app row is still app_tool with a name arg (invariant preserved).
    for r in app_rows:
        assert r["tool"] == "app_tool" and r["args"].get("name")


def test_negative_samples_include_correct_and_distractors() -> None:
    rows = add_negative_samples(augment(per_seed=4, rng=_rng()), _rng())
    for r in rows:
        present = r["present_tools"]
        assert r["tool"] in present, "correct tool must be presented"
        assert "done_tool" in present, "done_tool always available"
        assert len(present) >= 2, "must include at least one distractor"
        assert len(set(present)) == len(present), "no duplicate tools"


def test_app_open_has_observed_wrong_pick_as_distractor_sometimes() -> None:
    # Over many app_tool rows, type_tool (the real observed mis-pick) should
    # appear as a distractor at least once — proving hard negatives are used.
    rows = add_negative_samples(augment(per_seed=12, rng=_rng()), _rng())
    app_rows = [r for r in rows if r["tool"] == "app_tool"]
    assert any("type_tool" in r["present_tools"] for r in app_rows)
