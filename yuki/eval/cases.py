"""Hand-labeled evaluation cases for agent plan-correctness.

Each case is (task -> expected coordinate-free plan). args_matcher values are
regex patterns applied (case-insensitively) to the corresponding emitted arg.
ax_fixture optionally supplies a canned pruned AX-tree so state-dependent first
steps can be graded deterministically (no live Mac).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExpectedStep:
    tool: str
    # arg name -> regex the emitted arg value must match (case-insensitive).
    args_matcher: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCase:
    task: str
    expected_plan: list[ExpectedStep]
    reactive: bool = False          # if True, only the first step is graded
    ax_fixture: str | None = None   # filename under yuki/eval/fixtures/, or None


CASES: list[EvalCase] = [
    EvalCase(
        task="open calculator",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"calc"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="open the Notes app",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"notes"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="switch to Safari",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"safari"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="open calculator and type 5+5",
        expected_plan=[
            ExpectedStep("app_tool", {"name": r"calc"}),
            ExpectedStep("type_tool", {"text": r"5\+5"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="copy the selection",
        expected_plan=[
            ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+c"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="list the files in my Downloads folder",
        expected_plan=[
            ExpectedStep("shell_tool", {"command": r"(?i)ls.*downloads"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="scroll down on this page",
        expected_plan=[
            ExpectedStep("scroll_tool", {"direction": r"(?i)down"}),
            ExpectedStep("done_tool"),
        ],
    ),
    EvalCase(
        task="what is the capital of France?",
        expected_plan=[ExpectedStep("done_tool", {"answer": r"(?i)paris"})],
    ),
    EvalCase(
        task="say hello",
        expected_plan=[ExpectedStep("done_tool")],
    ),
    EvalCase(
        task="click the Submit button",
        expected_plan=[
            ExpectedStep("click_tool"),
            ExpectedStep("done_tool"),
        ],
        reactive=True,
        ax_fixture="submit_button.txt",
    ),
]
