"""Guards: max_turns, max_budget."""

from __future__ import annotations

import pytest

from yuki.runtime.guards import GuardViolation, check_max_budget, check_max_turns


def test_max_turns_under() -> None:
    check_max_turns(current_turns=3, max_turns=10)


def test_max_turns_over_raises() -> None:
    with pytest.raises(GuardViolation) as exc:
        check_max_turns(current_turns=11, max_turns=10)
    assert "max_turns" in str(exc.value)


def test_max_budget_under() -> None:
    totals = {"input_tokens": 1000, "output_tokens": 500}
    check_max_budget(totals=totals, max_total_tokens=10_000)


def test_max_budget_over_raises() -> None:
    totals = {"input_tokens": 9000, "output_tokens": 5000}
    with pytest.raises(GuardViolation):
        check_max_budget(totals=totals, max_total_tokens=10_000)
