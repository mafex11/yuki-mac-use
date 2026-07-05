"""Task-context retrieval — relevant notes, section filter, never-raise."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.memory.embeddings import StubEmbedder
from yuki.memory.indexer import Indexer
from yuki.memory.schemas import (
    AppNote,
    IdentityNote,
    KnowledgeNote,
    PersonContact,
    PersonNote,
)
from yuki.memory.task_context import retrieve_task_context
from yuki.memory.vault import Vault

_NOW = datetime(2026, 7, 4, tzinfo=UTC)


def _person(id_: str, name: str, phone: str | None = None) -> PersonNote:
    return PersonNote(
        id=id_,
        type="person",
        created_at=_NOW,
        updated_at=_NOW,
        confidence=0.9,
        source=[],
        name=name,
        contact=PersonContact(phone=phone),
    )


def _knowledge(id_: str, name: str) -> KnowledgeNote:
    return KnowledgeNote(
        id=id_,
        type="knowledge",
        created_at=_NOW,
        updated_at=_NOW,
        confidence=0.9,
        source=[],
        name=name,
    )


def _identity(id_: str, name: str) -> IdentityNote:
    return IdentityNote(
        id=id_,
        type="identity",
        created_at=_NOW,
        updated_at=_NOW,
        confidence=1.0,
        source=[],
        name=name,
    )


def _app(id_: str, name: str, bundle_id: str) -> AppNote:
    return AppNote(
        id=id_,
        type="app",
        created_at=_NOW,
        updated_at=_NOW,
        confidence=0.9,
        source=[],
        name=name,
        bundle_id=bundle_id,
        importance="primary",
    )


def _seed_and_index(vault: Vault) -> None:
    idx = Indexer(embedder=StubEmbedder(dim=8))
    idx.open()
    idx.reindex_all(vault)
    idx.close()


def test_retrieves_person_note_for_task(tmp_vault: Path) -> None:
    v = Vault()
    v.write(
        _person("person-mom", "Mom", phone="+1-555-0100"),
        body="Mom prefers WhatsApp for chat. Phone: +1-555-0100.",
    )
    v.write(
        _knowledge("knowledge-wifi", "Home Wifi"),
        body="Home wifi SSID is YukiNet, password in 1Password.",
    )
    _seed_and_index(v)
    out = retrieve_task_context(v, "send a message to mom")
    assert "## Possibly relevant memory" in out
    assert "Mom" in out
    assert "WhatsApp" in out


def test_excludes_identity_and_app_notes(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_identity("identity-profile", "Profile"), body="safari is my favorite word")
    v.write(_app("app-safari", "Safari", "com.apple.Safari"), body="safari browser tips")
    _seed_and_index(v)
    out = retrieve_task_context(v, "open safari")
    assert "favorite word" not in out
    assert "browser tips" not in out


def test_empty_vault_returns_empty(tmp_vault: Path) -> None:
    v = Vault()
    _seed_and_index(v)
    assert retrieve_task_context(v, "send a message to mom") == ""


def test_missing_index_db_returns_empty(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-mom", "Mom"), body="Mom uses WhatsApp.")
    # No index built at all.
    assert retrieve_task_context(v, "send a message to mom") == ""


def test_broken_db_returns_empty(tmp_vault: Path) -> None:
    v = Vault()
    db = tmp_vault.parent / "index.db"
    db.write_bytes(b"this is not a sqlite database at all")
    assert retrieve_task_context(v, "send a message to mom") == ""


def test_empty_or_stopword_task_returns_empty(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-mom", "Mom"), body="Mom uses WhatsApp.")
    _seed_and_index(v)
    assert retrieve_task_context(v, "") == ""
    assert retrieve_task_context(v, "can you please") == ""


def test_max_chars_caps_output(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-mom", "Mom"), body="mom " * 500)
    v.write(_knowledge("knowledge-mom-recipes", "Mom Recipes"), body="mom recipes " * 200)
    _seed_and_index(v)
    out = retrieve_task_context(v, "call mom", max_chars=300)
    assert 0 < len(out) <= 300
