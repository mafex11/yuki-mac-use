"""Triggers router — CRUD over markdown trigger notes + audit reads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from yuki.memory import frontmatter as fm
from yuki.memory import paths
from yuki.memory.schemas import parse_note
from yuki.triggers.loader import load_all

router = APIRouter(prefix="/triggers", tags=["triggers"])


class CreateRequest(BaseModel):
    note: dict[str, Any]
    body: str = ""


def _triggers_dir() -> Path:
    d = paths.vault_dir() / "30-Routines" / "triggers"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("")
def list_triggers() -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    for t in load_all():
        out.append(
            {
                "id": t.id,
                "kind": t.condition_kind,
                "fire_count": t.fire_count,
                "acceptance_rate": t.acceptance_rate,
            }
        )
    return {"triggers": out}


@router.post("")
def create(req: CreateRequest) -> dict[str, Any]:
    try:
        note = parse_note(req.note)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if note.type != "trigger":
        raise HTTPException(status_code=400, detail="must be a trigger note")
    slug = note.id.removeprefix("trigger-")
    path = _triggers_dir() / f"{slug}.md"
    fm.write_file(path, note.model_dump(mode="json"), req.body)
    return {"created": True, "id": note.id, "path": str(path)}


@router.delete("/{trigger_id}")
def delete(trigger_id: str) -> dict[str, Any]:
    for path in _triggers_dir().glob("*.md"):
        try:
            meta, _ = fm.read_file(path)
        except Exception:
            continue
        if meta.get("id") == trigger_id:
            path.unlink()
            return {"deleted": True, "id": trigger_id}
    raise HTTPException(status_code=404, detail="trigger not found")


@router.get("/audit")
def audit(date: str) -> dict[str, Any]:
    eps = paths.vault_dir() / "60-Episodes"
    path = eps / f"triggers-{date}.md"
    if not path.exists():
        return {"lines": []}
    return {"lines": path.read_text(encoding="utf-8").splitlines()}
