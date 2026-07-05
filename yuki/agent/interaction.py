"""InteractionHub — the channel between a running agent and the human.

Port of claude-leak's raced-promise permission pattern (interactiveHandler.ts)
reduced to Yuki's needs: one agent, one human, two interaction kinds —

  ask:    the agent asked a question and blocks until answer()/skip/stop
  pause:  the user took over the Mac; the loop parks until resume()/stop

Threading model: the backend runs the agent loop as an asyncio task on the
same event loop as the HTTP routers, but scripts drive the SYNC loop from a
plain thread. threading.Event state + short-poll async waiters work for both
(human-scale latency; 150ms polling is imperceptible).
"""

from __future__ import annotations

import asyncio
import threading
import time


class InteractionHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._answered = threading.Event()
        self._answer: str | None = None
        self._question: str | None = None
        self._resumed = threading.Event()

    # ------------------------------------------------------------- ask

    def begin_question(self, question: str) -> None:
        with self._lock:
            self._question = question
            self._answer = None
            self._answered.clear()

    @property
    def pending_question(self) -> str | None:
        return self._question

    def answer(self, text: str) -> bool:
        """Deliver the user's answer. False if nothing was being asked."""
        with self._lock:
            if self._question is None:
                return False
            self._answer = text
            self._question = None
            self._answered.set()
            return True

    def cancel_question(self) -> None:
        """Unblock a pending ask with no answer (stop/skip)."""
        with self._lock:
            if self._question is not None:
                self._question = None
                self._answer = None
                self._answered.set()

    def wait_answer_sync(self, timeout: float) -> str | None:
        self._answered.wait(timeout)
        return self._answer

    async def wait_answer_async(self, timeout: float) -> str | None:
        start = time.monotonic()
        while not self._answered.is_set():
            if time.monotonic() - start > timeout:
                return None
            await asyncio.sleep(0.15)
        return self._answer

    # ------------------------------------------------------------ pause

    def begin_pause(self) -> None:
        self._resumed.clear()

    def resume(self) -> None:
        self._resumed.set()

    def wait_resume_sync(self, should_abort, timeout: float = 300.0) -> bool:
        """Park until resume() or should_abort() or timeout. True = resumed."""
        start = time.monotonic()
        while not self._resumed.is_set():
            if should_abort() or time.monotonic() - start > timeout:
                return False
            time.sleep(0.15)
        return True

    async def wait_resume_async(self, should_abort, timeout: float = 300.0) -> bool:
        start = time.monotonic()
        while not self._resumed.is_set():
            if should_abort() or time.monotonic() - start > timeout:
                return False
            await asyncio.sleep(0.15)
        return True
