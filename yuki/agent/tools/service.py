from yuki.agent.tools.views import Click, Type, Scroll, Move, Shortcut, Wait, Scrape, Done, Shell, Memory, App, AskUser, ListAppNotes, ReadAppNote
from yuki.agent.desktop.service import Desktop as _Desktop
from typing import Literal,Optional
from yuki.tools import Tool
from pathlib import Path
from time import sleep
import os
from yuki.memory import frontmatter as _fm
from yuki.memory import paths as _paths

# Memory scratch dir. Must NOT be cwd-relative: when the app is launched from
# Finder cwd is "/", and `mkdir /.memories` fails on the read-only system
# volume, crashing the backend at import. Anchor it in the app-support dir
# (override with YUKI_MEMORY_DIR). mkdir is best-effort so a transient failure
# never takes down the whole import.
memory_path = Path(os.environ.get("YUKI_MEMORY_DIR") or (_paths.app_support_dir() / "memories"))
try:
    memory_path.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

_SCRAPE_MAX_CHARS = 20_000

def _resolve_memory_path(path: str) -> Path:
    """Resolve a memory file path, always sandboxed within .memories directory."""
    file_path = (memory_path / path).resolve()
    if not str(file_path).startswith(str(memory_path.resolve())):
        raise ValueError(f"Path escapes the .memories directory: {path}")
    return file_path

@Tool('done_tool',model=Done)
def done_tool(answer:str,**kwargs):
    '''
    Delivers a response to the user. This is the ONLY way to communicate with the user.

    MUST be called for every type of response:
    - Task completion: summarize what was accomplished
    - Answers to questions: provide the requested information
    - Conversational replies: greetings, clarifications, explanations
    - Error reports: explain what failed and why

    The answer should be formatted in clean markdown.
    '''
    return answer

@Tool('ask_user_tool',model=AskUser)
def ask_user_tool(question:str,options:Optional[list[str]]=None,**kwargs)->str:
    '''
    Asks the user a question mid-task and waits for their reply. Use when genuinely blocked on a decision only the user can make: ambiguous targets (two matching playlists/contacts/files), missing information (which email account), or confirmation before something destructive/irreversible.

    Do NOT use for questions you can answer yourself from the Desktop State, memory, or reasonable defaults. One clear question at a time; provide 2-4 options when the answer is a choice.

    The user's answer is returned as this tool's result — continue the task with it.
    '''
    # Executed by the agent loop itself (it owns the interaction hub); the
    # registry never runs this body.
    return ''

@Tool('app_tool',model=App)
def app_tool(mode:Literal['launch','resize','switch']='launch',name:Optional[str]=None,loc:Optional[list[int]]=None,size:Optional[list[int]]=None,**kwargs)->str:
    '''
    Manages application windows: launch new apps, switch between open windows, or resize/reposition the active window.

    - launch: Opens an application by name (as it appears in /Applications or Spotlight). Also brings an already-running app to the foreground.
    - switch: Brings an already-open window to the foreground. Provide the window title from the Window Info list.
    - resize: Moves and resizes the currently active window. Provide loc=[x,y] for position and size=[w,h] for dimensions.
    '''
    desktop:_Desktop=kwargs['desktop']
    return desktop.app(mode,name,loc,size)

