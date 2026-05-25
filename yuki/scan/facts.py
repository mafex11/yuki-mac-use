"""Fact: the unified intermediate representation between collectors and patterns."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

_EVIDENCE_CAP = 50


@dataclass
class Fact:
    subject: str
    predicate: str
    object: str
    confidence: float
    sources: list[str]
    evidence: list[dict[str, Any]]
    first_seen: datetime
    last_seen: datetime

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["first_seen"] = self.first_seen.isoformat()
        d["last_seen"] = self.last_seen.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fact:
        return cls(
            subject=d["subject"],
            predicate=d["predicate"],
            object=d["object"],
            confidence=d["confidence"],
            sources=list(d["sources"]),
            evidence=list(d["evidence"]),
            first_seen=datetime.fromisoformat(d["first_seen"]),
            last_seen=datetime.fromisoformat(d["last_seen"]),
        )

    @property
    def triple(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


def merge_evidence(a: Fact, b: Fact) -> Fact:
    sources = sorted(set(a.sources) | set(b.sources))
    evidence = (a.evidence + b.evidence)[:_EVIDENCE_CAP]
    return Fact(
        subject=a.subject,
        predicate=a.predicate,
        object=a.object,
        confidence=max(a.confidence, b.confidence),
        sources=sources,
        evidence=evidence,
        first_seen=min(a.first_seen, b.first_seen),
        last_seen=max(a.last_seen, b.last_seen),
    )


def dedupe(facts: list[Fact]) -> list[Fact]:
    by_triple: dict[tuple[str, str, str], Fact] = {}
    for f in facts:
        if f.triple in by_triple:
            by_triple[f.triple] = merge_evidence(by_triple[f.triple], f)
        else:
            by_triple[f.triple] = f
    return list(by_triple.values())
