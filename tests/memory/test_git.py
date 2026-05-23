"""VaultGit — every Vault.write becomes a commit."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yuki.memory.git import VaultGit
from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault


def _person(id_: str = "person-x", name: str = "X") -> PersonNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return PersonNote(
        id=id_,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["scan"],
        name=name,
    )


@pytest.fixture
def tmp_vault_with_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Like tmp_vault but with YUKI_VAULT_GIT enabled — overrides the project default."""
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "1")
    from yuki.memory.paths import SECTIONS

    for section in SECTIONS:
        (vault / section).mkdir(parents=True, exist_ok=True)
    return vault


def test_init_creates_git_repo(tmp_vault_with_git: Path) -> None:
    vg = VaultGit(tmp_vault_with_git)
    vg.init_if_needed()
    assert (tmp_vault_with_git / ".git").is_dir()


def test_init_idempotent(tmp_vault_with_git: Path) -> None:
    vg = VaultGit(tmp_vault_with_git)
    vg.init_if_needed()
    vg.init_if_needed()
    # No raise; still a single repo.
    assert (tmp_vault_with_git / ".git").is_dir()


def test_commit_after_vault_write(tmp_vault_with_git: Path) -> None:
    v = Vault()
    v.write(_person(), body="manager")
    log = subprocess.run(
        ["git", "-C", str(tmp_vault_with_git), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "person-x" in log or "write" in log.lower()


def test_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When YUKI_VAULT_GIT=0 (the test default), no .git/ should appear."""
    vault = tmp_path / "YukiVault"
    monkeypatch.setenv("YUKI_VAULT_DIR", str(vault))
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "idx.db"))
    monkeypatch.setenv("YUKI_VAULT_GIT", "0")
    from yuki.memory.paths import SECTIONS

    for section in SECTIONS:
        (vault / section).mkdir(parents=True, exist_ok=True)
    v = Vault()
    v.write(_person(), body="x")
    assert not (vault / ".git").exists()
