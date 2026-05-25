"""Screen Time collector — reads knowledgeC.db (best-effort, often locked)."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


def _default_db() -> Path:
    return Path.home() / "Library" / "Application Support" / "Knowledge" / "knowledgeC.db"


class ScreenTimeCollector:
    name = "screen_time"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _default_db()

    async def collect(self) -> list[dict[str, Any]]:
        if not self._db_path.exists():
            return []
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return []
        try:
            rows = conn.execute(
                "SELECT ZVALUESTRING, ZSTARTDATE, ZENDDATE FROM ZOBJECT "
                "WHERE ZSTREAMNAME = '/app/usage'"
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()
        totals: dict[str, float] = defaultdict(float)
        for bundle_id, start, end in rows:
            if not bundle_id or start is None or end is None:
                continue
            totals[bundle_id] += float(end) - float(start)
        return [
            {"bundle_id": b, "seconds": int(s)}
            for b, s in sorted(totals.items(), key=lambda kv: -kv[1])
        ]
