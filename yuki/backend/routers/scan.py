"""Scan router — kicks off onboarding scan + reports status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from yuki.scan import paths as scan_paths
from yuki.scan.runner import run as run_scan

router = APIRouter(prefix="/scan", tags=["scan"])


class RunRequest(BaseModel):
    polish: bool = False
    force: bool = False


@router.post("/run")
async def post_run(req: RunRequest) -> dict[str, Any]:
    result = await run_scan(polish=req.polish, force=req.force)
    return {
        "skipped": result.skipped,
        "fact_count": result.fact_count,
        "entity_count": result.entity_count,
        "written_paths": result.written_paths,
    }


@router.get("/status")
def get_status() -> dict[str, Any]:
    return {"complete": scan_paths.sentinel_path().exists()}
