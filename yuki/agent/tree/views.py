from dataclasses import dataclass,field
from typing import TYPE_CHECKING, Optional,Any
import json

WARNING_MESSAGE="The desktop UI services are temporarily unavailable. Please wait a few seconds and continue."
EMPTY_MESSAGE="No elements found"


def _clip(s: object, limit: int = 120) -> str:
    """Cap a free-text AX field. A single node's name/value can be an app's
    entire text content (terminal scrollback, editor document) — left whole it
    floods the agent's context (observed: a 558KB state message) and pushes
    small local models out of tool-calling into prose. Keep rows compact."""
    text = str(s)
    return text if len(text) <= limit else text[:limit] + "…"

if TYPE_CHECKING:
    from yuki.ax.core import Rect

@dataclass
class TreeState:
    status:bool=True
    root_node:Optional['TreeElementNode']=None
    dom_node:Optional['ScrollElementNode']=None
    interactive_nodes:list['TreeElementNode']|None=field(default_factory=list)
    scrollable_nodes:list['ScrollElementNode']|None=field(default_factory=list)
    dom_informative_nodes:list['TextElementNode']|None=field(default_factory=list)

    def interactive_elements_to_string(
        self,
        verbosity: str = "full",
        max_nodes: int = 25,
    ) -> str:
        parts = []
        if not self.status:
            parts.append(WARNING_MESSAGE)
            return "\n".join(parts)
        if not self.interactive_nodes and self.status:
            parts.append(EMPTY_MESSAGE)
            return "\n".join(parts)

        focused = next(
            (n for n in self.interactive_nodes
             if n.is_focused and n.canonical in {
                 "primary_input", "url_bar", "search_field", "text_input"
             }),
            None,
        )
        if focused is not None:
            value = _clip(focused.metadata.get("value") or "")
            placeholder = _clip(focused.metadata.get("placeholder") or "")
            parts.append(
                "<focused_input>\n"
                f"canonical={focused.canonical} window={focused.window_name} "
                f"role={focused.control_type} name={focused.name!r} "
                f"coords={focused.center.to_string()} "
                f"value={value!r} placeholder={placeholder!r}\n"
                "</focused_input>"
            )

        lean = verbosity == "lean"
        nodes = self.interactive_nodes
        if lean:
            # Drop the always-present desktop chrome (Dock items, menu-bar /
            # Control Centre items). It's never the target of a task — launching
            # uses app_tool, not Dock clicks — and on a busy Mac it floods the
            # context with 20-40 distractor rows that push small local models
            # (qwen2.5, llama3.2) out of tool-calling into prose replies.
            _CHROME_TYPES = {"AXDockItem", "AXMenuBarItem"}
            nodes = [n for n in self.interactive_nodes
                     if n.control_type not in _CHROME_TYPES]
            priority = {
                "url_bar": 0, "search_field": 1, "primary_input": 2,
                "text_input": 3, "submit_button": 4,
                # Stateful controls rank above plain buttons/links so the 25-node
                # cap never silently drops a toggle/checkbox/slider the user may
                # be asking about (e.g. "is Bluetooth on?").
                "toggle": 5, "checkbox": 5, "radio_button": 5,
                "slider": 6, "popup_button": 6, "tab": 6,
            }

            def _rank(n: 'TreeElementNode') -> tuple[bool, int]:
                # Focused first; then by canonical priority; a control carrying
                # explicit state (checked/selected) is treated as high-priority
                # even if its canonical tag isn't in the table above.
                has_state = any(
                    k in n.metadata for k in ("checked", "selected", "expanded")
                )
                base = priority.get(n.canonical or "", 7 if has_state else 9)
                return (not n.is_focused, base)

            nodes = sorted(nodes, key=_rank)[:max_nodes]

        header = "# id|window|control_type|canonical|name|coords|focused|metadata"
        rows = [header]
        for idx, node in enumerate(nodes):
            canonical = node.canonical or "-"
            focused_mark = "YES" if node.is_focused else "-"
            if lean:
                # Keep value/placeholder AND element STATE (checked/selected/
                # expanded/current selection). State is what lets the model see a
                # toggle's on/off position or a popup's current choice — dropping
                # it makes a checkbox indistinguishable from a button.
                _KEEP = ("value", "placeholder", "checked", "selected",
                         "expanded", "title")
                meta = {k: _clip(node.metadata[k]) for k in _KEEP
                        if k in node.metadata}
                name = _clip(node.name)
            else:
                meta = node.metadata
                name = node.name
            row = (
                f"{idx}|{node.window_name}|{node.control_type}|{canonical}|"
                f"{name}|{node.center.to_string()}|{focused_mark}|"
                f"{json.dumps(meta)}"
            )
            rows.append(row)
        parts.append("\n".join(rows))
        return "\n".join(parts)

    def scrollable_elements_to_string(self) -> str:
        parts = []
        if not self.status:
            parts.append(WARNING_MESSAGE)
            return "\n".join(parts)
        if not self.scrollable_nodes and self.status:
            parts.append(EMPTY_MESSAGE)
            return "\n".join(parts)
        # TOON-like format. Clip names: a scrollable area's name can be its
        # whole text content (same flooding risk as interactive elements).
        header = "# id|window|control_type|name|coords|metadata"
        rows = [header]
        base_index = len(self.interactive_nodes)
        for idx, node in enumerate(self.scrollable_nodes):
            row = (f"{base_index + idx}|{node.window_name}|{node.control_type}|{_clip(node.name)}|"
                   f"{node.center.to_string()}|{json.dumps(node.metadata)}")
            rows.append(row)
        parts.append("\n".join(rows))
        return "\n".join(parts)
    