@Tool('memory_tool',model=Memory)
def memory_tool(mode: Literal['view','read','write','delete','update'],path: Optional[str] = None,
    content: Optional[str] = None,operation: Optional[Literal['replace', 'insert']] = 'replace',
    old_str: Optional[str] = None,new_str: Optional[str] = None,line_number: Optional[int] = None,
    read_range: Optional[list[int]] = None,**kwargs) -> str:
    '''
    Persistent file-based storage for saving and retrieving information across steps. Files are stored as markdown in the .memories directory.

    - view: List all stored memory files.
    - write: Create a new file. Requires path and content.
    - read: Retrieve file contents. Optionally use read_range=[start, end] for partial reads.
    - update: Modify an existing file. Use operation='replace' with old_str/new_str, or operation='insert' with line_number/content.
    - delete: Remove a file by path.

    Use for storing intermediate results, research findings, plans, or any data needed in later steps.
    '''
    match mode:
        case 'view':
            search_dir = (memory_path / path).resolve() if path else memory_path
            if not str(search_dir).startswith(str(memory_path.resolve())):
                return "Error: path escapes the .memories directory."
            if not search_dir.exists():
                return "No memory files found."
            files = search_dir.rglob('*.md')
            result = '\n'.join([f'{i+1}. {file.relative_to(memory_path).as_posix()}' 
                               for i, file in enumerate(files)])
            return result if result else "No memory files found."
        
        case 'write':
            if not path:
                return "Error: path is required for write mode."
            if not path.endswith('.md'):
                path += '.md'
            file_path = _resolve_memory_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding='utf-8')
            return f'{file_path.name} created in {file_path.parent.relative_to(memory_path).as_posix()}.'
        
        case 'read':
            if not path:
                return "Error: path is required for read mode."
            file_path = _resolve_memory_path(path)
            if not file_path.exists():
                return f'Error: {file_path.name} not found.'
            
            file_content = file_path.read_text(encoding='utf-8')
            
            if read_range:
                start, end = read_range
                lines = file_content.splitlines()
                
                if start < 0 or start >= len(lines):
                    return f'Error: start line {start} out of range (0-{len(lines)-1}).'
                if end < start or end > len(lines):
                    return f'Error: end line {end} out of range ({start}-{len(lines)}).'
                
                selected_lines = lines[start:end]
                return f"File: {file_path.relative_to(memory_path).as_posix()}\nLines {start}-{end-1}:\n" + '\n'.join(selected_lines)
            
            return f"File: {file_path.relative_to(memory_path).as_posix()}\nContent:\n{file_content}"
        
        case 'update':
            if not path:
                return "Error: path is required for update mode."
            file_path = _resolve_memory_path(path)
            if not file_path.exists():
                return f'Error: {file_path.name} not found. Use "write" mode to create a new file.'
            
            current_content = file_path.read_text(encoding='utf-8')
            
            match operation:
                case 'replace':
                    if not old_str or not new_str:
                        return 'Error: both old_str and new_str are required for replace operation.'
                    if old_str not in current_content:
                        return f'Error: "{old_str}" not found in file.'
                    
                    new_content = current_content.replace(old_str, new_str)
                    file_path.write_text(new_content, encoding='utf-8')
                    old_display = f'"{old_str[:50]}{"..." if len(old_str) > 50 else ""}"'
                    new_display = f'"{new_str[:50]}{"..." if len(new_str) > 50 else ""}"'
                    return f'{file_path.name} updated: replaced {old_display} with {new_display}.'
                
                case 'insert':
                    if line_number is None:
                        return 'Error: line_number is required for insert operation.'
                    if not content:
                        return 'Error: content is required for insert operation.'
                    
                    lines = current_content.splitlines(keepends=True)
                    if line_number < 0 or line_number > len(lines):
                        return f'Error: line_number {line_number} out of range (0-{len(lines)}).'
                    
                    lines.insert(line_number, content + '\n' if not content.endswith('\n') else content)
                    new_content = ''.join(lines)
                    file_path.write_text(new_content, encoding='utf-8')
                    return f'{file_path.name} updated: inserted content at line {line_number}.'
                
                case _:
                    return f'Error: Unknown operation "{operation}".'
        
        case 'delete':
            if not path:
                return "Error: path is required for delete mode."
            file_path = _resolve_memory_path(path)
            if not file_path.exists():
                return f'Error: {file_path.name} not found.'
            
            file_path.unlink()
            return f'{file_path.name} deleted from {file_path.parent.relative_to(memory_path).as_posix()}.'
        
    return "Invalid mode. Use 'view', 'read', 'write', 'update', or 'delete'."

