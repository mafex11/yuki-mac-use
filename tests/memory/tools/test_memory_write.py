"""memory_write tool — confidence-gated routing + indexer upsert."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer
from yuki.memory.vault import Vault
from yuki.tools.memory.memory_write import memory_write


@pytest.fixture
def memctx(tmp_vault: Path) -> Iterator[tuple[Vault, Indexer]]:
    v = Vault()
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    yield v, idx
    idx.close()


def _person_payload(
    id_: str = "person-sarah", name: str = "Sarah Chen", confidence: float = 0.9
) -> dict[str, object]:
    return {
        "id": id_,
        "type": "person",
        "name": name,
        "confidence": confidence,
        "source": ["scan"],
        "created_at": "2026-05-22T09:00:00+00:00",
        "updated_at": "2026-05-22T09:00:00+00:00",
    }


def test_write_creates_note_and_indexes(memctx: tuple[Vault, Indexer], tmp_vault: Path) -> None:
    v, idx = memctx
    out = memory_write(note=_person_payload(), body="manager", vault=v, indexer=idx)
    assert out["id"] == "person-sarah"
    assert out["routed_to"] == "10-People"
    assert idx.row_count() == 1


def test_write_low_confidence_routes_to_inbox(
    memctx: tuple[Vault, Indexer], tmp_vault: Path
) -> None:
    v, idx = memctx
    out = memory_write(
        note=_person_payload(confidence=0.5),
        body="maybe a manager",
        vault=v,
        indexer=idx,
    )
    assert out["routed_to"] == "90-Inbox"
    assert idx.row_count() == 1
    inbox = list((tmp_vault / "90-Inbox").glob("*.md"))
    assert len(inbox) == 1


def test_write_invalid_schema_raises(memctx: tuple[Vault, Indexer]) -> None:
    v, idx = memctx
    with pytest.raises(ValueError):
        memory_write(note={"type": "person"}, body="x", vault=v, indexer=idx)


def test_write_update_replaces(memctx: tuple[Vault, Indexer], tmp_vault: Path) -> None:
    v, idx = memctx
    memory_write(note=_person_payload(), body="v1", vault=v, indexer=idx)
    memory_write(note=_person_payload(), body="v2", vault=v, indexer=idx, update=True)
    _note, body = v.read("person-sarah")
    assert "v2" in body
    assert idx.row_count() == 1
