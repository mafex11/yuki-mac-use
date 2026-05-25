"""Scan router: run + status."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from yuki.scan.runner import ScanResult


def test_run_triggers_scan(client: TestClient) -> None:
    fake = AsyncMock(
        return_value=ScanResult(
            skipped=False, fact_count=10, entity_count=3, written_paths=[]
        )
    )
    with patch("yuki.backend.routers.scan.run_scan", new=fake):
        r = client.post("/scan/run", json={"polish": False, "force": False})
    assert r.status_code == 200
    assert r.json()["entity_count"] == 3


def test_status_when_sentinel_absent(
    client: TestClient, tmp_path: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("YUKI_SCAN_CACHE", str(tmp_path / "scan-cache-empty"))
    r = client.get("/scan/status")
    assert r.status_code == 200
    assert "complete" in r.json()
