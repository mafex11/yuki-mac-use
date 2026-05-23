"""SQLite + sqlite-vec index over the markdown vault.

The vault is the source of truth. This index is rebuildable via reindex_all().
"""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import sqlite_vec  # type: ignore[import-untyped]

from yuki.memory import paths
from yuki.memory.embeddings import Embedder
from yuki.memory.schemas import AnyNote

if TYPE_CHECKING:
    from yuki.memory.vault import Vault


class IndexerError(Exception):
    """Raised on schema mismatch or DB-level failures."""


def _floats_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class Indexer:
    def __init__(self, embedder: Embedder, db_path: Path | None = None) -> None:
        self._embedder = embedder
        self._db_path = db_path or paths.index_db_path()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        self._init_schema(conn)
        self._verify_dim(conn)
        self._conn = conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        dim = self._embedder.dim
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT,
                body_hash TEXT,
                updated_at TEXT,
                confidence REAL,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS links (
                src_id TEXT,
                dst_id TEXT,
                PRIMARY KEY (src_id, dst_id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS note_vec USING vec0(
                id TEXT PRIMARY KEY,
                embedding FLOAT[{dim}]
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(id, title, body);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('embedding_dim', ?)",
            (str(dim),),
        )
        conn.commit()

    def _verify_dim(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT value FROM meta WHERE key = 'embedding_dim'").fetchone()
        if row is None:
            return
        stored = int(row[0])
        if stored != self._embedder.dim:
            raise IndexerError(
                f"Embedding dim mismatch: db={stored}, embedder={self._embedder.dim}. "
                "Reindex required."
            )

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise IndexerError("Indexer is not open. Call .open() first.")
        return self._conn

    def upsert(self, note: AnyNote, body: str, path: Path) -> None:
        title = getattr(note, "name", note.id)
        text = f"{title}\n\n{body}"
        vec = self._embedder.embed_one(text)
        c = self.conn
        c.execute("DELETE FROM notes WHERE id = ?", (note.id,))
        c.execute("DELETE FROM note_vec WHERE id = ?", (note.id,))
        c.execute("DELETE FROM note_fts WHERE id = ?", (note.id,))
        c.execute(
            "INSERT INTO notes(id, path, type, title, body_hash, updated_at, "
            "confidence, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note.id,
                str(path),
                note.type,
                title,
                str(hash(body)),
                note.updated_at.isoformat(),
                note.confidence,
                json.dumps(note.model_dump(mode="json")),
            ),
        )
        c.execute(
            "INSERT INTO note_vec(id, embedding) VALUES (?, ?)",
            (note.id, _floats_to_blob(vec)),
        )
        c.execute(
            "INSERT INTO note_fts(id, title, body) VALUES (?, ?, ?)",
            (note.id, title, body),
        )
        c.commit()

    def delete(self, id_: str) -> None:
        c = self.conn
        c.execute("DELETE FROM notes WHERE id = ?", (id_,))
        c.execute("DELETE FROM note_vec WHERE id = ?", (id_,))
        c.execute("DELETE FROM note_fts WHERE id = ?", (id_,))
        c.commit()

    def reindex_all(self, vault: Vault) -> None:
        c = self.conn
        c.executescript("DELETE FROM notes; DELETE FROM note_vec; DELETE FROM note_fts;")
        c.commit()
        for note, body in vault.walk():
            path = vault.resolve_wikilink(note.id)
            assert path is not None
            self.upsert(note, body, path)

    def row_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])
