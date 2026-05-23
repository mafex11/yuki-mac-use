"""SQLite indexer — schema, upsert, delete, reindex, dim mismatch."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer, IndexerError
from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault


def _person(id_: str, name: str) -> PersonNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return PersonNote(
        id=id_,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["calendar"],
        name=name,
    )


def test_open_creates_schema(tmp_vault: Path) -> None:
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    assert idx.row_count() == 0
    idx.close()


def test_upsert_then_count(tmp_vault: Path) -> None:
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.upsert(_person("person-a", "A"), body="alice rocks", path=tmp_vault / "10-People/A.md")
    assert idx.row_count() == 1
    idx.close()


def test_upsert_replaces_same_id(tmp_vault: Path) -> None:
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.upsert(_person("person-a", "A"), body="v1", path=tmp_vault / "10-People/A.md")
    idx.upsert(_person("person-a", "A"), body="v2", path=tmp_vault / "10-People/A.md")
    assert idx.row_count() == 1
    idx.close()


def test_delete_removes(tmp_vault: Path) -> None:
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.upsert(_person("person-a", "A"), body="x", path=tmp_vault / "10-People/A.md")
    idx.delete("person-a")
    assert idx.row_count() == 0
    idx.close()


def test_dim_mismatch_rejected(tmp_vault: Path) -> None:
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.close()
    idx2 = Indexer(embedder=StubEmbedder(dim=16))
    with pytest.raises(IndexerError):
        idx2.open()


def test_reindex_all_walks_vault(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-a", "A"), body="alpha")
    v.write(_person("person-b", "B"), body="beta")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    assert idx.row_count() == 2
    idx.close()


def test_reindex_idempotent(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-a", "A"), body="alpha")
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(v)
    idx.reindex_all(v)
    assert idx.row_count() == 1
    idx.close()
