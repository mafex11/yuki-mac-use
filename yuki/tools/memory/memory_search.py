"""memory_search — hybrid retrieval over the vault."""

from __future__ import annotations

from yuki.memory.indexer import Indexer
from yuki.memory.retriever import Retriever


def memory_search(
    query: str,
    k: int = 5,
    types: list[str] | None = None,
    *,
    indexer: Indexer,
) -> list[dict[str, object]]:
    """Search the memory vault.

    Args:
        query: free-form text query.
        k: max hits to return (default 5).
        types: optional list of note types to filter to (e.g. ["person"]).
        indexer: the open Indexer (DI; agent runtime supplies one per session).

    Returns:
        List of dicts: {id, type, title, path, snippet, score}.
    """
    retriever = Retriever(indexer)
    hits = retriever.search(query, k=k, types=types)
    return [
        {
            "id": h.id,
            "type": h.type,
            "title": h.title,
            "path": h.path,
            "snippet": h.snippet,
            "score": h.score,
        }
        for h in hits
    ]
