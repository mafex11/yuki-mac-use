"""Contacts collector — reads AddressBook-v22.abcddb."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from yuki.scan.collectors.contacts import ContactsCollector


def _seed_addressbook(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE ZABCDRECORD (
            Z_PK INTEGER PRIMARY KEY,
            ZFIRSTNAME TEXT, ZLASTNAME TEXT
        );
        CREATE TABLE ZABCDEMAILADDRESS (
            Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZADDRESS TEXT
        );
        CREATE TABLE ZABCDPHONENUMBER (
            Z_PK INTEGER PRIMARY KEY, ZOWNER INTEGER, ZFULLNUMBER TEXT
        );
        INSERT INTO ZABCDRECORD VALUES (1, 'Sarah', 'Chen');
        INSERT INTO ZABCDRECORD VALUES (2, 'Bob', 'Liu');
        INSERT INTO ZABCDEMAILADDRESS VALUES (10, 1, 'sarah@example.com');
        INSERT INTO ZABCDPHONENUMBER VALUES (20, 2, '555-1212');
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_contacts_collector_reads_db(tmp_path: Path) -> None:
    db = tmp_path / "AddressBook-v22.abcddb"
    _seed_addressbook(db)
    rows = await ContactsCollector(db_path=db).collect()
    by_name = {(r["first_name"], r["last_name"]): r for r in rows}
    assert by_name[("Sarah", "Chen")]["emails"] == ["sarah@example.com"]
    assert by_name[("Bob", "Liu")]["phones"] == ["555-1212"]


@pytest.mark.asyncio
async def test_contacts_missing_db_returns_empty(tmp_path: Path) -> None:
    rows = await ContactsCollector(db_path=tmp_path / "nope.db").collect()
    assert rows == []
