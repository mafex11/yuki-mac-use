"""Safety router — burst-mode bridge for the menu-bar app."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from yuki.backend.runtime import get_runtime

router = APIRouter(prefix="/safety", tags=["safety"])


class BurstRequest(BaseModel):
    duration: float = Field(default=30.0, ge=1.0, le=300.0)


@router.post("/burst")
def engage(req: BurstRequest) -> dict[str, Any]:
    rt = get_runtime()
    rt.burst.engage(duration=req.duration)
    return {"active": rt.burst.is_active(), "duration": req.duration}


@router.delete("/burst")
def disengage() -> dict[str, Any]:
    rt = get_runtime()
    rt.burst.disengage()
    return {"active": rt.burst.is_active()}


@router.get("/burst")
def status() -> dict[str, Any]:
    rt = get_runtime()
    return {"active": rt.burst.is_active()}
