"""Contacts collector — reads the macOS AddressBook SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _default_db() -> Path | None:
    base = Path.home() / "Library" / "Application Support" / "AddressBook" / "Sources"
    if not base.exists():
        return None
    for src in base.iterdir():
        candidate = src / "AddressBook-v22.abcddb"
        if candidate.exists():
            return candidate
    return None


class ContactsCollector:
    name = "contacts"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path if db_path is not None else _default_db()

    async def collect(self) -> list[dict[str, Any]]:
        if self._db_path is None or not self._db_path.exists():
            return []
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            people = conn.execute("SELECT Z_PK, ZFIRSTNAME, ZLASTNAME FROM ZABCDRECORD").fetchall()
            emails = conn.execute("SELECT ZOWNER, ZADDRESS FROM ZABCDEMAILADDRESS").fetchall()
            phones = conn.execute("SELECT ZOWNER, ZFULLNUMBER FROM ZABCDPHONENUMBER").fetchall()
        finally:
            conn.close()

        emails_by_owner: dict[int, list[str]] = {}
        for owner, addr in emails:
            if addr:
                emails_by_owner.setdefault(owner, []).append(addr)
        phones_by_owner: dict[int, list[str]] = {}
        for owner, num in phones:
            if num:
                phones_by_owner.setdefault(owner, []).append(num)

        rows: list[dict[str, Any]] = []
        for pk, first, last in people:
            rows.append(
                {
                    "first_name": first or "",
                    "last_name": last or "",
                    "emails": emails_by_owner.get(pk, []),
                    "phones": phones_by_owner.get(pk, []),
                }
            )
        return rows
