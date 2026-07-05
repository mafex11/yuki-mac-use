from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from yuki.agent.desktop.views import DesktopState

_EXEMPT = {'done_tool', 'wait_tool'}
_IGNORE_PARAMS = {'thought', 'evaluate', 'plan'}
# Hard-stop threshold: same action repeated this many times in a row → halt.
_HARD_STOP_REPEATS = 3

_REPEAT_NUDGES = {
    3: 'You have repeated the same action {n} times — make sure it is actually making progress.',
    5: 'Same action repeated {n} times. If you are stuck, try a different approach.',
    8: 'Same action repeated {n} times. Stop and take a completely different strategy.',
}


class LoopGuard:
    """Watches for signs that the agent is looping:

    - **Action repetition**: the same tool + params appearing too often in the last `window` steps.
    - **UI stagnation**: the desktop state not changing across consecutive steps.
    - **State cycle**: the agent returning to a UI state it has already visited.
    - **Failed action retry**: the agent calling the exact same action that just failed.
    """

    def __init__(self, window: int = 15) -> None:
        self._hashes: deque[str] = deque(maxlen=window)
        self._last_state: tuple[str, str] | None = None
        self._stagnant = 0
        self._visited_states: dict[str, int] = {}
        self._cycle_warning: str = ''
        self._last_action_key: str | None = None
        self._last_action_failed: bool = False
        self._failed_retry_warning: str = ''
        # Count of CONSECUTIVE identical actions (resets when a different
        # action is seen). Distinct from _hashes which tracks a sliding window.
        self._consecutive_repeats: int = 1
        self._last_consecutive_tool: str | None = None
        self._change_summary: str = ''
        self._last_window_title: str = ''

    def record_action(self, tool: str, params: dict, is_success: bool = True) -> None:
        if tool in _EXEMPT:
            return
        filtered = {k: v for k, v in params.items() if k not in _IGNORE_PARAMS}
        normalised = {
            k: v.strip().lower() if isinstance(v, str) else v
            for k, v in filtered.items()
        }
        raw = json.dumps({tool: normalised}, sort_keys=True).encode()
        key = hashlib.sha256(raw).hexdigest()[:12]
        self._hashes.append(key)

        if not is_success and self._last_action_key == key and self._last_action_failed:
            self._failed_retry_warning = (
                f"You are retrying '{tool}' with the same parameters after it already failed. "
                'The same action will produce the same failure — change your approach, '
                'try different parameters, or use a different tool.'
            )
        else:
            self._failed_retry_warning = ''

        # Consecutive-same-action tracking (for hard stop).
        if self._last_action_key == key:
            self._consecutive_repeats += 1
        else:
            self._consecutive_repeats = 1
        self._last_consecutive_tool = tool

        self._last_action_key = key
        self._last_action_failed = not is_success

    def record_state(self, desktop_state: DesktopState) -> None:
        """Record the current desktop state as a fingerprint."""
        # Use bundle_id + pid as window identity (macOS equivalent of HWND)
        if desktop_state and desktop_state.active_window:
            w = desktop_state.active_window
            window_id = f"{w.bundle_id}:{w.pid}"
            window_title = w.name or w.bundle_id
        else:
            window_id = "no_window"
            window_title = "no window"

        if desktop_state and desktop_state.tree_state:
            content_text = desktop_state.tree_state.interactive_elements_to_string()
        elif desktop_state and desktop_state.active_window:
            content_text = desktop_state.active_window.name
        else:
            content_text = "no_content"

        digest = hashlib.sha256(content_text.encode('utf-8', errors='replace')).hexdigest()[:16]
        state = (window_id, digest)

        # Per-step change summary, surfaced to the model in the next state
        # message. "Nothing changed" after a click is the single most useful
        # signal for self-correction — without it the model assumes success.
        if self._last_state is None:
            self._change_summary = ''
        elif state == self._last_state:
            self._change_summary = (
                'NO visible change: the active window and its elements are '
                'identical to before your last action. If you expected a '
                'change, the action likely missed or had no effect.'
            )
        elif self._last_state[0] != state[0]:
            self._change_summary = (
                f"The foreground window CHANGED to '{window_title}'. "
                'Coordinates from the previous state are stale — use the '
                'element list below.'
            )
        else:
            self._change_summary = (
                'The window contents changed after your last action '
                '(same app in foreground).'
            )
        self._last_window_title = window_title

        if state == self._last_state:
            self._stagnant += 1
        else:
            self._stagnant = 0
        self._last_state = state

    def change_summary(self) -> str:
        """Human-readable description of what changed since the previous state."""
        return self._change_summary

        fingerprint = f'{window_id}|{digest}'
        count = self._visited_states.get(fingerprint, 0) + 1
        self._visited_states[fingerprint] = count
        if count == 2:
            self._cycle_warning = (
                'You have returned to a UI state you already visited. '
                'You may be cycling between states. Try a completely different approach '
                'instead of repeating the same steps.'
            )
        elif count >= 3:
            self._cycle_warning = (
                f'You have returned to this state {count} times. '
                'You are stuck in a loop — stop and reconsider your strategy entirely. '
                'Try an alternative method or approach.'
            )
        else:
            self._cycle_warning = ''

    def check(self) -> str | None:
        warnings: list[str] = []

        if self._hashes:
            top = Counter(self._hashes).most_common(1)[0][1]
            for threshold in sorted(_REPEAT_NUDGES, reverse=True):
                if top >= threshold:
                    warnings.append(_REPEAT_NUDGES[threshold].format(n=top))
                    break

        if self._stagnant >= 4:
            warnings.append(
                f'The UI has not changed for {self._stagnant} steps. '
                'Your actions may not be having any effect. '
                'If waiting for something external use wait_tool first, then re-check.'
            )

        if self._cycle_warning:
            warnings.append(self._cycle_warning)

        if self._failed_retry_warning:
            warnings.append(self._failed_retry_warning)

        return '\n\n'.join(warnings) or None

    def hard_stop_reason(self) -> str | None:
        """Return a non-empty reason if the loop must HARD STOP this turn.

        Triggered when the same (tool, params) was seen `_HARD_STOP_REPEATS`
        consecutive times — port of LLM-OS rule #7. The agent loop should
        inject this as a system message forcing `done_tool` or a new approach.
        """
        if self._consecutive_repeats >= _HARD_STOP_REPEATS and self._last_consecutive_tool:
            return (
                f"You have called '{self._last_consecutive_tool}' with the same "
                f"parameters {self._consecutive_repeats} times in a row without "
                "the desired effect. STOP. Call `done_tool` reporting partial "
                "success and the specific failure and asking the user for "
                "guidance, OR take a substantively different approach "
                "(different tool, different coordinates from the refreshed "
                "Desktop State, different shortcut). Do NOT call the same "
                "action a fourth time."
            )
        return None

    def reset(self) -> None:
        self._hashes.clear()
        self._last_state = None
        self._stagnant = 0
        self._visited_states = {}
        self._cycle_warning = ''
        self._last_action_key = None
        self._last_action_failed = False
        self._failed_retry_warning = ''
        self._consecutive_repeats = 1
        self._last_consecutive_tool = None
        self._change_summary = ''
        self._last_window_title = ''


def should_continue(assistant_message) -> bool:
    """Continue the agent loop iff the assistant emitted any tool_use blocks.

    stop_reason is unreliable per Anthropic's own implementation
    (see claude-leak/src/query.ts:557 in the leaked Claude Code source).
    The block list is authoritative.

    Used as a defensive predicate for any future provider that produces
    Anthropic-shaped messages. The vendored MacOS-Use loop already uses
    "tool_name == 'done_tool'" as its termination signal.
    """
    blocks = getattr(assistant_message, "content", None) or []
    for b in blocks:
        kind = getattr(b, "type", None) or (
            b.get("type") if isinstance(b, dict) else None
        )
        if kind == "tool_use":
            return True
    return False
