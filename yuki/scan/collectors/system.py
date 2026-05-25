"""System collector — macOS version, build, locale, hostname."""

from __future__ import annotations

import asyncio
from typing import Any


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace").strip()


class SystemCollector:
    name = "system"

    async def collect(self) -> list[dict[str, Any]]:
        version = await _run("sw_vers", "-productVersion")
        build = await _run("sw_vers", "-buildVersion")
        host = await _run("hostname")
        locale = await _run("defaults", "read", "-g", "AppleLocale")
        return [
            {
                "macos_version": version,
                "build": build,
                "hostname": host,
                "locale": locale,
            }
        ]
