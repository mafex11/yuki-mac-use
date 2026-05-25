"""Memory router — wraps memory_search/read/write tools."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from yuki.backend.runtime import get_runtime
from yuki.tools.memory.memory_read import memory_read
from yuki.tools.memory.memory_search import memory_search
from yuki.tools.memory.memory_write import memory_write

router = APIRouter(prefix="/memory", tags=["memory"])


class WriteRequest(BaseModel):
    note: dict[str, Any]
    body: str = ""
    update: bool = False


@router.get("/search")
def search(query: str, k: int = 5) -> dict[str, Any]:
    rt = get_runtime()
    return {"hits": memory_search(query=query, k=k, indexer=rt.indexer)}


@router.get("/read")
def read(id_or_path: str, expand_links: int = 0) -> dict[str, Any]:
    rt = get_runtime()
    try:
        return memory_read(
            id_or_path=id_or_path, vault=rt.vault, expand_links=expand_links
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/write")
def write(req: WriteRequest) -> dict[str, Any]:
    rt = get_runtime()
    try:
        return memory_write(
            note=req.note,
            body=req.body,
            vault=rt.vault,
            indexer=rt.indexer,
            update=req.update,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
