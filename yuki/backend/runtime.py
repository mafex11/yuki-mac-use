"""Singleton runtime — one Vault, Indexer, Gatekeeper, etc. per process."""

from __future__ import annotations

from dataclasses import dataclass

from yuki.memory.embeddings import StubEmbedder, get_embedder
from yuki.memory.indexer import Indexer
from yuki.memory.vault import Vault
from yuki.safety.burst import BurstMode
from yuki.safety.confirmer import InMemoryConfirmer
from yuki.safety.gatekeeper import Gatekeeper
from yuki.safety.trusted import TrustedRoutineRegistry


@dataclass
class Runtime:
    vault: Vault
    indexer: Indexer
    gatekeeper: Gatekeeper
    burst: BurstMode


_runtime: Runtime | None = None


def build_runtime() -> Runtime:
    try:
        embedder = get_embedder()
    except Exception:
        embedder = StubEmbedder(dim=8)
    indexer = Indexer(embedder=embedder)
    indexer.open()
    burst = BurstMode()
    return Runtime(
        vault=Vault(),
        indexer=indexer,
        gatekeeper=Gatekeeper(
            confirmer=InMemoryConfirmer(),
            trusted=TrustedRoutineRegistry(),
            burst=burst,
        ),
        burst=burst,
    )


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = build_runtime()
    return _runtime


def reset_runtime() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.indexer.close()
    _runtime = None
