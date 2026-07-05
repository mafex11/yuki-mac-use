"""Task-scoped memory retrieval for control tasks.

Complements load_hot_context (00-Identity, always injected): given the task
text, pulls possibly-relevant notes from 10-People / 20-Projects /
30-Routines / 50-Knowledge and formats them as a compact markdown block.

Deliberately excluded:
- 00-Identity — already injected via hot context.
- 40-Apps — the agent has list_app_notes/read_app_note tools.
- 60-Episodes — episode bodies are long transcripts, not trivially includable.

This runs on every control task, so it is FTS-only (no embedder / network)
and it NEVER raises — any failure logs a warning and returns "".
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from yuki.memory import paths
from yuki.memory.vault import Vault

log = logging.getLogger(__name__)

# Note types corresponding to the sections we retrieve from.
_INCLUDED_TYPES: tuple[str, ...] = ("person", "project", "routine", "knowledge")

_MAX_NOTES = 5
_SNIPPET_CHARS = 400

# Filler words that would make an OR query match everything.
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "you", "your", "with", "that", "this", "are",
        "was", "can", "could", "would", "should", "please", "from", "about",
        "have", "has", "had", "will", "just", "then", "them", "they", "she",
        "him", "her", "his", "its", "our", "out", "not", "but", "all", "any",
        "some", "how", "what", "when", "where", "who", "why", "get", "got",
        "let", "now", "new", "use", "using", "make", "made", "want", "need",
    }
)  # fmt: skip


def _fts_query(task: str) -> str:
    """Turn free-form task text into a safe FTS5 OR-query of content words."""
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", task)]
    seen: set[str] = set()
    keep: list[str] = []
    for t in tokens:
        if len(t) < 3 or t in _STOPWORDS or t in seen:
            continue
        seen.add(t)
        keep.append(t)
    return " OR ".join(f'"{t}"' for t in keep)


def _fresh_body(vault: Vault, path_str: str) -> str:
    """Re-read the note body from the vault (source of truth); "" on failure."""
    try:
        _, body = vault.read_path(Path(path_str))
        return body
    except Exception:
        return ""


def _search(db_path: Path, query: str) -> list[tuple[str, str, str]]:
    """Return (title, path, fts_body) rows for the top FTS matches."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        placeholders = ",".join("?" for _ in _INCLUDED_TYPES)
        rows = conn.execute(
            "SELECT n.title, n.path, COALESCE(note_fts.body, '') "
            "FROM note_fts JOIN notes n ON n.id = note_fts.id "
            f"WHERE note_fts MATCH ? AND n.type IN ({placeholders}) "
            "ORDER BY bm25(note_fts) LIMIT ?",
            (query, *_INCLUDED_TYPES, _MAX_NOTES),
        ).fetchall()
    finally:
        conn.close()
    return [(str(t or ""), str(p or ""), str(b or "")) for t, p, b in rows]


def retrieve_task_context(vault: Vault, task: str, max_chars: int = 2000) -> str:
    """Return a markdown block of vault notes relevant to `task`, or "".

    Never raises: this runs on every control task and a broken index must
    not block task execution. Failures are logged as warnings.
    """
    try:
        query = _fts_query(task)
        if not query:
            return ""
        db_path = paths.index_db_path()
        if not db_path.exists():
            return ""
        rows = _search(db_path, query)
        if not rows:
            return ""
        parts = ["## Possibly relevant memory"]
        for title, path_str, fts_body in rows:
            body = _fresh_body(vault, path_str) or fts_body
            snippet = body.strip()[:_SNIPPET_CHARS]
            parts.append(f"### {title}\n{snippet}")
        return "\n\n".join(parts)[:max_chars]
    except Exception:
        log.warning("task-context retrieval failed; continuing without memory", exc_info=True)
        return ""
