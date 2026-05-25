"""Scanner paths — cache dir for raw collector output, sentinel for completion."""

from __future__ import annotations

import os
from pathlib import Path

from yuki.memory import paths as vault_paths


def cache_dir() -> Path:
    override = os.environ.get("YUKI_SCAN_CACHE")
    if override:
        return Path(override)
    return Path(os.environ["HOME"]) / "Library" / "Caches" / "Yuki" / "scan"


def raw_path(collector: str) -> Path:
    return cache_dir() / "raw" / f"{collector}.json"


def sentinel_path() -> Path:
    return vault_paths.vault_dir() / ".scan_complete"
