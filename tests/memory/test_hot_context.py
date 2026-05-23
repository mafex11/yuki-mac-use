"""Hot context loader — concatenates 00-Identity for the system prompt."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.memory.hot_context import load_hot_context
from yuki.memory.schemas import IdentityNote, PersonNote
from yuki.memory.vault import Vault


def _identity(id_: str, name: str, body: str = "") -> IdentityNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return IdentityNote(
        id=id_,
        type="identity",
        created_at=now,
        updated_at=now,
        confidence=1.0,
        source=["scan"],
        name=name,
        body=body,
    )


def test_empty_vault_returns_empty(tmp_vault: Path) -> None:
    v = Vault()
    assert load_hot_context(v) == ""


def test_loads_identity_section(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_identity("identity-profile", "Profile"), body="Name: Sudhanshu")
    v.write(_identity("identity-prefs", "Preferences"), body="Editor: vim")
    out = load_hot_context(v)
    assert "Profile" in out
    assert "Preferences" in out
    assert "Sudhanshu" in out
    assert "Editor: vim" in out


def test_skips_other_sections(tmp_vault: Path) -> None:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    v = Vault()
    v.write(
        PersonNote(
            id="person-bob",
            type="person",
            created_at=now,
            updated_at=now,
            confidence=0.9,
            source=[],
            name="Bob",
        ),
        body="not in hot context",
    )
    assert "not in hot context" not in load_hot_context(v)


def test_max_chars_caps_output(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_identity("identity-big", "Big", body="x" * 5000), body="x" * 5000)
    out = load_hot_context(v, max_chars=500)
    assert len(out) <= 500
