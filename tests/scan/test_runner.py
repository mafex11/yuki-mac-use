"""Runner — orchestrator for the four-stage scan pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuki.memory.vault import Vault
from yuki.scan import paths
from yuki.scan.runner import ScanResult, run


@pytest.mark.asyncio
async def test_runner_end_to_end_with_fakes(
    tmp_vault: Path, tmp_scan_cache: Path, tmp_home: Path
) -> None:
    raw = tmp_scan_cache / "raw"
    raw.mkdir(parents=True)
    (raw / "apps.json").write_text(
        json.dumps(
            [
                {
                    "name": "Slack",
                    "bundle_id": "com.tinyspeck.slackmacgap",
                    "path": "/x",
                }
            ]
        )
    )
    (raw / "system.json").write_text(
        json.dumps(
            [
                {
                    "macos_version": "14.4",
                    "build": "x",
                    "hostname": "mac.local",
                    "locale": "en_US",
                }
            ]
        )
    )
    (raw / "git.json").write_text(
        json.dumps(
            [
                {
                    "name": "yuki",
                    "path": "/x",
                    "last_commit": "2026-05-22T08:00:00+00:00",
                    "commit_count": 50,
                    "recent_subjects": [],
                }
            ]
        )
    )
    for empty in (
        "calendar",
        "contacts",
        "mail",
        "browser",
        "shell",
        "files",
        "screen_time",
    ):
        (raw / f"{empty}.json").write_text("[]")

    async def noop_collectors() -> None:
        return None

    with patch("yuki.scan.runner._run_collectors", side_effect=noop_collectors):
        result = await run(polish=False, force=False)

    assert isinstance(result, ScanResult)
    assert result.entity_count >= 2  # identity + slack + project
    v = Vault()
    note, _ = v.read("identity-profile")
    assert note.id == "identity-profile"
    assert paths.sentinel_path().exists()


@pytest.mark.asyncio
async def test_runner_skips_when_sentinel_exists(
    tmp_vault: Path, tmp_scan_cache: Path, tmp_home: Path
) -> None:
    paths.sentinel_path().parent.mkdir(parents=True, exist_ok=True)
    paths.sentinel_path().write_text("done")

    async def noop() -> None:
        return None

    with patch("yuki.scan.runner._run_collectors", side_effect=noop):
        result = await run(polish=False, force=False)
    assert result.skipped is True
    assert result.entity_count == 0


@pytest.mark.asyncio
async def test_runner_force_reruns(tmp_vault: Path, tmp_scan_cache: Path, tmp_home: Path) -> None:
    paths.sentinel_path().parent.mkdir(parents=True, exist_ok=True)
    paths.sentinel_path().write_text("done")
    raw = tmp_scan_cache / "raw"
    raw.mkdir(parents=True)
    for name in (
        "apps",
        "system",
        "git",
        "calendar",
        "contacts",
        "mail",
        "browser",
        "shell",
        "files",
        "screen_time",
    ):
        (raw / f"{name}.json").write_text("[]")

    async def noop() -> None:
        return None

    with patch("yuki.scan.runner._run_collectors", side_effect=noop):
        result = await run(polish=False, force=True)
    assert result.skipped is False