@Tool('shell_tool',model=Shell)
def shell_tool(command: str,mode:Literal['shell','osascript']='shell',timeout:int=10,**kwargs) -> str:
    '''
    Executes a command and returns the output and exit status code.

    - shell: Runs a bash command in Terminal. Working directory is the user's HOME. Use for file operations, system queries, installations, running scripts, and any task better done via command line than GUI.
    - osascript: Executes AppleScript code. Use for advanced macOS automation such as controlling apps, manipulating windows, interacting with System Events, displaying dialogs, or querying app-specific properties.

    Check the status code in the response: 0 means success, non-zero means failure.
    '''
    desktop:_Desktop=kwargs['desktop']
    response,status=desktop.execute_command(command,mode=mode,timeout=timeout)
    return f'Response: {response}\nStatus Code: {status}'

@Tool('click_tool',model=Click)
def click_tool(id:Optional[int]=None,loc:Optional[list[int]]=None,button:Literal['left','right','middle']='left',clicks:int=1,**kwargs)->str:
    '''
    Clicks an element from the Interactive Elements list (by row id — PREFERRED) or raw pixel coordinates (fallback).

    - id=N: clicks row N from the current Desktop State. The element's live position is re-read at click time and the accessibility press action is used when available, so this works even if the UI shifted since the snapshot. ALWAYS prefer this.
    - loc=[x,y]: raw coordinate click. Only for targets with no row id (empty space, canvas areas).
    - Single left click (clicks=1): select, press, focus, follow links. Double (clicks=2): open files/folders/icons. Right: context menus. clicks=0: hover only.
    '''
    desktop:_Desktop=kwargs['desktop']
    if id is not None:
        node = desktop.node_by_display_id(id)
        if node is None:
            return (f"No element with id {id} in the current Desktop State "
                    f"(ids are per-snapshot — re-read the list). Nothing was clicked.")
        how = desktop.click_element(node, button, clicks)
        return f"Click id={id}: {how}."
    if loc is None:
        return "Provide either id (preferred) or loc. Nothing was clicked."
    x,y=loc
    desktop.click(loc,button,clicks)
    num_clicks={1:'Single',2:'Double',3:'Triple'}
    return f'{num_clicks.get(clicks)} {button} clicked at ({x},{y}).'

def _element_at(desktop:_Desktop, x:int, y:int):
    """Return the interactive node whose bounding box contains (x,y), or None.

    Used to GROUND typing: we report what the target coordinate actually is so a
    mis-aimed type (e.g. into the wrong app's chrome) surfaces honestly instead
    of returning a false 'Typed ...' success.
    """
    state = getattr(desktop, 'desktop_state', None)
    tree = getattr(state, 'tree_state', None) if state else None
    nodes = getattr(tree, 'interactive_nodes', None) or []
    for node in nodes:
        bb = node.bounding_box
        if bb.left <= x <= bb.right and bb.top <= y <= bb.bottom:
            return node
    return None


_TEXT_CANONICALS = {"url_bar", "search_field", "primary_input", "text_input"}


