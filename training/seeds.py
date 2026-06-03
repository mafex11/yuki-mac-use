"""Hand-authored seed examples for Yuki tool-call fine-tuning.

These carry SEMANTIC diversity — the correct (task-intent -> tool + args)
mappings with natural phrasing. The augmentation script (augment.py) multiplies
the MECHANICAL dimensions (swap app names, rephrase verbs, inject negatives).
Keep seeds focused on covering distinct task SHAPES and the trickier tool
distinctions a template couldn't invent.

Each seed is a training Record (see training/schema.py):
    {task, screen, tool, args}
`thought` is included on every call (training rows must teach the preamble).
For reactive tasks, `screen` holds a small pruned AX-tree the click targets.
"""

from __future__ import annotations

from typing import Any

# A compact pruned-AX snapshot used by reactive (click/type) seeds. Matches the
# lean format emitted by interactive_elements_to_string(verbosity="lean").
_SCREEN_FORM = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    "0|Form|AXButton|submit_button|Submit|(420,560)|-|{}\n"
    "1|Form|AXButton|cancel_button|Cancel|(300,560)|-|{}\n"
    '2|Form|AXTextField|primary_input|Email|(360,400)|YES|{"value":""}'
)
_SCREEN_SEARCH = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Safari|AXTextField|url_bar|Address|(640,80)|YES|{"value":""}\n'
    "1|Safari|AXButton|submit_button|Go|(900,80)|-|{}"
)


def _t(thought: str, **kw: Any) -> dict[str, Any]:
    """Build an args dict with the thought preamble first."""
    return {"thought": thought, **kw}


