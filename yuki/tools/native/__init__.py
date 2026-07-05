"""Native macOS tools — registered into yuki.tools.native.registry.REGISTRY."""

from yuki.tools.loader import load_user_tools as _load_user_tools
from yuki.tools.native import (  # noqa: F401
    browser_tool,
    calendar_tool,
    clipboard_tool,
    contacts_tool,
    files_tool,
    mail_tool,
    meeting_tool,
    messages_tool,
    music_tool,
    notes_tool,
    reminders_tool,
    screenshot_tool,
    shortcuts_tool,
    spotify_tool,
    system_tool,
    web_search_tool,
)

_load_user_tools()
