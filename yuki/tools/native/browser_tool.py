"""browser_tool — AppleScript wrapper around Safari + Chrome."""

from __future__ import annotations

import os
from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _which() -> str:
    return os.environ.get("YUKI_BROWSER", "Safari")


@tool(name="browser", danger=DangerLevel.REVERSIBLE)
async def browser_tool(
    action: str,
    url: str = "",
) -> Any:
    """Read current URL/text or open/close/create tabs in the user's browser."""
    app = _which()
    if action == "current_url":
        return await osa(
            "-e",
            f'tell application "{app}" to URL of current tab of front window',
        )
    if action == "current_text":
        return await osa(
            "-e",
            f'tell application "{app}" to text of document of front window',
        )
    if action == "open_url":
        await osa(
            "-e",
            f'tell application "{app}" to make new tab at end of tabs of front window '
            f'with properties {{URL:"{_esc(url)}"}}',
        )
        return {"opened": True}
    if action == "close_tab":
        await osa(
            "-e",
            f'tell application "{app}" to close current tab of front window',
        )
        return {"closed": True}
    if action == "new_tab":
        await osa(
            "-e",
            f'tell application "{app}" to make new tab at end of tabs of front window',
        )
        return {"created": True}
    raise ValueError(f"Unknown browser action: {action!r}")
