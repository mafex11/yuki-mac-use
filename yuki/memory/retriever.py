"""Hybrid retrieval: FTS5 + vec0, merged via Reciprocal Rank Fusion."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from yuki.memory.indexer import Indexer

_RRF_K = 60  # standard constant from the original RRF paper


def _floats_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


@dataclass
class Hit:
    id: str
    type: str
    title: str
    path: str
    snippet: str
    score: float


class Retriever:
    def __init__(self, indexer: Indexer) -> None:
        self._idx = indexer

    def search(
        self,
        query: str,
        k: int = 5,
        types: list[str] | None = None,
    ) -> list[Hit]:
        if not query.strip():
            return []
        conn = self._idx.conn

        # FTS5 full-text search
        try:
            fts_rows = conn.execute(
                "SELECT id FROM note_fts WHERE note_fts MATCH ? LIMIT 50",
                (query,),
            ).fetchall()
        except Exception:
            fts_rows = []
        fts_ranked = {row[0]: rank for rank, row in enumerate(fts_rows)}

        # Vector cosine search using the indexer's embedder
        embedder = self._idx._embedder
        qvec = embedder.embed_one(query)
        vec_rows = conn.execute(
            "SELECT id FROM note_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 50",
            (_floats_to_blob(qvec),),
        ).fetchall()
        vec_ranked = {row[0]: rank for rank, row in enumerate(vec_rows)}

        # Reciprocal Rank Fusion merge
        all_ids = set(fts_ranked) | set(vec_ranked)
        scored: list[tuple[str, float]] = []
        for nid in all_ids:
            score = 0.0
            if nid in fts_ranked:
                score += 1.0 / (_RRF_K + fts_ranked[nid])
            if nid in vec_ranked:
                score += 1.0 / (_RRF_K + vec_ranked[nid])
            scored.append((nid, score))
        scored.sort(key=lambda t: t[1], reverse=True)

        hits: list[Hit] = []
        for nid, score in scored:
            row = conn.execute(
                "SELECT n.id, n.type, n.title, n.path, COALESCE(f.body, '') "
                "FROM notes n LEFT JOIN note_fts f ON f.id = n.id WHERE n.id = ?",
                (nid,),
            ).fetchone()
            if row is None:
                continue
            id_, type_, title, path, body = row
            if types and type_ not in types:
                continue
            snippet = (body or "")[:200]
            hits.append(
                Hit(
                    id=id_,
                    type=type_,
                    title=title,
                    path=path,
                    snippet=snippet,
                    score=score,
                )
            )
            if len(hits) >= k:
                break
        return hits
