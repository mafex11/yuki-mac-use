from yuki.messages import SystemMessage, HumanMessage, AIMessage, ImageMessage, ToolMessage
from yuki.agent.events import AgentEvent, Event, EventType, ConsoleEventSubscriber, FileEventSubscriber
from yuki.agent.tools import BUILTIN_TOOLS, EXPERIMENTAL_TOOLS
from yuki.agent.views import AgentResult, AgentState
from yuki.agent.registry.service import Registry
from yuki.agent.watchdog.service import WatchDog
from yuki.agent.desktop.service import Desktop
from yuki.agent.desktop.views import Browser
from yuki.agent.loop import LoopGuard
from yuki.providers.events import LLMEventType
from yuki.agent.context import Context
from yuki.agent.base import BaseAgent
from contextlib import nullcontext
from itertools import chain
from typing import Callable, Literal, TYPE_CHECKING
import logging
import time

if TYPE_CHECKING:
    from yuki.providers.base import BaseChatLLM

logger = logging.getLogger("yuki")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

_NON_TOOL_PARAMS = {"thought", "evaluate", "plan"}

# Settle delay (seconds) applied AFTER a tool runs and BEFORE the next AX-tree
# refresh, to let UI animations and focus changes propagate. Ported from
# LLM-OS windows_use/agent/service.py:546-626 settle policy. Tool names match
# yuki.agent.tools.service. Tools not listed default to 0.0s (no extra wait).
_POST_ACTION_SETTLE: dict[str, float] = {
    # Strong settle: window-level changes
    "app_tool": 1.0,           # launch/switch/resize → window animations + AX warm-up
    # Medium settle: focus + tab/window structural changes
    "shortcut_tool": 1.0,      # cmd+t / cmd+w / cmd+r — Chrome omnibox needs ~700ms
    "click_tool": 0.3,         # may navigate or open modal
    "type_tool": 0.5,          # press_enter triggers nav; allow page to start loading
    "scroll_tool": 0.2,        # content reflows
    "move_tool": 0.0,          # pure mouse move; no UI mutation
    "drag_tool": 0.3,          # drop may reorder UI
    "multi_select_tool": 0.2,
    "multi_edit_tool": 0.2,
    # No settle: explicit wait or terminal/non-UI tools
    "wait_tool": 0.0,          # already waited
    "done_tool": 0.0,          # terminal
    "shell_tool": 0.0,         # background shell, no UI mutation
    "memory_tool": 0.0,
    "scrape_tool": 0.0,
    "desktop_tool": 0.5,       # space switching
}


def _settle_for(tool_name: str) -> float:
    return _POST_ACTION_SETTLE.get(tool_name, 0.0)


