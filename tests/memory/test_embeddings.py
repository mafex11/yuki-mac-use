"""Embedder protocol + StubEmbedder + get_embedder dispatch."""

from __future__ import annotations

import pytest

from yuki.memory.embeddings import Embedder, StubEmbedder, get_embedder


def test_stub_is_deterministic() -> None:
    e = StubEmbedder(dim=8)
    a = e.embed_one("hello world")
    b = e.embed_one("hello world")
    assert a == b
    assert len(a) == 8


def test_stub_different_inputs_differ() -> None:
    e = StubEmbedder(dim=8)
    assert e.embed_one("apple") != e.embed_one("banana")


def test_stub_batch() -> None:
    e = StubEmbedder(dim=4)
    out = e.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == 4 for v in out)


def test_get_embedder_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_EMBEDDER", "stub")
    e = get_embedder()
    assert isinstance(e, StubEmbedder)


def test_get_embedder_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_EMBEDDER", "nonsense")
    with pytest.raises(ValueError):
        get_embedder()


def test_embedder_protocol_dim() -> None:
    e: Embedder = StubEmbedder(dim=12)
    assert e.dim == 12
