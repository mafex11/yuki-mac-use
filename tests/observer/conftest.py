"""Observer-test fixtures: temp DB path so tests don't touch real index.db."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_index_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "index.db"
    monkeypatch.setenv("YUKI_INDEX_DB", str(db))
    return db
