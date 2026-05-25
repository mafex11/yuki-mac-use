"""system_tool — volume, brightness, dark mode, dnd toggles."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.osa import osa
from yuki.tools.native.registry import DangerLevel, tool


@tool(name="system", danger=DangerLevel.REVERSIBLE)
async def system_tool(
    action: str,
    value: int = 0,
) -> Any:
    """Adjust system settings: set_volume, set_brightness, toggle_dark_mode, toggle_dnd."""
    if action == "set_volume":
        await osa("-e", f"set volume output volume {int(value)}")
        return {"ok": True}
    if action == "set_brightness":
        return {"ok": True, "warning": "brightness via IOKit only — see menubar app"}
    if action == "toggle_dark_mode":
        await osa(
            "-e",
            'tell application "System Events" to tell appearance preferences '
            "to set dark mode to not dark mode",
        )
        return {"ok": True}
    if action == "toggle_dnd":
        return {"ok": False, "hint": "use shortcuts_tool with a Focus shortcut"}
    raise ValueError(f"Unknown system action: {action!r}")
