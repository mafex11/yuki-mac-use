"""Apps collector — walks .app dirs, reads Info.plist."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.scan.collectors.apps import AppsCollector


def _make_app(root: Path, name: str, bundle_id: str) -> None:
    contents = root / f"{name}.app" / "Contents"
    contents.mkdir(parents=True)
    plist = contents / "Info.plist"
    plist.write_text(
        f"""<?xml version="1.0"?>
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>{bundle_id}</string>
  <key>CFBundleName</key><string>{name}</string>
</dict>
</plist>
"""
    )


@pytest.mark.asyncio
async def test_apps_collector_walks_dirs(tmp_path: Path) -> None:
    sys_apps = tmp_path / "sys"
    user_apps = tmp_path / "user"
    sys_apps.mkdir()
    user_apps.mkdir()
    _make_app(sys_apps, "Slack", "com.tinyspeck.slackmacgap")
    _make_app(user_apps, "Vim", "org.vim.MacVim")

    rows = await AppsCollector(roots=[sys_apps, user_apps]).collect()
    names = {r["name"] for r in rows}
    assert names == {"Slack", "Vim"}
    assert any(r["bundle_id"] == "com.tinyspeck.slackmacgap" for r in rows)


@pytest.mark.asyncio
async def test_apps_collector_skips_malformed(tmp_path: Path) -> None:
    sys_apps = tmp_path / "sys"
    sys_apps.mkdir()
    bad = sys_apps / "Broken.app" / "Contents"
    bad.mkdir(parents=True)
    (bad / "Info.plist").write_text("not xml")
    _make_app(sys_apps, "Good", "com.example.good")

    rows = await AppsCollector(roots=[sys_apps]).collect()
    assert {r["name"] for r in rows} == {"Good"}


@pytest.mark.asyncio
async def test_apps_collector_missing_root(tmp_path: Path) -> None:
    rows = await AppsCollector(roots=[tmp_path / "nope"]).collect()
    assert rows == []
