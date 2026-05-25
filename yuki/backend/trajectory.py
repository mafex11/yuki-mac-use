"""Trajectory recorder — every chat turn streamed to JSONL on disk.

Borrowed from anthropic-quickstarts: persisted trajectories make agent behavior
auditable, replayable, and useful raw material for the observer daemon.
One file per conversation_id. Disable via YUKI_TRAJECTORIES=0.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def _enabled() -> bool:
    return os.environ.get("YUKI_TRAJECTORIES", "1") != "0"


def _root() -> Path:
    override = os.environ.get("YUKI_TRAJECTORY_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Yuki" / "trajectories"


_REDACT_KEYS = ("api_key", "password", "secret", "token", "authorization")


def _redact(obj: Any) -> Any:
    """Walk a dict/list and redact secret-looking keys."""
    if isinstance(obj, dict):
        return {
            k: (
                "<redacted>"
                if any(s in k.lower() for s in _REDACT_KEYS)
                else _redact(v)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


class TrajectoryRecorder:
    def __init__(self, conversation_id: str | None) -> None:
        self._conv = conversation_id or uuid4().hex[:12]

    def record(self, event: dict[str, Any]) -> None:
        if not _enabled():
            return
        event = _redact(event)
        root = _root()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{self._conv}.jsonl"
        stamped = {**event, "ts": datetime.now(UTC).isoformat()}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(stamped, default=str) + "\n")
