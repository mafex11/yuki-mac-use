"""Presenter: in-memory records, urgency-based routing, fallback to low."""

from __future__ import annotations

from datetime import UTC, datetime

from yuki.triggers.presenter import (
    InMemoryPresenter,
    Presenter,
    Suggestion,
    pick_presenter,
)


def _s(urgency: str = "low") -> Suggestion:
    return Suggestion(
        trigger_id="trigger-x",
        text="Suggestion text",
        urgency=urgency,
        ts=datetime.now(UTC),
    )


async def test_in_memory_presenter_records() -> None:
    p = InMemoryPresenter()
    await p.present(_s())
    await p.present(_s("high"))
    assert len(p.shown) == 2


def test_pick_presenter_routes_by_urgency() -> None:
    presenters: dict[str, Presenter] = {
        "low": InMemoryPresenter(),
        "medium": InMemoryPresenter(),
        "high": InMemoryPresenter(),
    }
    assert pick_presenter(_s("low"), presenters) is presenters["low"]
    assert pick_presenter(_s("high"), presenters) is presenters["high"]


def test_pick_presenter_unknown_urgency_falls_back_low() -> None:
    p_low = InMemoryPresenter()
    presenters: dict[str, Presenter] = {
        "low": p_low,
        "medium": InMemoryPresenter(),
        "high": InMemoryPresenter(),
    }
    assert pick_presenter(_s("zzz"), presenters) is p_low
