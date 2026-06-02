"""OllamaEmbedder conforms to the Embedder protocol (client mocked)."""
from __future__ import annotations

from yuki.memory.embeddings import OllamaEmbedder


class _FakeClient:
    def embeddings(self, model: str, prompt: str):  # noqa: ANN001
        v = float(len(prompt) % 7) + 1.0
        return {"embedding": [v, v + 1.0, v + 2.0]}


def test_embed_one_returns_vector() -> None:
    e = OllamaEmbedder(client=_FakeClient(), dim=3)
    vec = e.embed_one("hello")
    assert len(vec) == 3
    assert e.dim == 3


def test_embed_batch_matches_one() -> None:
    e = OllamaEmbedder(client=_FakeClient(), dim=3)
    batch = e.embed_batch(["a", "bb"])
    assert len(batch) == 2
    assert batch[0] == e.embed_one("a")
