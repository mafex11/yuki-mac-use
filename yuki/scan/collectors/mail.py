"""Mail collector — reads sender frequency from Mail's Envelope Index SQLite.

Body content is never read. Per spec §5.2 + §11.2.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _default_db() -> Path:
    return Path.home() / "Library" / "Mail" / "V10" / "MailData" / "Envelope Index"


class MailCollector:
    name = "mail"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _default_db()

    async def collect(self) -> list[dict[str, Any]]:
        if not self._db_path.exists():
            return []
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT a.address, COUNT(m.ROWID), MAX(m.date_received) "
                "FROM messages m JOIN addresses a ON m.sender = a.ROWID "
                "GROUP BY a.address ORDER BY COUNT(m.ROWID) DESC"
            ).fetchall()
        finally:
            conn.close()
        return [{"address": addr, "count": cnt, "last_seen_unix": last} for addr, cnt, last in rows]
