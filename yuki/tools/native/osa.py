"""Shared osascript helper. Always invokes via static argv — never shell."""

from __future__ import annotations

import asyncio


class OsaError(Exception):
    """Non-zero exit, timeout, or other osascript failure."""


async def _spawn(args: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "osascript",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    text = (out or err).decode("utf-8", errors="replace")
    return (proc.returncode or 0), text


async def osa(*args: str, timeout: float = 30.0) -> str:
    try:
        rc, text = await asyncio.wait_for(_spawn(list(args)), timeout=timeout)
    except TimeoutError as e:
        raise OsaError(f"osascript timed out after {timeout}s") from e
    if rc != 0:
        raise OsaError(text.strip() or f"osascript exited with {rc}")
    return text.strip()
