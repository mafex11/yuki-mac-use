"""files_tool — find/read/move/delete with path-safety guard."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool

_FORBIDDEN = (".git", "Library", "Applications")


def _allowed(path: str) -> bool:
    p = Path(path).expanduser().resolve()
    home = Path.home().resolve()
    try:
        p.relative_to(home)
    except ValueError:
        return False
    return not any(part in _FORBIDDEN for part in p.parts)


async def _mdfind(query: str) -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        "mdfind",
        query,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return [line for line in out.decode().splitlines() if line.strip()]


@tool(name="files", danger=DangerLevel.DESTRUCTIVE)
async def files_tool(
    action: str,
    query: str = "",
    path: str = "",
    dest: str = "",
) -> Any:
    """Find files via mdfind, read a text file, move, or delete (with safety)."""
    if action == "find":
        return await _mdfind(query)
    if action == "read":
        if not _allowed(path):
            return {"error": "refused: path outside home or in protected dir"}
        return Path(path).read_text(encoding="utf-8", errors="replace")
    if action == "move":
        if not (_allowed(path) and _allowed(dest)):
            return {"error": "refused: source or dest disallowed"}
        shutil.move(path, dest)
        return {"moved": True}
    if action == "delete":
        if not _allowed(path):
            return {"error": "refused: path disallowed"}
        if Path(path).is_file():
            os.remove(path)
        else:
            shutil.rmtree(path)
        return {"deleted": True}
    raise ValueError(f"Unknown files action: {action!r}")
