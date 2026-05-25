"""Screen Time collector — knowledgeC.db (best-effort)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.screen_time import ScreenTimeCollector


def _seed(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE ZOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            ZSTREAMNAME TEXT,
            ZVALUESTRING TEXT,
            ZSTARTDATE REAL,
            ZENDDATE REAL
        );
        INSERT INTO ZOBJECT VALUES (1, '/app/usage', 'com.apple.Safari', 100.0, 460.0);
        INSERT INTO ZOBJECT VALUES (2, '/app/usage', 'com.apple.Safari', 500.0, 800.0);
        INSERT INTO ZOBJECT VALUES (3, '/app/usage', 'com.tinyspeck.slackmacgap', 0.0, 60.0);
        INSERT INTO ZOBJECT VALUES (4, '/notification', 'irrelevant', 0.0, 1.0);
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_screen_time_aggregates(tmp_path: Path) -> None:
    db = tmp_path / "knowledgeC.db"
    _seed(db)
    rows = await ScreenTimeCollector(db_path=db).collect()
    by_id = {r["bundle_id"]: r["seconds"] for r in rows}
    assert by_id["com.apple.Safari"] == 360 + 300
    assert by_id["com.tinyspeck.slackmacgap"] == 60
    assert "irrelevant" not in by_id


@pytest.mark.asyncio
async def test_screen_time_missing_db(tmp_path: Path) -> None:
    rows = await ScreenTimeCollector(db_path=tmp_path / "no.db").collect()
    assert rows == []
