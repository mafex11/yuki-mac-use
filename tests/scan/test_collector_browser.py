"""Browser collector — Safari + Chrome history aggregation by domain."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.browser import BrowserCollector


def _seed_safari(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE history_items (id INTEGER PRIMARY KEY, url TEXT, visit_count INTEGER);
        INSERT INTO history_items VALUES (1, 'https://github.com/x', 30);
        INSERT INTO history_items VALUES (2, 'https://github.com/y', 12);
        INSERT INTO history_items VALUES (3, 'https://news.ycombinator.com/', 8);
        """
    )
    conn.commit()
    conn.close()


def _seed_chrome(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, visit_count INTEGER);
        INSERT INTO urls VALUES (1, 'https://docs.python.org/x', 50);
        INSERT INTO urls VALUES (2, 'https://github.com/z', 5);
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_browser_collector_aggregates(tmp_path: Path) -> None:
    safari = tmp_path / "History.db"
    chrome = tmp_path / "History"
    _seed_safari(safari)
    _seed_chrome(chrome)
    rows = await BrowserCollector(safari_db=safari, chrome_db=chrome).collect()
    by_domain = {r["domain"]: r["visits"] for r in rows}
    assert by_domain["github.com"] == 30 + 12 + 5
    assert by_domain["docs.python.org"] == 50


@pytest.mark.asyncio
async def test_browser_collector_missing_dbs(tmp_path: Path) -> None:
    rows = await BrowserCollector(safari_db=tmp_path / "x", chrome_db=tmp_path / "y").collect()
    assert rows == []
