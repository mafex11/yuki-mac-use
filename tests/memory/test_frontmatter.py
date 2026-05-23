"""YAML frontmatter helpers — round-trip safety."""

from __future__ import annotations

from pathlib import Path

from yuki.memory.frontmatter import dumps, loads, read_file, write_file

SAMPLE = """---
id: person-sarah-chen
type: person
name: Sarah Chen
confidence: 0.9
created_at: '2026-05-22T09:00:00Z'
updated_at: '2026-05-22T09:00:00Z'
source:
  - calendar
---

Sarah is the engineering manager.

Worked on [[Yuki]] launch.
"""


def test_loads_basic() -> None:
    fm, body = loads(SAMPLE)
    assert fm["id"] == "person-sarah-chen"
    assert fm["type"] == "person"
    assert "engineering manager" in body


def test_dumps_round_trip() -> None:
    fm, body = loads(SAMPLE)
    out = dumps(fm, body)
    fm2, body2 = loads(out)
    assert fm2 == fm
    assert body2.strip() == body.strip()


def test_loads_no_frontmatter() -> None:
    fm, body = loads("just a body, no frontmatter\n")
    assert fm == {}
    assert body.startswith("just a body")


def test_loads_empty_body() -> None:
    src = "---\nid: x-y\ntype: knowledge\n---\n"
    fm, body = loads(src)
    assert fm["id"] == "x-y"
    assert body == ""


def test_read_write_file(tmp_path: Path) -> None:
    p = tmp_path / "sarah.md"
    write_file(p, {"id": "person-sarah", "type": "person", "name": "Sarah"}, "Body text.")
    fm, body = read_file(p)
    assert fm["id"] == "person-sarah"
    assert body.strip() == "Body text."
