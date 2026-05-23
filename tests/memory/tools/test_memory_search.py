"""memory_search tool — wraps Retriever for the agent."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer
from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault
from yuki.tools.memory.memory_search import memory_search


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


@pytest.fixture
def memctx(tmp_vault: Path) -> Iterator[Indexer]:
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="standup runner")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    yield idx
    idx.close()


def test_memory_search_returns_dict_list(memctx: Indexer) -> None:
    out = memory_search(query="standup", k=3, indexer=memctx)
    assert isinstance(out, list)
    assert all(isinstance(h, dict) for h in out)
    assert any(h["id"] == "person-sarah" for h in out)


def test_memory_search_respects_types(memctx: Indexer) -> None:
    out = memory_search(query="standup", k=5, types=["project"], indexer=memctx)
    assert all(h["type"] == "project" for h in out)


def test_memory_search_empty_query(memctx: Indexer) -> None:
    assert memory_search(query="   ", k=5, indexer=memctx) == []
