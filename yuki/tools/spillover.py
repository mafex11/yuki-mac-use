"""Spill oversized tool results to disk; return path + preview to the LLM.

Mirrors claude-leak/src/utils/toolResultStorage.ts. The model never sees
megabytes inline; it gets a path it can subsequently read with files_tool
or quote in a follow-up question.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _root() -> Path:
    override = os.environ.get("YUKI_BLOB_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Yuki" / "blobs"


def _serialize(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, indent=2)


def maybe_spill(value: Any, *, max_chars: int, tool_name: str) -> Any:
    """Return value unchanged if small; spill to disk + return stub if oversized."""
    serialized = _serialize(value)
    if len(serialized) <= max_chars:
        return value
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{tool_name}-{int(time.time() * 1000)}.txt"
    path.write_text(serialized, encoding="utf-8")
    preview = serialized[:200] + ("…" if len(serialized) > 200 else "")
    return {
        "spilled": True,
        "tool": tool_name,
        "path": str(path),
        "bytes": len(serialized),
        "preview": preview,
    }
