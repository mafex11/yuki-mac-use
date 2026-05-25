"""Settings router — JSON KV under Application Support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from yuki.memory import paths

router = APIRouter(prefix="/settings", tags=["settings"])

ALLOWED = {
    "llm_provider",
    "llm_model",
    "embedder",
    "burst_seconds",
    "deviation_alerts_enabled",
    "wakeword_enabled",
    "hotkey",
}
DEFAULTS: dict[str, Any] = {
    "llm_provider": "anthropic",
    "llm_model": "claude-sonnet-4-6",
    "embedder": "voyage",
    "burst_seconds": 30,
    "deviation_alerts_enabled": True,
    "wakeword_enabled": False,
    "hotkey": "cmd+shift+y",
}


def _path() -> Path:
    return paths.index_db_path().parent / "settings.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return dict(DEFAULTS)
    try:
        return {**DEFAULTS, **json.loads(p.read_text())}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def _save(data: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


@router.get("")
def get_all() -> dict[str, Any]:
    return {"settings": _load()}


@router.put("")
def put(updates: dict[str, Any]) -> dict[str, Any]:
    unknown = set(updates) - ALLOWED
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown keys: {sorted(unknown)}"
        )
    current = _load()
    current.update(updates)
    _save(current)
    return {"settings": current}
