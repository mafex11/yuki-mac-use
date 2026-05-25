"""shortcuts_tool — list and run user Shortcuts via the shortcuts CLI."""

from __future__ import annotations

import asyncio
from typing import Any

from yuki.tools.native.registry import DangerLevel, tool


async def _run_cli(*args: str, stdin: bytes | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "shortcuts",
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(stdin)
    return (
        proc.returncode or 0,
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


@tool(name="shortcuts", danger=DangerLevel.REVERSIBLE)
async def shortcuts_tool(
    action: str,
    name: str = "",
    input_text: str = "",
) -> Any:
    """List or run macOS Shortcuts."""
    if action == "list":
        rc, out, _ = await _run_cli("list")
        if rc != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]
    if action == "run":
        rc, out, err = await _run_cli(
            "run",
            name,
            stdin=input_text.encode("utf-8") if input_text else None,
        )
        if rc != 0:
            return {"error": err.strip() or f"exit {rc}"}
        return {"output": out.strip()}
    raise ValueError(f"Unknown shortcuts action: {action!r}")
