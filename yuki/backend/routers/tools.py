"""GET /tools — list registered native tools with danger levels."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

import yuki.tools.native  # noqa: F401 — registers native tools
from yuki.tools.native.registry import REGISTRY

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools(include_experimental: bool = False) -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": s.name,
                "danger": s.danger.value,
                "description": s.description,
                "experimental": s.experimental,
                "parameters": s.parameters,
            }
            for s in REGISTRY.values()
            if include_experimental or not s.experimental
        ]
    }
