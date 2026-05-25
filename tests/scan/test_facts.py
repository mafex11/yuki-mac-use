"""Fact dataclass + dedupe + merge_evidence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from yuki.scan.facts import Fact, dedupe, merge_evidence


def _f(
    subject: str = "Sarah Chen",
    predicate: str = "meets_with_recurring",
    object_: str = "user",
    confidence: float = 0.8,
    sources: Sequence[str] = ("calendar",),
    evidence: list[dict[str, Any]] | None = None,
) -> Fact:
    return Fact(
        subject=subject,
        predicate=predicate,
        object=object_,
        confidence=confidence,
        sources=list(sources),
        evidence=list(evidence or [{"event": "1:1"}]),
        first_seen=datetime(2026, 5, 1, tzinfo=UTC),
        last_seen=datetime(2026, 5, 22, tzinfo=UTC),
    )


def test_fact_round_trip_dict() -> None:
    f = _f()
    d = f.to_dict()
    f2 = Fact.from_dict(d)
    assert f2 == f


def test_dedupe_merges_same_triple() -> None:
    f1 = _f(sources=("calendar",), evidence=[{"a": 1}])
    f2 = _f(sources=("contacts",), evidence=[{"b": 2}])
    out = dedupe([f1, f2])
    assert len(out) == 1
    merged = out[0]
    assert set(merged.sources) == {"calendar", "contacts"}
    assert len(merged.evidence) == 2


def test_dedupe_keeps_distinct_triples() -> None:
    f1 = _f(predicate="meets_with_recurring")
    f2 = _f(predicate="emailed_user")
    assert len(dedupe([f1, f2])) == 2


def test_merge_evidence_caps_at_50() -> None:
    f1 = _f(evidence=[{"i": i} for i in range(40)])
    f2 = _f(evidence=[{"i": i} for i in range(40, 80)])
    merged = merge_evidence(f1, f2)
    assert len(merged.evidence) <= 50