@Tool('type_tool',model=Type)
def type_tool(id:Optional[int]=None,loc:Optional[list[int]]=None,text:str='',clear:Literal['true','false']='false',caret_position:Literal['start','idle','end']='idle',press_enter:Literal['true','false']='false',**kwargs):
    '''
    Clicks an input field and types text into it. Do NOT pre-click with click_tool — this tool handles focusing automatically.

    - PREFER id=N (row id from the Interactive Elements list): the field's live position is resolved at type time.
    - loc=[x,y] is the fallback for fields without a row id.
    - Set clear=true to replace existing text, or clear=false to append.
    - Set press_enter=true to submit after typing (search bars, forms, dialogs).
    - Set caret_position to control where typing begins relative to existing text.

    Use for search queries, form fields, text editors, address bars, and any text input.
    '''
    desktop:_Desktop=kwargs['desktop']

    if id is not None:
        node = desktop.node_by_display_id(id)
        if node is None:
            return (f"No element with id {id} in the current Desktop State "
                    f"(ids are per-snapshot — re-read the list). Nothing was typed.")
        # Fresh geometry at type time — the field may have moved since snapshot.
        import yuki.ax as _ax
        fresh = _ax.GetRect(node.ax_element) if node.ax_element is not None else None
        if fresh is not None and fresh.width > 0 and fresh.height > 0:
            loc = [int(fresh.left + fresh.width // 2), int(fresh.top + fresh.height // 2)]
        else:
            loc = [node.center.x, node.center.y]
    if loc is None:
        return "Provide either id (preferred) or loc. Nothing was typed."
    x,y=loc

    # Ground the target BEFORE typing: what is actually at (x,y) in the last
    # observed state? A coordinate that hits no element, or a non-text element,
    # almost always means the model is typing into the wrong place (stale coords,
    # wrong app focused). Surface that honestly so it can re-focus instead of
    # silently typing into the void.
    target = desktop.node_by_display_id(id) if id is not None else _element_at(desktop, x, y)

    desktop.type(loc=loc,text=text,caret_position=caret_position,clear=clear,press_enter=press_enter)

    if target is None:
        return (f"Typed {text!r} at ({x},{y}), but NO interactive element was listed "
                f"at those coordinates in the last Desktop State. The text may have "
                f"gone nowhere or into the wrong window. Re-read the Desktop State and "
                f"confirm a text field is focused (check the <focused_input> block) "
                f"before typing again.")
    canonical = target.canonical or ""
    if canonical not in _TEXT_CANONICALS and target.control_type not in (
        "AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"
    ):
        return (f"Typed {text!r} at ({x},{y}), but the element there is "
                f"{target.control_type}/{canonical or 'untagged'} ({target.name!r}), "
                f"not a text input. If the text didn't land where you intended, find a "
                f"row whose canonical is url_bar/search_field/text_input and type there.")
    return f"Typed {text!r} into {canonical or target.control_type} ({target.name!r}) at ({x},{y})."

@Tool('scroll_tool',model=Scroll)
def scroll_tool(loc:Optional[list[int]]=None,type:Literal['horizontal','vertical']='vertical',direction:Literal['up','down','left','right']='down',wheel_times:int=1,**kwargs)->str:
    '''
    Scrolls content at the specified location or at the current cursor position.

    Each wheel increment scrolls roughly 3-5 lines of text. Use wheel_times=3-5 for moderate scrolling, 10+ for large jumps.

    Check scroll percentages in the Scrollable Elements list to gauge position before scrolling. If loc is omitted, scrolling occurs at the current cursor location.
    '''
    desktop:_Desktop=kwargs['desktop']
    response=desktop.scroll(loc,type,direction,wheel_times)
    if response:
        return response
    return f'Scrolled {type} {direction} by {wheel_times} wheel times.'

@Tool('move_tool',model=Move)
def move_tool(loc:list[int],drag:bool=False,**kwargs)->str:
    '''
    Moves the mouse cursor to a target location, or drags from the current position to the target.

    - drag=false: Hover over elements to reveal tooltips, dropdown menus, or reposition the cursor.
    - drag=true: Hold left mouse button from the current cursor position and drag to the target coordinates. Use for drag-and-drop of files, window resizing, slider adjustment, or reordering items.
    '''
    x,y=loc
    desktop:_Desktop=kwargs['desktop']
    if drag:
        desktop.drag(loc)
        return f'Dragged the selected element to ({x},{y}).'
    else:
        desktop.move(loc)
        return f'Moved the mouse pointer to ({x},{y}).'

@Tool('shortcut_tool',model=Shortcut)
def shortcut_tool(shortcut:str,**kwargs)->str:
    '''
    Presses a macOS keyboard shortcut. Use '+' to combine keys (e.g., 'cmd+c').

    Common macOS shortcuts: cmd+c (copy), cmd+v (paste), cmd+z (undo), cmd+s (save), cmd+a (select all), cmd+f (find), cmd+w (close tab/window), cmd+t (new tab), cmd+l (focus address bar), cmd+k (in-app search in many apps), cmd+tab (switch app), cmd+q (quit app), cmd+space (Spotlight), enter (confirm), escape (cancel).

    Prefer shortcuts over mouse interactions when the operation is unambiguous — they are faster and don't depend on element coordinates.
    '''
    desktop:_Desktop=kwargs['desktop']
    desktop.shortcut(shortcut)
    return f'Pressed {shortcut}.'

@Tool('wait_tool',model=Wait)
def wait_tool(duration:int,**kwargs)->str:
    '''
    Pauses for the specified number of seconds before the next action. Use to wait for applications to launch, pages to load, dialogs to appear, or animations to finish. Typical waits: 2-3s for UI transitions, 5s for app launches, 10s+ for installations or downloads.
    '''
    sleep(duration)
    return f'Waited for {duration} seconds.'

def _truncate_scrape(content: str) -> str:
    if len(content) > _SCRAPE_MAX_CHARS:
        return content[:_SCRAPE_MAX_CHARS] + f"\n\n...[truncated — {len(content) - _SCRAPE_MAX_CHARS} chars omitted. Scroll the page and scrape again to read more.]"
    return content

@Tool('scrape_tool',model=Scrape)
def scrape_tool(url:str,**kwargs)->str:
    '''
    Fetches a URL over HTTP (fresh, logged-OUT session) and returns the page text as markdown.

    NOTE: this does NOT see the page as rendered in the user's browser — no cookies, no login state, no JavaScript. For content behind a login or rendered client-side, read the "Visible Text" section of the Desktop State, or use browser_tool(action='current_text') to read the page the user actually has open.

    Use for public pages: articles, docs, search results.
    '''
    desktop:_Desktop=kwargs['desktop']
    content=_truncate_scrape(desktop.scrape(url))
    return f'URL:{url}\nContent:\n{content}'


def _first_meaningful_line(body: str, max_len: int = 140) -> str:
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        return line[:max_len]
    return ""


@Tool('list_app_notes', model=ListAppNotes)
def list_app_notes(**kwargs) -> str:
    '''
    List every app note Yuki has accumulated guidance for. Returns one line per
    app: `bundle_id  |  name  |  one-line summary`.

    Call this BEFORE controlling an unfamiliar app, or whenever the user names
    an app you haven't worked with this session. If the listing shows a
    matching note, follow up with `read_app_note(bundle_id=...)` to load the
    full guidance. Notes encode hard-won knowledge from past runs (correct
    coordinates, working shortcuts, things to avoid) — they are usually more
    reliable than guessing from the AX tree alone.
    '''
    apps_dir = _paths.vault_dir() / "40-Apps"
    if not apps_dir.exists():
        return "No 40-Apps directory found. No app guidance available yet."
    rows: list[str] = []
    for path in sorted(apps_dir.glob("*.md")):
        try:
            meta, body = _fm.read_file(path)
        except Exception:
            continue
        if meta.get("type") != "app":
            continue
        bundle = str(meta.get("bundle_id") or "").strip()
        name = str(meta.get("name") or path.stem).strip()
        if not bundle:
            continue
        summary = _first_meaningful_line(body)
        rows.append(f"{bundle}  |  {name}  |  {summary}")
    if not rows:
        return "No app notes found in 40-Apps. No guidance available yet."
    header = "# bundle_id  |  name  |  summary"
    return "\n".join([header, *rows])


@Tool('read_app_note', model=ReadAppNote)
def read_app_note(bundle_id: str, **kwargs) -> str:
    '''
    Read the full body of the 40-Apps note for the given bundle_id. Use this
    after `list_app_notes` returns a relevant entry. The body contains
    confirmed-working coordinates, sequences, shortcuts, and pitfalls for that
    specific app. Treat it as authoritative guidance — prefer it over guessing.
    '''
    apps_dir = _paths.vault_dir() / "40-Apps"
    if not apps_dir.exists():
        return f"No app note found for bundle_id={bundle_id!r} (40-Apps missing)."
    for path in apps_dir.glob("*.md"):
        try:
            meta, body = _fm.read_file(path)
        except Exception:
            continue
        if meta.get("type") == "app" and str(meta.get("bundle_id") or "") == bundle_id:
            name = str(meta.get("name") or path.stem)
            return f"# {name} ({bundle_id})\n\n{body.strip()}"
    return f"No app note found for bundle_id={bundle_id!r}."
