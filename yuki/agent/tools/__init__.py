from .service import (click_tool,type_tool, app_tool, shell_tool, done_tool,
shortcut_tool, scroll_tool, move_tool,wait_tool,
scrape_tool, memory_tool, ask_user_tool,
list_app_notes, read_app_note)
from .native_bridge import build_native_agent_tools

# High-level native app tools (spotify, music, browser, calendar, ...) act in
# one deterministic AppleScript call where GUI navigation takes many fragile
# steps. files is excluded: its destructive surface (delete/move) stays behind
# the gatekeeper-guarded /tools API rather than the autonomous agent loop.
NATIVE_AGENT_TOOLS = build_native_agent_tools(exclude={"files"})

BUILTIN_TOOLS=[click_tool,type_tool, app_tool, shell_tool, done_tool,
shortcut_tool, scroll_tool, move_tool,wait_tool,
scrape_tool, memory_tool, ask_user_tool,
list_app_notes, read_app_note] + NATIVE_AGENT_TOOLS

EXPERIMENTAL_TOOLS=[]
