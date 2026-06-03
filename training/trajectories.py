"""Multi-step task trajectories for Yuki tool-call fine-tuning.

WHY THIS EXISTS
---------------
The first 1b fine-tune scored 0.20 and collapsed onto a few tools. Root cause:
the seed set (seeds.py) is almost entirely SINGLE-STEP ("open calculator" ->
app_tool, done). Augmenting it multiplies surface variety (app names, verb
phrasings) but not SEMANTIC variety — every row teaches the same intent->tool
map, so a 1b memorizes "prompt-shape -> favorite tool" instead of learning to
READ the task + screen and pick the next action.

Real Yuki tasks are multi-step. The agent is a STEP LOOP (yuki/agent/service.py):
it calls the model, gets ONE tool, executes it, observes the NEW screen, and
calls again. So a goal like "open Chrome, go to YouTube, play a trending video"
is not one row — it is a TRAJECTORY of single-tool decisions, each conditioned
on the goal + the screen at that step.

This module encodes goals as trajectories and flattens them into the same
single-decision Record shape (task, screen, tool, args) the loop trains on. The
payoff: the SAME tool appears in many different contexts (shortcut_tool for
"new tab" mid-Chrome vs "copy" mid-doc), forcing real discrimination — exactly
what the single-step seeds could not teach.

SCREEN STATE
------------
Mid-trajectory steps carry a pruned AX snapshot in `screen`, matching the lean
format from interactive_elements_to_string(verbosity="lean") used by the live
agent. Coordinates in a step's tool call (loc=[x,y]) MUST point at an element
present in that step's screen — that consistency is the lesson (find the element,
emit its coords). The `evaluate` arg ("neutral" on the first action, "success"
once a prior action landed) teaches the model to track WHERE it is in the task.
"""

from __future__ import annotations

from typing import Any, TypedDict


class Step(TypedDict):
    screen: str       # pruned AX snapshot visible at this step ("" if none)
    tool: str         # the correct next tool
    args: dict[str, Any]


# A trajectory: a natural-language goal + the ordered single-tool decisions that
# accomplish it. The goal text is REUSED verbatim as each step's `task` (the loop
# keeps the original query in context at every step), so the model learns the
# next action is conditioned on goal + current screen, not on changing phrasing.
class Trajectory(TypedDict):
    goal: str
    steps: list[Step]


def _t(thought: str, **kw: Any) -> dict[str, Any]:
    """Args dict with the thought preamble first (matches seeds.py)."""
    return {"thought": thought, **kw}


# --- Reusable pruned-AX screens (lean format: id|window|type|canonical|name|coords|focused|metadata) ---
_DESKTOP_EMPTY = ""  # nothing open / plain desktop — no interactive elements worth listing

_CHROME_NEWTAB = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Chrome|AXTextField|url_bar|Address and search bar|(640,72)|YES|{"value":""}\n'
    "1|Chrome|AXButton|reload_button|Reload|(80,72)|-|{}"
)
_YOUTUBE_HOME = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Chrome|AXTextField|search_field|Search|(700,90)|-|{"value":""}\n'
    "1|Chrome|AXLink|video_thumb|Trending: Top music video|(360,320)|-|{}\n"
    "2|Chrome|AXLink|video_thumb|Trending: Tech keynote highlights|(720,320)|-|{}\n"
    "3|Chrome|AXLink|video_thumb|Trending: Game trailer|(1080,320)|-|{}"
)
_GOOGLE_RESULTS = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Chrome|AXTextField|search_field|Search|(640,120)|YES|{"value":"weather today"}\n'
    "1|Chrome|AXLink|result_link|Weather - National Service|(300,260)|-|{}\n"
    "2|Chrome|AXLink|result_link|Local forecast 10-day|(300,360)|-|{}"
)
_NOTES_EMPTY = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Notes|AXTextArea|text_input|Note body|(700,400)|YES|{"value":""}\n'
    "1|Notes|AXButton|new_note_button|New Note|(120,60)|-|{}"
)
_TEXTEDIT_EMPTY = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|TextEdit|AXTextArea|text_input|Document|(600,360)|YES|{"value":""}'
)
_FINDER_WINDOW = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Finder|AXTextField|search_field|Search|(900,70)|-|{"value":""}\n'
    "1|Finder|AXButton|new_folder_button|New Folder|(120,70)|-|{}"
)
_SAFARI_NEWTAB = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Safari|AXTextField|url_bar|Address|(640,80)|YES|{"value":""}'
)
_SETTINGS_SEARCH = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|System Settings|AXTextField|search_field|Search|(180,90)|YES|{"value":""}'
)
_SLACK_GENERAL = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Slack|AXTextArea|text_input|Message #general|(760,820)|YES|{"value":""}\n'
    "1|Slack|AXStaticText|message|Latest: standup at 10am tomorrow|(500,600)|-|{}"
)
_SPOTIFY_SEARCH = (
    "# id|window|control_type|canonical|name|coords|focused|metadata\n"
    '0|Spotify|AXTextField|search_field|Search|(500,90)|YES|{"value":""}\n'
    "1|Spotify|AXButton|play_button|Play|(360,400)|-|{}"
)