SEEDS: list[dict[str, Any]] = [
    # ---- app_tool: launch / switch (the most common control intent) ----
    {"task": "open calculator", "screen": "", "tool": "app_tool",
     "args": _t("Launch the Calculator app.", mode="launch", name="Calculator")},
    {"task": "switch to Safari", "screen": "", "tool": "app_tool",
     "args": _t("Bring Safari to the foreground.", mode="switch", name="Safari")},
    {"task": "open the Notes app", "screen": "", "tool": "app_tool",
     "args": _t("Launch Notes.", mode="launch", name="Notes")},
    {"task": "launch Spotify and nothing else", "screen": "", "tool": "app_tool",
     "args": _t("Open Spotify.", mode="launch", name="Spotify")},
    {"task": "I want to use the Terminal", "screen": "", "tool": "app_tool",
     "args": _t("Open Terminal.", mode="launch", name="Terminal")},

    # ---- shortcut_tool: keyboard actions (distinct from clicking) ----
    {"task": "copy the selection", "screen": "", "tool": "shortcut_tool",
     "args": _t("Copy with Cmd+C.", shortcut="command+c")},
    {"task": "paste it here", "screen": "", "tool": "shortcut_tool",
     "args": _t("Paste with Cmd+V.", shortcut="command+v")},
    {"task": "save this file", "screen": "", "tool": "shortcut_tool",
     "args": _t("Save with Cmd+S.", shortcut="command+s")},
    {"task": "undo that", "screen": "", "tool": "shortcut_tool",
     "args": _t("Undo with Cmd+Z.", shortcut="command+z")},
    {"task": "select everything", "screen": "", "tool": "shortcut_tool",
     "args": _t("Select all with Cmd+A.", shortcut="command+a")},
    {"task": "open a new tab", "screen": "", "tool": "shortcut_tool",
     "args": _t("New tab with Cmd+T.", shortcut="command+t")},
    {"task": "close this window", "screen": "", "tool": "shortcut_tool",
     "args": _t("Close with Cmd+W.", shortcut="command+w")},
    {"task": "find on this page", "screen": "", "tool": "shortcut_tool",
     "args": _t("Open find with Cmd+F.", shortcut="command+f")},

    # ---- shell_tool: filesystem / system queries (NOT app_tool) ----
    # Tricky distinction: "list Downloads" = shell ls, not opening Finder.
    {"task": "list the files in my Downloads folder", "screen": "", "tool": "shell_tool",
     "args": _t("List Downloads via shell.", mode="shell", command="ls -la ~/Downloads")},
    {"task": "how much disk space is free", "screen": "", "tool": "shell_tool",
     "args": _t("Check disk usage.", mode="shell", command="df -h /")},
    {"task": "what's my current working directory", "screen": "", "tool": "shell_tool",
     "args": _t("Print working directory.", mode="shell", command="pwd")},
    {"task": "show running processes", "screen": "", "tool": "shell_tool",
     "args": _t("List processes.", mode="shell", command="ps aux")},
    {"task": "create a folder called projects on my desktop", "screen": "", "tool": "shell_tool",
     "args": _t("Make the directory.", mode="shell", command="mkdir -p ~/Desktop/projects")},

    # ---- scroll_tool ----
    {"task": "scroll down on this page", "screen": "", "tool": "scroll_tool",
     "args": _t("Scroll down.", type="vertical", direction="down")},
    {"task": "scroll back up", "screen": "", "tool": "scroll_tool",
     "args": _t("Scroll up.", type="vertical", direction="up")},
    {"task": "scroll to the right", "screen": "", "tool": "scroll_tool",
     "args": _t("Scroll right.", type="horizontal", direction="right")},

    # ---- wait_tool ----
    {"task": "wait a few seconds for it to load", "screen": "", "tool": "wait_tool",
     "args": _t("Pause for the page to load.", duration=3)},
    {"task": "give it a moment", "screen": "", "tool": "wait_tool",
     "args": _t("Wait briefly.", duration=2)},

    # ---- type_tool + click_tool: REACTIVE (need screen state) ----
    {"task": "type my email into the field", "screen": _SCREEN_FORM, "tool": "type_tool",
     "args": _t("Type into the focused email field.", loc=[360, 400],
                text="me@example.com")},
    {"task": "click the Submit button", "screen": _SCREEN_FORM, "tool": "click_tool",
     "args": _t("Click Submit at its coordinates.", loc=[420, 560], button="left", clicks=1)},
    {"task": "press cancel", "screen": _SCREEN_FORM, "tool": "click_tool",
     "args": _t("Click the Cancel button.", loc=[300, 560], button="left", clicks=1)},
    {"task": "go to github.com", "screen": _SCREEN_SEARCH, "tool": "type_tool",
     "args": _t("Type the URL into the focused address bar and submit.",
                loc=[640, 80], text="github.com", press_enter=True)},

    # ---- done_tool: conversational / no desktop action ----
    {"task": "what is the capital of France?", "screen": "", "tool": "done_tool",
     "args": _t("Answer directly; no desktop action needed.",
                answer="The capital of France is Paris.")},
    {"task": "say hello", "screen": "", "tool": "done_tool",
     "args": _t("Greet the user.", answer="Hello! How can I help you today?")},
    {"task": "explain what RAM is in one sentence", "screen": "", "tool": "done_tool",
     "args": _t("Explain concisely; no action.",
                answer="RAM is fast, temporary memory your computer uses to hold "
                       "data it's actively working with.")},
    {"task": "thanks", "screen": "", "tool": "done_tool",
     "args": _t("Acknowledge politely.", answer="You're welcome!")},

    # ---- desktop_tool: spaces (distinct intent) ----
    {"task": "create a new desktop space", "screen": "", "tool": "desktop_tool",
     "args": _t("Add a virtual desktop.", action="create")},
    {"task": "switch to the Work desktop", "screen": "", "tool": "desktop_tool",
     "args": _t("Switch spaces.", action="switch", desktop_name="Work")},

    # ---- list_app_notes / read_app_note: vault guidance (rare, but real) ----
    {"task": "what do you know about controlling WhatsApp", "screen": "", "tool": "list_app_notes",
     "args": _t("Check stored per-app guidance.")},
]
