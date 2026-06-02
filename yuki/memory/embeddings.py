"""Pluggable embedding providers.

The indexer + retriever depend only on the Embedder protocol. Switching providers
at the env level (YUKI_EMBEDDER=voyage|openai|stub) is the only intended config knob.
"""

from __future__ import annotations

import hashlib
import os
import struct
from typing import Protocol


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    def embed_one(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class StubEmbedder:
    """Deterministic, hash-based fake. For tests only."""

    def __init__(self, dim: int = 16) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Repeat hash bytes until we have enough float32 worth of data.
        needed = self._dim * 4
        buf = (h * ((needed // len(h)) + 1))[:needed]
        floats = struct.unpack(f"{self._dim}f", buf)
        # Normalize to unit-ish vector so cosine sim stays bounded.
        norm = sum(x * x for x in floats) ** 0.5 or 1.0
        return [x / norm for x in floats]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class VoyageEmbedder:
    """Production default. Requires VOYAGE_API_KEY."""

    def __init__(self, model: str = "voyage-3", dim: int = 1024) -> None:
        import voyageai

        self._client = voyageai.Client()  # type: ignore[attr-defined]
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        result = self._client.embed(texts, model=self._model, input_type="document")
        return [list(e) for e in result.embeddings]


class OpenAIEmbedder:
    """Alternate. Requires OPENAI_API_KEY."""

    def __init__(self, model: str = "text-embedding-3-small", dim: int = 1536) -> None:
        from openai import OpenAI

        self._client = OpenAI()
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


class OllamaEmbedder:
    """Local embeddings via Ollama. Works offline. Requires the embed model
    pulled (default 'nomic-embed-text'). `client` is injectable for tests."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        dim: int = 768,
        client: object | None = None,
    ) -> None:
        if client is None:
            import ollama

            client = ollama.Client()
        self._client = client
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        resp = self._client.embeddings(model=self._model, prompt=text)
        vec = resp["embedding"] if isinstance(resp, dict) else resp.embedding
        return list(vec)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


def get_embedder() -> Embedder:
    name = os.environ.get("YUKI_EMBEDDER", "voyage").lower()
    if name == "voyage":
        return VoyageEmbedder()
    if name == "openai":
        return OpenAIEmbedder()
    if name == "ollama":
        return OllamaEmbedder()
    if name == "stub":
        return StubEmbedder()
    raise ValueError(f"Unknown embedder: {name!r}. Use voyage|openai|ollama|stub.")