@dataclass
class BoundingBox:
    left:int
    top:int
    right:int
    bottom:int
    width:int
    height:int

    @classmethod
    def from_bounding_rectangle(cls,bounding_rectangle:'Rect')->'BoundingBox':
        return cls(
            left=int(bounding_rectangle.left),
            top=int(bounding_rectangle.top),
            right=int(bounding_rectangle.right),
            bottom=int(bounding_rectangle.bottom),
            width=int(bounding_rectangle.width),
            height=int(bounding_rectangle.height)
        )

    def get_center(self)->'Center':
        return Center(x=self.left+self.width//2,y=self.top+self.height//2)

    def xywh_to_string(self):
        return f'({self.left},{self.top},{self.width},{self.height})'
    
    def xyxy_to_string(self):
        x1,y1,x2,y2=self.convert_xywh_to_xyxy()
        return f'({x1},{y1},{x2},{y2})'
    
    def convert_xywh_to_xyxy(self)->tuple[int,int,int,int]:
        x1,y1=self.left,self.top
        x2,y2=self.left+self.width,self.top+self.height
        return x1,y1,x2,y2
    
    def contains(self, other: 'BoundingBox') -> bool:
        return (
            self.left <= other.left and
            self.right >= other.right and
            self.top <= other.top and
            self.bottom >= other.bottom
        )

@dataclass
class Center:
    x:int
    y:int

    def to_string(self)->str:
        return f'({self.x},{self.y})'

@dataclass
class TreeElementNode:
    bounding_box: BoundingBox
    center: Center
    name: str=''
    control_type: str=''
    window_name: str=''
    metadata:dict[str,Any]=field(default_factory=dict)
    is_focused: bool=False
    canonical: str|None=None

    def update_from_node(self,node:'TreeElementNode'):
        self.name=node.name
        self.control_type=node.control_type
        self.window_name=node.window_name
        self.value=node.value
        self.shortcut=node.shortcut
        self.bounding_box=node.bounding_box
        self.center=node.center
        self.metadata=node.metadata

    # Legacy method kept for compatibility if needed, but not used in new format
    def to_row(self, index: int):
        return [index, self.window_name, self.control_type, self.name, self.value, self.shortcut, self.center.to_string(),self.is_focused]

@dataclass
class ScrollElementNode:
    name: str
    control_type: str
    window_name: str
    bounding_box: BoundingBox
    center: Center
    metadata:dict[str,Any]=field(default_factory=dict)

    # Legacy method kept for compatibility
    def to_row(self, index: int, base_index: int):
        return [
            base_index + index,
            self.window_name,
            self.control_type,
            self.name,
            self.center.to_string(),
            json.dumps(self.metadata)
        ]

@dataclass
class TextElementNode:
    text:str

ElementNode=TreeElementNode|ScrollElementNode|TextElementNode