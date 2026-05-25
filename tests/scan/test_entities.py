"""Entity dataclass."""

from __future__ import annotations

from yuki.scan.entities import Entity


def test_entity_minimal() -> None:
    e = Entity(
        kind="person",
        id="person-sarah-chen",
        name="Sarah Chen",
        confidence=0.9,
        attributes={"role": "manager"},
        fact_ids=[],
    )
    assert e.kind == "person"
    assert e.attributes["role"] == "manager"


def test_entity_to_dict_round_trip() -> None:
    e = Entity(
        kind="project",
        id="project-yuki",
        name="Yuki",
        confidence=0.85,
        attributes={"status": "active"},
        fact_ids=["t1", "t2"],
    )
    d = e.to_dict()
    assert d["kind"] == "project"
    assert d["fact_ids"] == ["t1", "t2"]
    assert Entity.from_dict(d) == e
