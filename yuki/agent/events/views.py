"""Agent event dataclasses."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(str, Enum):
    THOUGHT = "thought"
    PLAN = "plan"
    EVALUATE = "evaluate"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATE = "state"
    DONE = "done"
    ERROR = "error"
    ASK = "ask"          # agent is waiting for the user's answer
    PAUSED = "paused"    # user took over; agent paused
    RESUMED = "resumed"


@dataclass
class AgentEvent:
    """Generic agent event with type discriminator and data dict."""

    type: EventType
    data: dict[str, Any]
