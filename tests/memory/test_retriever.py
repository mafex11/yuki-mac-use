"""Hybrid retriever — FTS + vec, RRF merge, type filter."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer
from yuki.memory.retriever import Retriever
from yuki.memory.schemas import PersonNote, ProjectNote
from yuki.memory.vault import Vault


def _person(id_: str, name: str) -> PersonNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return PersonNote(
        id=id_,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        name=name,
    )


def _project(id_: str, name: str) -> ProjectNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return ProjectNote(
        id=id_,
        type="project",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        name=name,
        status="active",
    )


@pytest.fixture
def seeded(tmp_vault: Path) -> Iterator[tuple[Vault, Indexer]]:
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="engineering manager who runs standup")
    v.write(_person("person-bob", "Bob Liu"), body="data scientist focused on ranking")
    v.write(_project("project-yuki", "Yuki"), body="macos jarvis assistant")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    yield v, idx
    idx.close()


def test_search_returns_hits(seeded: tuple[Vault, Indexer]) -> None:
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("standup", k=5)
    assert any(h.id == "person-sarah" for h in hits)


def test_search_filters_by_type(seeded: tuple[Vault, Indexer]) -> None:
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("yuki", k=5, types=["project"])
    assert all(h.type == "project" for h in hits)


def test_search_k_caps_results(seeded: tuple[Vault, Indexer]) -> None:
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("a", k=2)
    assert len(hits) <= 2


def test_hit_has_snippet(seeded: tuple[Vault, Indexer]) -> None:
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("standup", k=1)
    assert hits[0].snippet  # non-empty
    assert len(hits[0].snippet) <= 220


def test_empty_query_returns_empty(seeded: tuple[Vault, Indexer]) -> None:
    _, idx = seeded
    r = Retriever(idx)
    assert r.search("", k=5) == []


def test_no_match_returns_list(seeded: tuple[Vault, Indexer]) -> None:
    _, idx = seeded
    r = Retriever(idx)
    hits = r.search("zzzzz-no-such-token-anywhere", k=5)
    # vec search may still return things; FTS is empty. Just confirm a list
    # comes back without raising.
    assert isinstance(hits, list)
