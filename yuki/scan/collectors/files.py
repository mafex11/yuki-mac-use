"""Files collector — mdfind for recently-touched files, grouped by directory."""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from typing import Any


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace")


class FilesCollector:
    name = "files"

    def __init__(self, days: int = 90) -> None:
        self._days = days

    async def collect(self) -> list[dict[str, Any]]:
        query = f"kMDItemLastUsedDate >= $time.now(-{self._days * 86400})"
        text = await _run("mdfind", query)
        counts: Counter[str] = Counter()
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            counts[os.path.dirname(line)] += 1
        return [{"directory": d, "count": n} for d, n in counts.most_common(200)]
