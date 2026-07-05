from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional

class SharedBaseModel(BaseModel):

    model_config = ConfigDict(extra='allow')

    evaluate: Literal["success", "neutral", "fail"] = Field(
        "neutral",
        description="Assessment of the previous action's outcome: 'success' if the last action achieved its goal, 'fail' if it did not produce the expected result, 'neutral' for the first action or when the outcome is unclear"
    )
    plan: str = Field(
        "",
        description="The current step-by-step plan to satisfy the user's task, regenerated on every turn from the latest Desktop State. Mark completed steps as DONE and the active step as ACTIVE. Empty string is acceptable on the first action and on conversational tasks that need no plan. (max. 6 short lines)"
    )
    thought: str = Field(
        ...,
        description="A rigorous thinking process where you analyze the current state, potential issues, and explain why this specific action advances the active step of the plan. (max. 3 sentences)"
    )

class App(SharedBaseModel):
    mode: Literal['launch', 'resize', 'switch'] = Field(
        'launch',
        description="Operation mode: 'launch' opens the application, 'resize' adjusts the active window's size and position, 'switch' brings a specific open window into the foreground",
        examples=['launch']
    )
    name: Optional[str] = Field(
        description="Application name as it appears in the Applications folder or Dock (for launch/switch). Example: 'Safari' or 'WhatsApp'.",
        examples=['Safari', 'WhatsApp', 'Cursor'],
        default=None
    )
    loc: Optional[list[int]] = Field(
        description="Target [x, y] pixel coordinates for the window's top-left corner. Required for resize mode only.",
        examples=[[0, 0]],
        default=None
    )
    size: Optional[list[int]] = Field(
        description="Target [width, height] in pixels for the window dimensions. Required for resize mode only.",
        examples=[[1920, 1080]],
        default=None
    )

class Done(SharedBaseModel):
    answer: str = Field(
        ...,
        description="The response to deliver to the user, formatted in markdown. This is the ONLY way to communicate with the user.",
        examples=["## Task Completed\n\nThe file has been saved to Desktop.", "Hello! How can I help you today?", "I was unable to find the file. The Downloads folder is empty."]
    )

class Memory(SharedBaseModel):
    mode: Literal['view', 'read', 'write', 'delete', 'update'] = Field(
        description="Operation mode: 'view' lists all stored files, 'read' retrieves file content, 'write' creates a new file, 'update' modifies an existing file, 'delete' removes a file"
    )
    path: Optional[str] = Field(
        None,
        description="Relative file path from the .memories directory (e.g., 'notes.md', 'project/data.md'). Required for read, write, update, and delete."
    )
    content: Optional[str] = Field(
        None,
        description="Text content to write into the file. Required for 'write' mode and 'insert' operation in 'update' mode."
    )
    operation: Optional[Literal['replace', 'insert']] = Field(
        'replace',
        description="Update strategy: 'replace' finds old_str and substitutes it with new_str, 'insert' adds content at a specific line number. Only used in 'update' mode."
    )
    old_str: Optional[str] = Field(
        None,
        description="Exact string to find in the file. Required when operation='replace'."
    )
    new_str: Optional[str] = Field(
        None,
        description="Replacement string. Required when operation='replace'."
    )
    line_number: Optional[int] = Field(
        None,
        description="0-indexed line number where content will be inserted. Required when operation='insert'."
    )
    read_range: Optional[list[int]] = Field(
        None,
        description="Optional [start, end] line range for partial reads (0-indexed, end exclusive). Example: [0, 10] reads lines 0 through 9."
    )

class Click(SharedBaseModel):
    id: Optional[int] = Field(
        default=None,
        description="PREFERRED: the row id of the target element from the Interactive Elements list. The click resolves the element's live position at click time (immune to stale coordinates) and uses the accessibility press action when available.",
        examples=[3, 12]
    )
    loc: Optional[list[int]] = Field(
        default=None,
        description="Fallback: [x, y] pixel coordinates. Use ONLY when the target has no row id (e.g. clicking empty space or a spot inside a canvas).",
        examples=[[640, 360], [100, 200]]
    )
    button: Literal['left', 'right', 'middle'] = Field(
        description="Mouse button: 'left' for standard clicks and selection, 'right' for context menus, 'middle' for middle-click actions",
        default='left',
        examples=['left', 'right']
    )
    clicks: Literal[0, 1, 2] = Field(
        description="Number of clicks: 1 for single click (select, focus, press buttons), 2 for double click (open files, folders, apps), 0 for hover only (no click performed)",
        default=1,
        examples=[1, 2]
    )

