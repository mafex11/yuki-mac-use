"""Markdown vault: read/write typed notes, list, walk, resolve wikilinks.

Source of truth is the filesystem. The indexer (separate module) caches metadata
for fast retrieval but every fact in the vault can be reconstructed from .md files.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from yuki.memory import frontmatter as fm
from yuki.memory import paths
from yuki.memory.git import VaultGit
from yuki.memory.schemas import AnyNote, parse_note

# type → section. Triggers live under 30-Routines/triggers.
_TYPE_TO_SECTION: dict[str, str] = {
    "identity": "00-Identity",
    "preference": "00-Identity",
    "person": "10-People",
    "project": "20-Projects",
    "routine": "30-Routines",
    "app": "40-Apps",
    "knowledge": "50-Knowledge",
    "episode": "60-Episodes",
    "trigger": "30-Routines/triggers",
}


class VaultError(Exception):
    """Raised on missing notes, write failures, or schema errors at the vault layer."""


def slugify(name: str) -> str:
    """Filesystem-safe slug; preserves capitalization for human-friendly filenames."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = nfkd.encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^\w\s-]", "", ascii_only)
    return re.sub(r"[\s_]+", "-", cleaned).strip("-")


class Vault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or paths.vault_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        for section in paths.SECTIONS:
            (self.root / section).mkdir(parents=True, exist_ok=True)
        self._git = VaultGit(self.root)
        self._git.init_if_needed()

    def _section_for(self, note: AnyNote, *, low_confidence: bool) -> Path:
        if low_confidence:
            return self.root / "90-Inbox"
        return self.root / _TYPE_TO_SECTION[note.type]

    def _filename_for(self, note: AnyNote) -> str:
        name = getattr(note, "name", note.id)
        return f"{slugify(name) or note.id}.md"

    def write(
        self,
        note: AnyNote,
        body: str,
        *,
        route_low_confidence: bool = False,
    ) -> Path:
        low = route_low_confidence and note.confidence < 0.7
        section = self._section_for(note, low_confidence=low)
        section.mkdir(parents=True, exist_ok=True)
        path = section / self._filename_for(note)
        meta = note.model_dump(mode="json")
        fm.write_file(path, meta, body)
        self._git.commit_path(path, summary=f"write({note.type}): {note.id}")
        return path

    def read(self, id_: str) -> tuple[AnyNote, str]:
        path = self.resolve_wikilink(id_)
        if path is None:
            raise VaultError(f"Note not found: {id_}")
        return self.read_path(path)

    def read_path(self, path: Path) -> tuple[AnyNote, str]:
        meta, body = fm.read_file(path)
        try:
            note = parse_note(meta)
        except Exception as e:
            raise VaultError(f"Invalid note at {path}: {e}") from e
        return note, body

    def resolve_wikilink(self, target: str) -> Path | None:
        """Resolve [[target]] — id first, then filename (case-insensitive)."""
        for path in self._iter_markdown():
            try:
                meta, _ = fm.read_file(path)
            except Exception:
                continue
            if meta.get("id") == target:
                return path
        slug_target = slugify(target).lower()
        for path in self._iter_markdown():
            if path.stem.lower() == slug_target or path.stem.lower() == target.lower():
                return path
        return None

    def list_section(self, section: str) -> list[tuple[AnyNote, str]]:
        out: list[tuple[AnyNote, str]] = []
        for path in (self.root / section).glob("*.md"):
            try:
                out.append(self.read_path(path))
            except VaultError:
                continue
        return out

    def walk(self) -> Iterator[tuple[AnyNote, str]]:
        for path in self._iter_markdown():
            try:
                yield self.read_path(path)
            except VaultError:
                continue

    def _iter_markdown(self) -> Iterator[Path]:
        yield from self.root.rglob("*.md")
