"""Apps collector — discovers installed .app bundles and reads Info.plist."""

from __future__ import annotations

import plistlib
from pathlib import Path
from typing import Any


class AppsCollector:
    name = "apps"

    def __init__(self, roots: list[Path] | None = None) -> None:
        if roots is None:
            roots = [Path("/Applications"), Path.home() / "Applications"]
        self._roots = roots

    async def collect(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for root in self._roots:
            if not root.exists():
                continue
            for app in root.glob("*.app"):
                plist = app / "Contents" / "Info.plist"
                if not plist.exists():
                    continue
                try:
                    data = plistlib.loads(plist.read_bytes())
                except Exception:
                    continue
                rows.append(
                    {
                        "name": data.get("CFBundleName") or app.stem,
                        "bundle_id": data.get("CFBundleIdentifier", ""),
                        "path": str(app),
                    }
                )
        return rows
