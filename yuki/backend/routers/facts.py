"""/facts — flat CRUD over the vault's personalization facts (Memory UI).

Distinct from /memory (search/read/write of arbitrary typed notes). Writing a
fact creates a free-text IdentityNote; listing spans Identity/People/Projects/
Apps so the UI shows everything Yuki knows.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from yuki.backend import appstate
from yuki.backend.runtime import get_runtime
from yuki.memory import fact_store

router = APIRouter(prefix="/facts", tags=["facts"])


class AddFact(BaseModel):
    text: str


@router.get("")
def list_facts() -> dict[str, Any]:
    rt = get_runtime()
    return {"facts": fact_store.list_facts(rt.vault)}


@router.post("")
def add_fact(req: AddFact) -> dict[str, Any]:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="empty fact text")
    rt = get_runtime()
    return dict(fact_store.add_identity_fact(rt.vault, req.text))


@router.delete("/{fact_id}")
def delete_fact(fact_id: str) -> dict[str, Any]:
    rt = get_runtime()
    if not fact_store.delete_fact(rt.vault, fact_id):
        raise HTTPException(status_code=404, detail="fact not found")
    return {"ok": True}


class FactSettings(BaseModel):
    learner_enabled: bool | None = None
    ask_before_remember: bool | None = None


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    cfg = appstate.load()
    return {
        "learner_enabled": bool(cfg.get("learner_enabled", True)),
        "ask_before_remember": bool(cfg.get("ask_before_remember", True)),
    }


@router.post("/settings")
def set_settings(req: FactSettings) -> dict[str, Any]:
    cfg = appstate.load()
    if req.learner_enabled is not None:
        cfg["learner_enabled"] = req.learner_enabled
    if req.ask_before_remember is not None:
        cfg["ask_before_remember"] = req.ask_before_remember
    appstate.save(cfg)
    return {
        "learner_enabled": bool(cfg["learner_enabled"]),
        "ask_before_remember": bool(cfg["ask_before_remember"]),
    }
