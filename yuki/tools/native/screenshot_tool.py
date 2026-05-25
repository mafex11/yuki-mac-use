"""screenshot_tool — wraps screencapture CLI."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


def _scratch_path() -> Path:
    base = Path.home() / "Library" / "Caches" / "Yuki" / "screenshots"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{int(time.time() * 1000)}.png"


async def _capture(*flags: str) -> Path:
    out = _scratch_path()
    proc = await asyncio.create_subprocess_exec(
        "screencapture",
        *flags,
        str(out),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return out


@tool(name="screenshot", danger=DangerLevel.READ_ONLY)
async def screenshot_tool(action: str) -> Any:
    """take | take_window | take_region — returns path to PNG."""
    if action == "take":
        path = await _capture("-x")
    elif action == "take_window":
        path = await _capture("-x", "-W")
    elif action == "take_region":
        path = await _capture("-i")
    else:
        raise ValueError(f"Unknown screenshot action: {action!r}")
    return {"path": str(path)}
