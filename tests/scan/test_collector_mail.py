"""Mail collector — sender-frequency-only Envelope Index reader."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.mail import MailCollector


def _seed_envelope(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE addresses (ROWID INTEGER PRIMARY KEY, address TEXT);
        CREATE TABLE messages (
            ROWID INTEGER PRIMARY KEY,
            sender INTEGER,
            date_received INTEGER
        );
        INSERT INTO addresses VALUES (1, 'sarah@example.com');
        INSERT INTO addresses VALUES (2, 'newsletter@spam.example');
        INSERT INTO messages VALUES (10, 1, 1700000000);
        INSERT INTO messages VALUES (11, 1, 1700100000);
        INSERT INTO messages VALUES (12, 1, 1700200000);
        INSERT INTO messages VALUES (13, 2, 1700300000);
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_mail_collector_counts_senders(tmp_path: Path) -> None:
    db = tmp_path / "Envelope Index"
    _seed_envelope(db)
    rows = await MailCollector(db_path=db).collect()
    by_addr = {r["address"]: r for r in rows}
    assert by_addr["sarah@example.com"]["count"] == 3
    assert by_addr["newsletter@spam.example"]["count"] == 1


@pytest.mark.asyncio
async def test_mail_missing_db_returns_empty(tmp_path: Path) -> None:
    rows = await MailCollector(db_path=tmp_path / "nope").collect()
    assert rows == []