TRAJECTORIES: list[Trajectory] = [
    # 1. Browser: launch -> navigate -> click a result
    {"goal": "open Chrome, go to YouTube, and play a trending video", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch Chrome first.", evaluate="neutral", mode="launch", name="Google Chrome")},
        {"screen": _CHROME_NEWTAB, "tool": "type_tool",
         "args": _t("Chrome is open with the address bar focused; go to YouTube.",
                    evaluate="success", loc=[640, 72], text="youtube.com", press_enter=True)},
        {"screen": _YOUTUBE_HOME, "tool": "click_tool",
         "args": _t("YouTube loaded; click the first trending video.",
                    evaluate="success", loc=[360, 320], button="left", clicks=1)},
        {"screen": "", "tool": "done_tool",
         "args": _t("The video is playing.", evaluate="success",
                    answer="I've opened YouTube and started a trending video for you.")},
    ]},

    # 2. Search the web and open a result
    {"goal": "search Google for the weather today and open the first result", "steps": [
        {"screen": _CHROME_NEWTAB, "tool": "type_tool",
         "args": _t("Type the search query into the focused address bar.",
                    evaluate="neutral", loc=[640, 72], text="weather today", press_enter=True)},
        {"screen": _GOOGLE_RESULTS, "tool": "click_tool",
         "args": _t("Results are up; open the first result.",
                    evaluate="success", loc=[300, 260], button="left", clicks=1)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Opened the top weather result.", evaluate="success",
                    answer="I searched for today's weather and opened the top result.")},
    ]},

    # 3. Copy from a doc, paste into a new TextEdit document
    {"goal": "copy the selected text and paste it into a new TextEdit document", "steps": [
        {"screen": "", "tool": "shortcut_tool",
         "args": _t("Copy the current selection.", evaluate="neutral", shortcut="command+c")},
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Open TextEdit to paste into.", evaluate="success", mode="launch", name="TextEdit")},
        {"screen": _TEXTEDIT_EMPTY, "tool": "shortcut_tool",
         "args": _t("TextEdit is open and focused; paste the copied text.",
                    evaluate="success", shortcut="command+v")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Pasted into TextEdit.", evaluate="success",
                    answer="I copied the text and pasted it into a new TextEdit document.")},
    ]},

    # 4. Make a folder then open it (shell first, then Finder)
    {"goal": "create a folder called Reports on my Desktop and open it in Finder", "steps": [
        {"screen": "", "tool": "shell_tool",
         "args": _t("Create the folder via shell.", evaluate="neutral",
                    mode="shell", command="mkdir -p ~/Desktop/Reports")},
        {"screen": "", "tool": "shell_tool",
         "args": _t("Open the new folder in Finder.", evaluate="success",
                    mode="shell", command="open ~/Desktop/Reports")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Folder created and opened.", evaluate="success",
                    answer="I created ~/Desktop/Reports and opened it in Finder.")},
    ]},

    # 5. Take a new note and type into it
    {"goal": "open Notes, make a new note, and write 'Buy groceries'", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch Notes.", evaluate="neutral", mode="launch", name="Notes")},
        {"screen": _NOTES_EMPTY, "tool": "click_tool",
         "args": _t("Click New Note to start a fresh note.",
                    evaluate="success", loc=[120, 60], button="left", clicks=1)},
        {"screen": _NOTES_EMPTY, "tool": "type_tool",
         "args": _t("Type the note content into the focused body.",
                    evaluate="success", loc=[700, 400], text="Buy groceries")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Note written.", evaluate="success",
                    answer="I created a new note that says 'Buy groceries'.")},
    ]},

    # 6. Play a song in Spotify
    {"goal": "open Spotify and play some lofi music", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch Spotify.", evaluate="neutral", mode="launch", name="Spotify")},
        {"screen": _SPOTIFY_SEARCH, "tool": "type_tool",
         "args": _t("Search for lofi in the focused search field.",
                    evaluate="success", loc=[500, 90], text="lofi beats", press_enter=True)},
        {"screen": _SPOTIFY_SEARCH, "tool": "click_tool",
         "args": _t("Press play on the top result.",
                    evaluate="success", loc=[360, 400], button="left", clicks=1)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Music is playing.", evaluate="success",
                    answer="I'm playing some lofi beats on Spotify.")},
    ]},

    # 7. Change a system setting via search
    {"goal": "open System Settings and go to the Bluetooth section", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch System Settings.", evaluate="neutral", mode="launch", name="System Settings")},
        {"screen": _SETTINGS_SEARCH, "tool": "type_tool",
         "args": _t("Search for Bluetooth in the focused search box.",
                    evaluate="success", loc=[180, 90], text="Bluetooth", press_enter=True)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Navigated to Bluetooth.", evaluate="success",
                    answer="I opened System Settings and went to Bluetooth.")},
    ]},

    # 8. Open a URL in Safari (switch context: Safari not Chrome)
    {"goal": "open Safari and go to github.com", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch Safari.", evaluate="neutral", mode="launch", name="Safari")},
        {"screen": _SAFARI_NEWTAB, "tool": "type_tool",
         "args": _t("Type the URL into the focused address bar.",
                    evaluate="success", loc=[640, 80], text="github.com", press_enter=True)},
        {"screen": "", "tool": "done_tool",
         "args": _t("GitHub is open.", evaluate="success",
                    answer="I opened Safari and navigated to github.com.")},
    ]},

    # 9. New folder via Finder UI (not shell) — teaches UI-vs-shell discrimination
    {"goal": "in Finder, make a new folder", "steps": [
        {"screen": _FINDER_WINDOW, "tool": "click_tool",
         "args": _t("Click the New Folder button in the Finder toolbar.",
                    evaluate="neutral", loc=[120, 70], button="left", clicks=1)},
        {"screen": "", "tool": "done_tool",
         "args": _t("New folder created.", evaluate="success",
                    answer="I created a new folder in the current Finder window.")},
    ]},

    # 10. Save the current document
    {"goal": "save this document", "steps": [
        {"screen": _TEXTEDIT_EMPTY, "tool": "shortcut_tool",
         "args": _t("Save with Cmd+S.", evaluate="neutral", shortcut="command+s")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Saved.", evaluate="success", answer="I've saved the document.")},
    ]},

    # 11. Switch apps then act (switch, not launch)
    {"goal": "switch to Chrome and open a new tab", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Bring Chrome to the foreground.", evaluate="neutral", mode="switch", name="Google Chrome")},
        {"screen": _CHROME_NEWTAB, "tool": "shortcut_tool",
         "args": _t("Open a new tab with Cmd+T.", evaluate="success", shortcut="command+t")},
        {"screen": "", "tool": "done_tool",
         "args": _t("New tab opened.", evaluate="success",
                    answer="I switched to Chrome and opened a new tab.")},
    ]},

    # 12. Scroll to find content then stop
    {"goal": "scroll down to see more videos on YouTube", "steps": [
        {"screen": _YOUTUBE_HOME, "tool": "scroll_tool",
         "args": _t("Scroll down the page.", evaluate="neutral", type="vertical", direction="down")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Scrolled.", evaluate="success", answer="I scrolled down to show more videos.")},
    ]},

    # 13. Wait for a load, then proceed
    {"goal": "open Mail and wait for it to finish loading", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch Mail.", evaluate="neutral", mode="launch", name="Mail")},
        {"screen": "", "tool": "wait_tool",
         "args": _t("Give Mail a moment to sync.", evaluate="success", duration=3)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Mail is ready.", evaluate="success", answer="Mail is open and finished loading.")},
    ]},

    # 14. Pure conversational (single step) — keeps done_tool well-represented in context
    {"goal": "what's the capital of Japan?", "steps": [
        {"screen": "", "tool": "done_tool",
         "args": _t("Answer directly; no desktop action.", evaluate="neutral",
                    answer="The capital of Japan is Tokyo.")},
    ]},

    # 15. Disk check then report (shell -> done, conversational outcome)
    {"goal": "how much free disk space do I have?", "steps": [
        {"screen": "", "tool": "shell_tool",
         "args": _t("Check disk usage.", evaluate="neutral", mode="shell", command="df -h /")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Report the result.", evaluate="success",
                    answer="I checked your disk usage with df -h.")},
    ]},

    # 16. Select-all then copy (two keyboard steps in a row — distinct shortcuts)
    {"goal": "select everything and copy it", "steps": [
        {"screen": _TEXTEDIT_EMPTY, "tool": "shortcut_tool",
         "args": _t("Select all with Cmd+A.", evaluate="neutral", shortcut="command+a")},
        {"screen": _TEXTEDIT_EMPTY, "tool": "shortcut_tool",
         "args": _t("Now copy the selection with Cmd+C.", evaluate="success", shortcut="command+c")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Selected and copied.", evaluate="success",
                    answer="I selected all the text and copied it.")},
    ]},

    # 17. Create a new desktop space then switch (desktop_tool, two actions)
    {"goal": "create a new desktop space and switch to it", "steps": [
        {"screen": "", "tool": "desktop_tool",
         "args": _t("Add a new virtual desktop.", evaluate="neutral", action="create")},
        {"screen": "", "tool": "done_tool",
         "args": _t("New space created.", evaluate="success",
                    answer="I created a new desktop space and moved you to it.")},
    ]},

    # 18. Search Finder for a file
    {"goal": "find my resume file in Finder", "steps": [
        {"screen": _FINDER_WINDOW, "tool": "type_tool",
         "args": _t("Type the query into the Finder search field.",
                    evaluate="neutral", loc=[900, 70], text="resume", press_enter=True)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Search running.", evaluate="success",
                    answer="I searched Finder for files named 'resume'.")},
    ]},

    # 19. Greeting (single conversational step, different surface)
    {"goal": "hey Yuki, you there?", "steps": [
        {"screen": "", "tool": "done_tool",
         "args": _t("Acknowledge presence.", evaluate="neutral",
                    answer="Yes, I'm here! What would you like to do?")},
    ]},

    # 20. Close the current window after finishing
    {"goal": "close this window", "steps": [
        {"screen": _CHROME_NEWTAB, "tool": "shortcut_tool",
         "args": _t("Close the window with Cmd+W.", evaluate="neutral", shortcut="command+w")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Window closed.", evaluate="success", answer="I closed the window.")},
    ]},

    # 21. Launch terminal and run a command (app -> shell)
    {"goal": "open Terminal and list my home directory", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch Terminal.", evaluate="neutral", mode="launch", name="Terminal")},
        {"screen": "", "tool": "shell_tool",
         "args": _t("List the home directory.", evaluate="success",
                    mode="shell", command="ls -la ~")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Listed.", evaluate="success",
                    answer="I opened Terminal and listed your home directory.")},
    ]},

    # 22. Type a message in Slack and send it
    {"goal": "send 'on my way' to the general channel in Slack", "steps": [
        {"screen": _SLACK_GENERAL, "tool": "type_tool",
         "args": _t("Type the message into the focused #general composer and send.",
                    evaluate="neutral", loc=[760, 820], text="on my way", press_enter=True)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Message sent.", evaluate="success",
                    answer="I sent 'on my way' to #general.")},
    ]},

    # 23. Open calculator and type an expression (app -> type, no screen needed for keys)
    {"goal": "open the calculator and compute 12 times 9", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Launch Calculator.", evaluate="neutral", mode="launch", name="Calculator")},
        {"screen": "", "tool": "type_tool",
         "args": _t("Type the expression into the calculator.",
                    evaluate="success", loc=[0, 0], text="12*9", press_enter=True)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Computed.", evaluate="success",
                    answer="12 times 9 is 108 — I entered it in Calculator.")},
    ]},

    # 24. Switch to Messages and read (switch -> done conversational)
    {"goal": "switch to Messages", "steps": [
        {"screen": _DESKTOP_EMPTY, "tool": "app_tool",
         "args": _t("Bring Messages to the front.", evaluate="neutral", mode="switch", name="Messages")},
        {"screen": "", "tool": "done_tool",
         "args": _t("Switched.", evaluate="success", answer="I switched to Messages.")},
    ]},

    # 25. Paste into the address bar specifically (type into focused url_bar)
    {"goal": "paste the link into the address bar and go", "steps": [
        {"screen": _CHROME_NEWTAB, "tool": "type_tool",
         "args": _t("Paste/enter the link into the focused address bar and submit.",
                    evaluate="neutral", loc=[640, 72], text="https://example.com", press_enter=True)},
        {"screen": "", "tool": "done_tool",
         "args": _t("Navigated.", evaluate="success", answer="I opened the link in the browser.")},
    ]},
]


def flatten(trajectories: list[Trajectory] = TRAJECTORIES) -> list[dict[str, Any]]:
    """Expand trajectories into single-decision Records (schema.py shape).

    Each step becomes {task=goal, screen, tool, args}. The goal is reused as the
    task for every step (matching the loop, which keeps the original query in
    context across steps), so the model learns: next action depends on goal +
    CURRENT screen, not on per-step phrasing.
    """
    rows: list[dict[str, Any]] = []
    for traj in trajectories:
        for step in traj["steps"]:
            rows.append({
                "task": traj["goal"],
                "screen": step["screen"],
                "tool": step["tool"],
                "args": dict(step["args"]),
            })
    return rows
