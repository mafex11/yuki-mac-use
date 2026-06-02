# yuki/agent/toolrag.py
"""Tool RAG: select the few task-relevant tools to show the model.

Showing all 16 tools every step overwhelms small models. We embed each tool's
description once, then per task return the top-K by cosine similarity plus an
always-include core set so essentials are never filtered out. Degrades to "all
tools" if embedding fails — it can never block a task.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yuki.memory.embeddings import Embedder
    from yuki.tools import Tool

log = logging.getLogger("yuki")

# Essentials that must always be available regardless of similarity.
_CORE = ("done_tool", "app_tool", "shell_tool")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class ToolSelector:
    def __init__(
        self,
        tools: list["Tool"],
        embedder: "Embedder",
        top_k: int = 5,
    ) -> None:
        self._tools = tools
        self._by_name = {t.name: t for t in tools}
        self._embedder = embedder
        self._top_k = top_k
        self._vectors: dict[str, list[float]] | None = None

    def _ensure_index(self) -> bool:
        """Embed tool descriptions once. Returns False if embedding is unavailable."""
        if self._vectors is not None:
            return True
        try:
            texts = [f"{t.name}. {t.description or ''}" for t in self._tools]
            vecs = self._embedder.embed_batch(texts)
            self._vectors = {t.name: v for t, v in zip(self._tools, vecs)}
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("ToolRAG indexing failed (%s); using all tools", type(e).__name__)
            self._vectors = None
            return False

    def select(self, task: str) -> list["Tool"]:
        if not task.strip():
            return self._core_only()
        if not self._ensure_index():
            return list(self._tools)  # embedding unavailable → don't block
        try:
            q = self._embedder.embed_one(task)
        except Exception as e:  # noqa: BLE001
            log.warning("ToolRAG query embed failed (%s); using all tools", type(e).__name__)
            return list(self._tools)

        ranked = sorted(
            self._tools,
            key=lambda t: _cosine(q, self._vectors[t.name]),  # type: ignore[index]
            reverse=True,
        )
        names = {t.name for t in ranked[: self._top_k]}
        names.update(n for n in _CORE if n in self._by_name)
        # Preserve original tool order for determinism.
        return [t for t in self._tools if t.name in names]

    def _core_only(self) -> list["Tool"]:
        return [self._by_name[n] for n in _CORE if n in self._by_name]
