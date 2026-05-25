"""Stop hooks: pass-through, inject, first-inject-wins."""

from __future__ import annotations

from yuki.runtime.stop_hooks import StopHookRegistry, StopVerdict


def test_no_hooks_returns_pass_through() -> None:
    reg = StopHookRegistry()
    verdict = reg.evaluate(messages=[])
    assert verdict.action == "pass"


def test_hook_inject_reopens_loop() -> None:
    reg = StopHookRegistry()
    reg.register(lambda msgs: StopVerdict.inject("Are you sure you're done?"))
    verdict = reg.evaluate(messages=[])
    assert verdict.action == "inject"
    assert "sure" in verdict.injected_message


def test_first_inject_wins() -> None:
    reg = StopHookRegistry()
    reg.register(lambda msgs: StopVerdict.pass_through())
    reg.register(lambda msgs: StopVerdict.inject("wait"))
    reg.register(lambda msgs: StopVerdict.inject("ignored"))
    verdict = reg.evaluate(messages=[])
    assert verdict.action == "inject"
    assert verdict.injected_message == "wait"
