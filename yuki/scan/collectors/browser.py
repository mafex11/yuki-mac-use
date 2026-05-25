"""Browser history collector — top domains by visit count."""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _safari_default() -> Path:
    return Path.home() / "Library" / "Safari" / "History.db"


def _chrome_default() -> Path:
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "Google"
        / "Chrome"
        / "Default"
        / "History"
    )


def _read_safari(db: Path) -> list[tuple[str, int]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT url, visit_count FROM history_items").fetchall()
    finally:
        conn.close()


def _read_chrome(db: Path) -> list[tuple[str, int]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT url, visit_count FROM urls").fetchall()
    finally:
        conn.close()


class BrowserCollector:
    name = "browser"

    def __init__(
        self,
        safari_db: Path | None = None,
        chrome_db: Path | None = None,
    ) -> None:
        self._safari = safari_db or _safari_default()
        self._chrome = chrome_db or _chrome_default()

    async def collect(self) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        sources: list[tuple[Path, Callable[[Path], list[tuple[str, int]]]]] = [
            (self._safari, _read_safari),
            (self._chrome, _read_chrome),
        ]
        for db, reader in sources:
            if not db.exists():
                continue
            try:
                for url, visits in reader(db):
                    if not url:
                        continue
                    domain = urlparse(url).netloc
                    if domain:
                        counts[domain] += int(visits or 0)
            except sqlite3.Error:
                continue
        return [{"domain": d, "visits": n} for d, n in counts.most_common()]