class Shell(SharedBaseModel):
    mode: Literal['shell', 'osascript'] = Field(
        'shell',
        description="Execution mode: 'shell' runs a bash command in Terminal, 'osascript' executes AppleScript code via osascript.",
        examples=['shell', 'osascript']
    )
    command: str = Field(
        ...,
        description="The command or script to execute. For 'shell' mode: a bash command. For 'osascript' mode: AppleScript code.",
        examples=[
            'ls -la ~/Downloads',
            'pkill WhatsApp',
            'open -a WhatsApp',
            'sw_vers',
            'tell application "Finder" to get name of every window',
            'tell application "System Events" to get name of every process whose frontmost is true'
        ]
    )
    timeout: Optional[int] = Field(
        description="Maximum seconds to wait for command completion. Increase for long-running operations.",
        default=10,
        examples=[10, 30, 60]
    )

class Type(SharedBaseModel):
    id: Optional[int] = Field(
        default=None,
        description="PREFERRED: row id of the input field from the Interactive Elements list. Its live position is resolved at type time.",
        examples=[0, 5]
    )
    loc: Optional[list[int]] = Field(
        default=None,
        description="Fallback: [x, y] pixel coordinates of the input field. The tool clicks this location automatically before typing — do not pre-click.",
        examples=[[640, 360], [200, 150]]
    )
    text: str = Field(
        ...,
        description="The text string to type into the element",
        examples=['hello world', 'user@example.com', 'search query']
    )
    clear: bool = Field(
        description="If true, selects all existing text and replaces it. If false, appends to whatever is already in the field.",
        default=False,
        examples=[True, False]
    )
    caret_position: Literal['start', 'idle', 'end'] = Field(
        description="Where to position the text cursor before typing: 'start' moves to the beginning of the field, 'end' moves to the end, 'idle' leaves it where it is",
        default='idle',
        examples=['start', 'end', 'idle']
    )
    press_enter: bool = Field(
        description="If true, presses Enter after typing to submit the input (search, form, dialog). If false, leaves the cursor in the field.",
        default=False,
        examples=[True, False]
    )

class Scroll(SharedBaseModel):
    loc: Optional[list[int]] = Field(
        description="[x, y] pixel coordinates where scrolling occurs. If omitted, scrolls at the current cursor position.",
        default=None,
        examples=[[640, 360], [800, 400]]
    )
    type: Literal['horizontal', 'vertical'] = Field(
        description="Scroll axis: 'vertical' for up/down scrolling, 'horizontal' for left/right scrolling",
        default='vertical',
        examples=['vertical', 'horizontal']
    )
    direction: Literal['up', 'down', 'left', 'right'] = Field(
        description="Scroll direction: 'up' or 'down' for vertical, 'left' or 'right' for horizontal",
        default='down',
        examples=['down', 'up', 'right']
    )
    wheel_times: int = Field(
        description="Number of scroll increments. Each increment scrolls roughly 3-5 lines of text. Use 3-5 for moderate scrolling, 10+ for large jumps.",
        default=1,
        examples=[1, 3, 5, 10]
    )

class Move(SharedBaseModel):
    loc: list[int] = Field(
        ...,
        description="[x, y] pixel coordinates to move the mouse cursor to",
        examples=[[640, 360], [100, 100]]
    )
    drag: bool = Field(
        description="If true, holds the left mouse button and drags from the current position to the target (drag-and-drop). If false, moves the cursor without clicking (hover).",
        default=False,
        examples=[True, False]
    )

class Shortcut(SharedBaseModel):
    shortcut: str = Field(
        ...,
        description="Keyboard shortcut to press. Use '+' to combine keys for simultaneous press. Examples: 'command+c' for copy, 'command+tab' for window switch, 'enter' for confirm, 'escape' for cancel.",
        examples=['enter', 'escape', 'command+c', 'command+v', 'command+tab', 'command+shift+n']
    )

class Wait(SharedBaseModel):
    duration: int = Field(
        ...,
        description="Number of seconds to pause. Use to wait for applications to launch, pages to load, or animations to finish before the next action.",
        examples=[2, 5, 10]
    )

class Scrape(SharedBaseModel):
    url: str = Field(
        ...,
        description="URL of the webpage currently open in the browser. The tool extracts visible text content from the rendered page via the accessibility tree and returns it as markdown.",
        examples=['https://google.com', 'https://example.com/page']
    )

class AskUser(SharedBaseModel):
    question: str = Field(
        ...,
        description="The question to ask the user, phrased naturally and specifically. One question at a time.",
        examples=["You have two playlists matching 'japanese': 'Japanese Chill' and 'J-Rock Heavy'. Which one?"]
    )
    options: Optional[list[str]] = Field(
        default=None,
        description="Optional 2-4 short answer choices shown as buttons. Omit for free-text questions.",
        examples=[["Japanese Chill", "J-Rock Heavy"]]
    )

class ListAppNotes(SharedBaseModel):
    pass

class ReadAppNote(SharedBaseModel):
    bundle_id: str = Field(
        ...,
        description="Bundle id of the app whose note to read, exactly as returned by list_app_notes (e.g. 'net.whatsapp.WhatsApp', 'com.google.Chrome').",
        examples=['net.whatsapp.WhatsApp', 'com.google.Chrome', 'com.apple.Safari']
    )
