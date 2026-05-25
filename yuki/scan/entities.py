"""Entity: the typed bundle emitted by the pattern detector."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EntityKind = Literal["person", "project", "routine", "app", "identity"]


@dataclass
class Entity:
    kind: EntityKind
    id: str
    name: str
    confidence: float
    attributes: dict[str, Any]
    fact_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Entity:
        return cls(
            kind=d["kind"],
            id=d["id"],
            name=d["name"],
            confidence=d["confidence"],
            attributes=dict(d["attributes"]),
            fact_ids=list(d.get("fact_ids", [])),
        )
