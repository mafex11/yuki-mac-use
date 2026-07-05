from yuki.messages import SystemMessage, HumanMessage, AIMessage, ImageMessage, ToolMessage
from yuki.agent.events import AgentEvent, Event, EventType, ConsoleEventSubscriber, FileEventSubscriber
from yuki.agent.tools import BUILTIN_TOOLS, EXPERIMENTAL_TOOLS
from yuki.agent.views import AgentResult, AgentState
from yuki.agent.registry.service import Registry
from yuki.agent.watchdog.service import WatchDog
from yuki.agent.desktop.service import Desktop
from yuki.agent.desktop.views import Browser
from yuki.agent.loop import LoopGuard
from yuki.agent.settle import SettleTracker, bounds_for
from yuki.agent.usersense import UserSense
from yuki.agent.interaction import InteractionHub
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
        disable_loop_detection: bool = False,
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
            disable_loop_detection: Disable loop detection warnings. Defaults to False (guard active).
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

        # Optional Tool RAG selector. When set, `tools` returns a task-relevant
        # subset instead of all tools (helps small models). Built by the caller
        # (e.g. the control endpoint) for local models; None = all tools.
        self.tool_selector = None
        # AX-tree verbosity: "lean" for small/local models, "full" otherwise.
        self.ax_verbosity = "full"

        # Cooperative cancellation: request_stop() (e.g. from the HUD stop
        # button via /chat/control/cancel) makes the loop exit cleanly at the
        # next step boundary instead of mid-action.
        self._stop_requested = False

        # Event-driven settling: the watchdog stamps every AX notification;
        # after an action we wait for the UI to quiesce instead of sleeping a
        # fixed amount. UserSense spots hardware input the agent didn't inject
        # (= the human took over) so the loop can pause instead of fighting.
        self.settle_tracker = SettleTracker()
        self.usersense = UserSense()
        # Ask-mid-task + pause/resume channel (backend routes user replies in).
        self.interaction = InteractionHub()

        self.event = Event()
        if event_subscriber is not None:
            self.event.add_subscriber(event_subscriber)
        if log_to_console:
            self.event.add_subscriber(ConsoleEventSubscriber())
        if log_to_file:
            self.event.add_subscriber(FileEventSubscriber())

        self._cached_system_message: SystemMessage | None = None

    def request_stop(self) -> None:
        """Ask the running loop to stop at the next step boundary."""
        self._stop_requested = True
        # Unblock a parked ask/pause so the stop lands immediately.
        self.interaction.cancel_question()
        self.interaction.resume()

    def _maybe_pause_for_user(self, step: int) -> bool:
        """Park while the human is driving. False = stop was requested."""
        if step == 0 or not self.usersense.user_intervened():
            return True
        self.event.emit(AgentEvent(type=EventType.PAUSED, data={
            "step": step,
            "reason": "You took over the mouse/keyboard — paused.",
        }))
        self.interaction.begin_pause()
        resumed = self.interaction.wait_resume_sync(
            should_abort=lambda: self._stop_requested
        )
        if not resumed:
            return False
        self.usersense.mark_agent_action()  # forgive input made during pause
        self.event.emit(AgentEvent(type=EventType.RESUMED, data={"step": step}))
        return True

    def _handle_ask_user(self, step: int, params: dict) -> str:
        """Block on the interaction hub until the user answers (or stops)."""
        question = str(params.get("question") or "").strip()
        options = params.get("options") or []
        self.interaction.begin_question(question)
        self.event.emit(AgentEvent(type=EventType.ASK, data={
            "step": step, "question": question, "options": options,
        }))
        answer = self.interaction.wait_answer_sync(timeout=300.0)
        if answer is None:
            return ("The user did not answer (question dismissed or timed out). "
                    "Proceed with the most reasonable default and mention the "
                    "choice in your final answer, or finish with done_tool if "
                    "you cannot proceed safely.")
        return f"The user answered: {answer}"

    def _stopped_result(self) -> AgentResult:
        self.event.emit(
            AgentEvent(
                type=EventType.ERROR,
                data={"step": self.state.step, "error": "Stopped by user."},
            )
        )
        return AgentResult(is_done=False, error="cancelled")

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
        all_tools = self.registry.get_tools()
        selector = getattr(self, "tool_selector", None)
        task = getattr(self.state, "task", "") or ""
        if selector is None or not task:
            return all_tools
        return selector.select(task)

    def _ax_verbosity(self) -> str:
        return getattr(self, "ax_verbosity", "full")

    def loop(self) -> AgentResult:
        """Run the main agent loop synchronously."""
        self.state.messages.insert(0, self.system_message)
        self.state.messages.append(self.task_message)
        consecutive_failures = 0
        self._loop_guard.reset()

        for step in range(self.state.max_steps):
            self.state.step = step
            if self._stop_requested:
                return self._stopped_result()
            if not self._maybe_pause_for_user(step):
                return self._stopped_result()

            # Snapshot FIRST so change detection can diff against the previous
            # step before the prompt is built from this same snapshot.
            self.desktop.get_state()
            self._loop_guard.record_state(self.desktop.desktop_state)
            ui_change = self._loop_guard.change_summary() if step > 0 else ""

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
                verbosity=self._ax_verbosity(),
                ui_change=ui_change,
                refresh=False,
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
                        "ui_change": ui_change or None,
                    },
                )
            )
            if nudge:
                self.event.emit(
                    AgentEvent(type=EventType.ERROR, data={"step": step, "error": f"Loop detected: {nudge}"})
                )
            self.state.messages.append(state_msg)

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
            # Text-rejection nudges only matter within this step's retry loop.
            self.state.error_messages.clear()

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
            if tool_name == "ask_user_tool":
                from yuki.agent.registry.views import ToolResult
                answer_text = self._handle_ask_user(step, tool_params)
                if self._stop_requested:
                    return self._stopped_result()
                tool_result = ToolResult(is_success=True, content=answer_text)
            else:
                self.usersense.mark_agent_action()
                tool_result = self.registry.execute(tool_name=tool_name, tool_params=tool_params, desktop=self.desktop)
            self.usersense.mark_agent_action()

            self._loop_guard.record_action(tool_name, tool_params, tool_result.is_success)

            # Event-driven settle: wait until AX notifications quiesce (min/max
            # bounds per tool) instead of a fixed sleep. Falls back to the old
            # fixed sleep when the watchdog produced no signal this run.
            settle = 0.0
            if tool_result.is_success and tool_name != "done_tool":
                min_w, max_w = bounds_for(tool_name)
                if max_w > 0.0:
                    settle = self.settle_tracker.settle(min_w, max_w)

            # Both outcomes go into the MAIN history so the model sees actions
            # and their failures in chronological order. (Failures used to go
            # to the error_messages side-channel, which is appended after the
            # whole history on every call — out of order and never pruned.)
            content = tool_result.content if tool_result.is_success else tool_result.error
            message.content = content
            self.state.messages.append(message)

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

            # Only treat done_tool as terminal when it actually VALIDATED.
            # A malformed done (e.g. small models dropping the required
            # `answer`/`thought` fields) must NOT count as success — otherwise
            # the agent exits with 0 steps and an empty reply having done
            # nothing. A failed done was already recorded as a tool failure
            # above (its validation error is fed back), so the loop retries and
            # the model is pushed to either act or emit a valid done.
            if tool_name == "done_tool" and tool_result.is_success:
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
        self._stop_requested = False
        self.state.task = task
        try:
            with self.desktop.auto_minimize() if self.auto_minimize else nullcontext():
                self.watchdog.set_focus_callback(self.desktop.tree.on_focus_changed)
                # Structure/property notifications feed the settle tracker so
                # post-action waits end as soon as the UI actually quiesces.
                self.watchdog.set_structure_callback(self.settle_tracker.notify)
                self.watchdog.set_property_callback(self.settle_tracker.notify)
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
            if self._stop_requested:
                return self._stopped_result()
            if not self._maybe_pause_for_user(step):
                return self._stopped_result()

            # Snapshot FIRST so change detection can diff against the previous
            # step before the prompt is built from this same snapshot.
            self.desktop.get_state()
            self._loop_guard.record_state(self.desktop.desktop_state)
            ui_change = self._loop_guard.change_summary() if step > 0 else ""

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
                verbosity=self._ax_verbosity(),
                ui_change=ui_change,
                refresh=False,
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
                        "ui_change": ui_change or None,
                    },
                )
            )
            if nudge:
                self.event.emit(
                    AgentEvent(type=EventType.ERROR, data={"step": step, "error": f"Loop detected: {nudge}"})
                )
            self.state.messages.append(state_msg)

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
            # Text-rejection nudges only matter within this step's retry loop.
            self.state.error_messages.clear()

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

            if tool_name == "ask_user_tool":
                from yuki.agent.registry.views import ToolResult
                answer_text = await asyncio.to_thread(self._handle_ask_user, step, tool_params)
                if self._stop_requested:
                    return self._stopped_result()
                tool_result = ToolResult(is_success=True, content=answer_text)
            else:
                self.usersense.mark_agent_action()
                tool_result = await self.registry.aexecute(tool_name=tool_name, tool_params=tool_params, desktop=self.desktop)
            self.usersense.mark_agent_action()

            self._loop_guard.record_action(tool_name, tool_params, tool_result.is_success)

            # Event-driven settle (async): same bounds, off-loop-friendly wait.
            settle = 0.0
            if tool_result.is_success and tool_name != "done_tool":
                min_w, max_w = bounds_for(tool_name)
                if max_w > 0.0:
                    settle = await asyncio.to_thread(
                        self.settle_tracker.settle, min_w, max_w
                    )

            # Both outcomes go into the MAIN history so the model sees actions
            # and their failures in chronological order. (Failures used to go
            # to the error_messages side-channel, which is appended after the
            # whole history on every call — out of order and never pruned.)
            content = tool_result.content if tool_result.is_success else tool_result.error
            message.content = content
            self.state.messages.append(message)

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

            # Only treat done_tool as terminal when it actually VALIDATED.
            # A malformed done (e.g. small models dropping the required
            # `answer`/`thought` fields) must NOT count as success — otherwise
            # the agent exits with 0 steps and an empty reply having done
            # nothing. A failed done was already recorded as a tool failure
            # above (its validation error is fed back), so the loop retries and
            # the model is pushed to either act or emit a valid done.
            if tool_name == "done_tool" and tool_result.is_success:
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
        self._stop_requested = False
        self.state.task = task
        try:
            with self.desktop.auto_minimize() if self.auto_minimize else nullcontext():
                self.watchdog.set_focus_callback(self.desktop.tree.on_focus_changed)
                # Structure/property notifications feed the settle tracker so
                # post-action waits end as soon as the UI actually quiesces.
                self.watchdog.set_structure_callback(self.settle_tracker.notify)
                self.watchdog.set_property_callback(self.settle_tracker.notify)
                with self.watchdog:
                    result = await self.aloop()
            return result
        except Exception as e:
            self.event.emit(
                AgentEvent(type=EventType.ERROR, data={"step": self.state.step, "error": str(e)})
            )
            raise