class Agent(BaseAgent):
    def __init__(
        self,
        mode: Literal["flash", "normal"] = "normal",
        instructions: list[str] | None = None,
        browser: Browser = Browser.SAFARI,
        use_annotation: bool = False,
        use_accessibility: bool = True,
        use_vision: bool = False,
        llm: "BaseChatLLM" = None,
        max_consecutive_failures: int = 3,
        max_steps: int = 25,
        auto_minimize: bool = False,
        log_to_file: bool = False,
        log_to_console: bool = True,
        event_subscriber: Callable[[AgentEvent], None] | None = None,
        experimental: bool = False,
        disable_loop_detection: bool = True,
    ):
        """
        Initialize the Agent.

        Args:
            mode: "flash" for lightweight prompts, "normal" for full prompts.
            instructions: Additional instructions for the agent.
            browser: The target web browser for web-related tasks.
            use_annotation: Overlay UI element annotations on screenshots.
            use_accessibility: Use the accessibility tree. Defaults to True.
            use_vision: Provide screenshots to the LLM. Defaults to False.
            llm: The LLM instance used for decision making.
            max_consecutive_failures: Max consecutive failures before giving up.
            max_steps: Maximum steps allowed in execution.
            auto_minimize: Minimize the current window before agent proceeds.
            log_to_file: Write agent events to a log file.
            log_to_console: Show intermediate steps in the console.
            event_subscriber: Optional callback for each agent event.
            experimental: Include experimental tools.
            disable_loop_detection: Disable loop detection warnings. Defaults to True.
        """
        self.name = "MacOS Use"
        self.description = "An agent that can interact with GUI elements on macOS"
        self.mode = mode
        self.registry = Registry(
            BUILTIN_TOOLS + EXPERIMENTAL_TOOLS if experimental else BUILTIN_TOOLS
        )
        self.instructions = instructions or []
        self.browser = browser
        self.auto_minimize = auto_minimize
        self.desktop = Desktop(
            use_vision=use_vision,
            use_annotation=use_annotation,
            use_accessibility=use_accessibility,
        )
        self.state = AgentState(
            max_consecutive_failures=max_consecutive_failures,
            max_steps=max_steps,
        )
        self.watchdog = WatchDog()
        self.context = Context()
        self.llm = llm
        self._loop_guard = LoopGuard()
        self.disable_loop_detection = disable_loop_detection

        self.event = Event()
        if event_subscriber is not None:
            self.event.add_subscriber(event_subscriber)
        if log_to_console:
            self.event.add_subscriber(ConsoleEventSubscriber())
        if log_to_file:
            self.event.add_subscriber(FileEventSubscriber())

        self._cached_system_message: SystemMessage | None = None

    @property
    def system_message(self) -> SystemMessage:
        if self._cached_system_message is not None:
            return self._cached_system_message
        self._cached_system_message = self.context.system(
            mode=self.mode,
            desktop=self.desktop,
            browser=self.browser,
            max_steps=self.state.max_steps,
            instructions=self.instructions,
        )
        return self._cached_system_message

    @property
    def task_message(self) -> HumanMessage:
        return self.context.task(task=self.state.task)

    @property
    def tools(self):
        return self.registry.get_tools()

    def loop(self) -> AgentResult:
        """Run the main agent loop synchronously."""
        self.state.messages.insert(0, self.system_message)
        self.state.messages.append(self.task_message)
        consecutive_failures = 0
        self._loop_guard.reset()

        for step in range(self.state.max_steps):
            self.state.step = step

            nudge = None if self.disable_loop_detection else self._loop_guard.check()
            hard_stop = None if self.disable_loop_detection else self._loop_guard.hard_stop_reason()
            if hard_stop:
                nudge = f"{nudge}\n\n{hard_stop}" if nudge else hard_stop
            state_msg = self.context.state(
                query=self.state.task,
                step=step,
                max_steps=self.state.max_steps,
                desktop=self.desktop,
                nudge=nudge or "",
            )
            _aw = (
                self.desktop.desktop_state.active_window
                if self.desktop.desktop_state else None
            )
            active_app = (
                (_aw.name.strip() or f"<{_aw.bundle_id}>") if _aw else "Unknown"
            )

            tree = getattr(self.desktop.desktop_state, "tree_state", None)
            focused_input = None
            url_bars: list[str] = []
            search_fields: list[str] = []
            if tree and getattr(tree, "interactive_nodes", None):
                for n in tree.interactive_nodes:
                    if n.canonical == "url_bar":
                        url_bars.append(f"{n.center.to_string()} {n.window_name}")
                    elif n.canonical == "search_field":
                        search_fields.append(f"{n.center.to_string()} {n.window_name}")
                    if n.is_focused and n.canonical in {
                        "primary_input", "url_bar", "search_field", "text_input"
                    }:
                        focused_input = (
                            f"{n.canonical} @ {n.center.to_string()} "
                            f"(role={n.control_type}, name={n.name!r})"
                        )

            self.event.emit(
                AgentEvent(
                    type=EventType.STATE,
                    data={
                        "step": step,
                        "max_steps": self.state.max_steps,
                        "active_app": active_app,
                        "focused_input": focused_input,
                        "url_bars": url_bars[:3],
                        "search_fields": search_fields[:3],
                    },
                )
            )
            if nudge:
                self.event.emit(
                    AgentEvent(type=EventType.ERROR, data={"step": step, "error": f"Loop detected: {nudge}"})
                )
            self.state.messages.append(state_msg)

            self._loop_guard.record_state(self.desktop.desktop_state)

            # Reason: call LLM with retry
            message: ToolMessage | None = None
            last_error: Exception | None = None
            for attempt in range(self.state.max_consecutive_failures):
                try:
                    messages = list(chain(self.state.messages, self.state.error_messages))
                    llm_event = self.llm.invoke(messages=messages, tools=self.tools)
                    match llm_event.type:
                        case LLMEventType.TOOL_CALL:
                            message = ToolMessage(
                                id=llm_event.tool_call.id,
                                name=llm_event.tool_call.name,
                                params=llm_event.tool_call.params,
                                thinking=llm_event.thinking.content if llm_event.thinking else None,
                                thinking_signature=llm_event.thinking.signature if llm_event.thinking else None,
                            )
                            break
                        case LLMEventType.TEXT:
                            ai_message = AIMessage(content=llm_event.content)
                            human_message = HumanMessage(
                                content="Response rejected, please use the `done_tool` to respond to the user."
                            )
                            self.state.error_messages.extend([ai_message, human_message])
                            continue
                except Exception as e:
                    last_error = e
                    if attempt < self.state.max_consecutive_failures - 1:
                        wait_time = 2 ** (attempt + 1)
                        logger.error(
                            f"Failed to get response from {self.llm.provider} "
                            f"for {self.llm.model_name}.\n"
                            f"Retrying...({attempt + 1}/{self.state.max_consecutive_failures})"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to get response from {self.llm.provider} "
                            f"for {self.llm.model_name}.\n"
                            f"All {self.state.max_consecutive_failures} attempts exhausted."
                        )

            if message is None:
                error = f"Agent failed after exhausting retries: {last_error}"
                self.event.emit(
                    AgentEvent(type=EventType.ERROR, data={"step": step, "error": error})
                )
                return AgentResult(is_done=False, error=error)

            self.state.messages.pop()  # Remove the previous state message

            tool_name = message.name
            tool_params = message.params

            evaluate = tool_params.get("evaluate", "neutral")
            plan = tool_params.get("plan", "")
            thought = tool_params.get("thought", "")
            if evaluate and evaluate != "neutral":
                self.event.emit(
                    AgentEvent(type=EventType.EVALUATE, data={"step": step, "evaluate": evaluate})
                )
            if plan:
                self.event.emit(
                    AgentEvent(type=EventType.PLAN, data={"step": step, "plan": plan})
                )
            self.event.emit(
                AgentEvent(type=EventType.THOUGHT, data={"step": step, "thought": thought})
            )

            if tool_name != "done_tool":
                self.event.emit(
                    AgentEvent(
                        type=EventType.TOOL_CALL,
                        data={
                            "step": step,
                            "tool_name": tool_name,
                            "tool_params": {k: v for k, v in tool_params.items() if k not in _NON_TOOL_PARAMS},
                        },
                    )
                )

            # Act
            tool_result = self.registry.execute(tool_name=tool_name, tool_params=tool_params, desktop=self.desktop)

            self._loop_guard.record_action(tool_name, tool_params, tool_result.is_success)

            # Smart settle: let UI animations finish before the next state capture.
            # Per-tool delays are in _POST_ACTION_SETTLE.
            settle = _settle_for(tool_name) if tool_result.is_success else 0.0
            if settle > 0.0 and tool_name != "done_tool":
                time.sleep(settle)

            if tool_result.is_success:
                content = tool_result.content
                message.content = content
                self.state.messages.append(message)
            else:
                content = tool_result.error
                message.content = content
                self.state.error_messages.append(message)

            if tool_name != "done_tool":
                self.event.emit(
                    AgentEvent(
                        type=EventType.TOOL_RESULT,
                        data={
                            "step": step,
                            "tool_name": tool_name,
                            "is_success": tool_result.is_success,
                            "content": content,
                            "settle_s": settle if settle > 0.0 else None,
                        },
                    )
                )

            if not tool_result.is_success:
                consecutive_failures += 1
                if consecutive_failures >= self.state.max_consecutive_failures:
                    error = (
                        f"Agent aborted after {self.state.max_consecutive_failures} "
                        f"consecutive tool failures. Last error: {content}"
                    )
                    self.event.emit(
                        AgentEvent(type=EventType.ERROR, data={"step": step, "error": error})
                    )
                    return AgentResult(is_done=False, error=error)
            else:
                consecutive_failures = 0

            if tool_name == "done_tool":
                content = tool_params.get("answer", "")
                self.event.emit(
                    AgentEvent(type=EventType.DONE, data={"step": step, "content": content})
                )
                return AgentResult(content=content, is_done=True)

        error = f"Agent reached the maximum number of steps ({self.state.max_steps}) without completing."
        self.event.emit(
            AgentEvent(type=EventType.ERROR, data={"step": self.state.max_steps, "error": error})
        )
        return AgentResult(is_done=False, error=error)

    def invoke(self, task: str) -> AgentResult:
        self.state.reset()
        self.state.task = task
        try:
            with self.desktop.auto_minimize() if self.auto_minimize else nullcontext():
                self.watchdog.set_focus_callback(self.desktop.tree.on_focus_changed)
                with self.watchdog:
                    result = self.loop()
            return result
        except Exception as e:
            self.event.emit(
                AgentEvent(type=EventType.ERROR, data={"step": self.state.step, "error": str(e)})
            )
            raise

    async def aloop(self) -> AgentResult:
        """Run the main agent loop asynchronously."""
        import asyncio
        self.state.messages.insert(0, self.system_message)
        self.state.messages.append(self.task_message)
        consecutive_failures = 0
        self._loop_guard.reset()

        for step in range(self.state.max_steps):
            self.state.step = step

            nudge = None if self.disable_loop_detection else self._loop_guard.check()
            hard_stop = None if self.disable_loop_detection else self._loop_guard.hard_stop_reason()
            if hard_stop:
                nudge = f"{nudge}\n\n{hard_stop}" if nudge else hard_stop
            state_msg = self.context.state(
                query=self.state.task,
                step=step,
                max_steps=self.state.max_steps,
                desktop=self.desktop,
                nudge=nudge or "",
            )
            _aw = (
                self.desktop.desktop_state.active_window
                if self.desktop.desktop_state else None
            )
            active_app = (
                (_aw.name.strip() or f"<{_aw.bundle_id}>") if _aw else "Unknown"
            )

            tree = getattr(self.desktop.desktop_state, "tree_state", None)
            focused_input = None
            url_bars: list[str] = []
            search_fields: list[str] = []
            if tree and getattr(tree, "interactive_nodes", None):
                for n in tree.interactive_nodes:
                    if n.canonical == "url_bar":
                        url_bars.append(f"{n.center.to_string()} {n.window_name}")
                    elif n.canonical == "search_field":
                        search_fields.append(f"{n.center.to_string()} {n.window_name}")
                    if n.is_focused and n.canonical in {
                        "primary_input", "url_bar", "search_field", "text_input"
                    }:
                        focused_input = (
                            f"{n.canonical} @ {n.center.to_string()} "
                            f"(role={n.control_type}, name={n.name!r})"
                        )

            self.event.emit(
                AgentEvent(
                    type=EventType.STATE,
                    data={
                        "step": step,
                        "max_steps": self.state.max_steps,
                        "active_app": active_app,
                        "focused_input": focused_input,
                        "url_bars": url_bars[:3],
                        "search_fields": search_fields[:3],
                    },
                )
            )
            if nudge:
                self.event.emit(
                    AgentEvent(type=EventType.ERROR, data={"step": step, "error": f"Loop detected: {nudge}"})
                )
            self.state.messages.append(state_msg)

            self._loop_guard.record_state(self.desktop.desktop_state)

            message: ToolMessage | None = None
            last_error: Exception | None = None
            for attempt in range(self.state.max_consecutive_failures):
                try:
                    messages = list(chain(self.state.messages, self.state.error_messages))
                    llm_event = await self.llm.ainvoke(messages=messages, tools=self.tools)
                    match llm_event.type:
                        case LLMEventType.TOOL_CALL:
                            message = ToolMessage(
                                id=llm_event.tool_call.id,
                                name=llm_event.tool_call.name,
                                params=llm_event.tool_call.params,
                                thinking=llm_event.thinking.content if llm_event.thinking else None,
                                thinking_signature=llm_event.thinking.signature if llm_event.thinking else None,
                            )
                            break
                        case LLMEventType.TEXT:
                            ai_message = AIMessage(content=llm_event.content)
                            human_message = HumanMessage(
                                content="Response rejected, please use the `done_tool` to respond to the user."
                            )
                            self.state.error_messages.extend([ai_message, human_message])
                            continue
                except Exception as e:
                    last_error = e
                    if attempt < self.state.max_consecutive_failures - 1:
                        wait_time = 2 ** (attempt + 1)
                        logger.error(
                            f"Failed to get response from {self.llm.provider} "
                            f"for {self.llm.model_name}.\n"
                            f"Retrying...({attempt + 1}/{self.state.max_consecutive_failures})"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to get response from {self.llm.provider} "
                            f"for {self.llm.model_name}.\n"
                            f"All {self.state.max_consecutive_failures} attempts exhausted."
                        )

            if message is None:
                error = f"Agent failed after exhausting retries: {last_error}"
                self.event.emit(
                    AgentEvent(type=EventType.ERROR, data={"step": step, "error": error})
                )
                return AgentResult(is_done=False, error=error)

            self.state.messages.pop()

            tool_name = message.name
            tool_params = message.params

            evaluate = tool_params.get("evaluate", "neutral")
            plan = tool_params.get("plan", "")
            thought = tool_params.get("thought", "")
            if evaluate and evaluate != "neutral":
                self.event.emit(
                    AgentEvent(type=EventType.EVALUATE, data={"step": step, "evaluate": evaluate})
                )
            if plan:
                self.event.emit(
                    AgentEvent(type=EventType.PLAN, data={"step": step, "plan": plan})
                )
            self.event.emit(
                AgentEvent(type=EventType.THOUGHT, data={"step": step, "thought": thought})
            )

            if tool_name != "done_tool":
                self.event.emit(
                    AgentEvent(
                        type=EventType.TOOL_CALL,
                        data={
                            "step": step,
                            "tool_name": tool_name,
                            "tool_params": {k: v for k, v in tool_params.items() if k not in _NON_TOOL_PARAMS},
                        },
                    )
                )

            tool_result = await self.registry.aexecute(tool_name=tool_name, tool_params=tool_params, desktop=self.desktop)

            self._loop_guard.record_action(tool_name, tool_params, tool_result.is_success)

            # Smart settle: let UI animations finish before the next state capture.
            settle = _settle_for(tool_name) if tool_result.is_success else 0.0
            if settle > 0.0 and tool_name != "done_tool":
                await asyncio.sleep(settle)

            if tool_result.is_success:
                content = tool_result.content
                message.content = content
                self.state.messages.append(message)
            else:
                content = tool_result.error
                message.content = content
                self.state.error_messages.append(message)

            if tool_name != "done_tool":
                self.event.emit(
                    AgentEvent(
                        type=EventType.TOOL_RESULT,
                        data={
                            "step": step,
                            "tool_name": tool_name,
                            "is_success": tool_result.is_success,
                            "content": content,
                            "settle_s": settle if settle > 0.0 else None,
                        },
                    )
                )

            if not tool_result.is_success:
                consecutive_failures += 1
                if consecutive_failures >= self.state.max_consecutive_failures:
                    error = (
                        f"Agent aborted after {self.state.max_consecutive_failures} "
                        f"consecutive tool failures. Last error: {content}"
                    )
                    self.event.emit(
                        AgentEvent(type=EventType.ERROR, data={"step": step, "error": error})
                    )
                    return AgentResult(is_done=False, error=error)
            else:
                consecutive_failures = 0

            if tool_name == "done_tool":
                content = tool_params.get("answer", "")
                self.event.emit(
                    AgentEvent(type=EventType.DONE, data={"step": step, "content": content})
                )
                return AgentResult(content=content, is_done=True)

        error = f"Agent reached the maximum number of steps ({self.state.max_steps}) without completing."
        self.event.emit(
            AgentEvent(type=EventType.ERROR, data={"step": self.state.max_steps, "error": error})
        )
        return AgentResult(is_done=False, error=error)

    async def ainvoke(self, task: str) -> AgentResult:
        self.state.reset()
        self.state.task = task
        try:
            with self.desktop.auto_minimize() if self.auto_minimize else nullcontext():
                self.watchdog.set_focus_callback(self.desktop.tree.on_focus_changed)
                with self.watchdog:
                    result = await self.aloop()
            return result
        except Exception as e:
            self.event.emit(
                AgentEvent(type=EventType.ERROR, data={"step": self.state.step, "error": str(e)})
            )
            raise
