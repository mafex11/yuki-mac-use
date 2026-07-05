"""Hand-labeled evaluation cases for agent plan-correctness.

Each case is (task -> expected coordinate-free plan). args_matcher values are
regex patterns applied (case-insensitively) to the corresponding emitted arg.
ax_fixture optionally supplies a canned pruned AX-tree so state-dependent first
steps can be graded deterministically (no live Mac).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files


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


# NOTE on measurement: run.py grades the FIRST emitted tool call against
# expected_plan[0]. So each case is really a "given this task (+ optional
# screen), what's the correct FIRST action?" test. Cases are phrased
# DIFFERENTLY from the training seeds/trajectories on purpose — we want to
# measure generalization, not memorization of training surface forms.
#
# 36 cases (was 10) so a fine-tune delta is measurable above the ~±0.1 noise a
# 10-case set has. Grouped by the tool the first step should select; each group
# spans varied phrasings + the tricky discriminations (e.g. "list Downloads" =
# shell, NOT app/Finder; a question = done_tool, NOT a desktop action).
CASES: list[EvalCase] = [
    # ---- app_tool: launch / switch (varied phrasings, varied apps) ----
    EvalCase(task="open calculator",
             expected_plan=[ExpectedStep("app_tool", {"name": r"calc"}), ExpectedStep("done_tool")]),
    EvalCase(task="fire up Spotify for me",
             expected_plan=[ExpectedStep("app_tool", {"name": r"spotify"}), ExpectedStep("done_tool")]),
    EvalCase(task="I need to use the Terminal",
             expected_plan=[ExpectedStep("app_tool", {"name": r"terminal"}), ExpectedStep("done_tool")]),
    EvalCase(task="bring Safari to the front",
             expected_plan=[ExpectedStep("app_tool", {"name": r"safari"}), ExpectedStep("done_tool")]),
    EvalCase(task="get me into Notes",
             expected_plan=[ExpectedStep("app_tool", {"name": r"notes"}), ExpectedStep("done_tool")]),
    EvalCase(task="launch the Mail app",
             expected_plan=[ExpectedStep("app_tool", {"name": r"mail"}), ExpectedStep("done_tool")]),

    # ---- shortcut_tool: keyboard actions (distinct from clicking/typing) ----
    EvalCase(task="copy that",
             expected_plan=[ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+c"}), ExpectedStep("done_tool")]),
    EvalCase(task="paste it",
             expected_plan=[ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+v"}), ExpectedStep("done_tool")]),
    EvalCase(task="save the file",
             expected_plan=[ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+s"}), ExpectedStep("done_tool")]),
    EvalCase(task="undo the last change",
             expected_plan=[ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+z"}), ExpectedStep("done_tool")]),
    EvalCase(task="open a new browser tab",
             expected_plan=[ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+t"}), ExpectedStep("done_tool")]),
    EvalCase(task="select all the text",
             expected_plan=[ExpectedStep("shortcut_tool", {"shortcut": r"(?i)command\+a"}), ExpectedStep("done_tool")]),

    # ---- shell_tool: filesystem/system (the tricky "not app_tool" cases) ----
    EvalCase(task="list the files in my Downloads folder",
             expected_plan=[ExpectedStep("shell_tool", {"command": r"(?i)ls.*downloads"}), ExpectedStep("done_tool")]),
    EvalCase(task="how much free disk space is there",
             expected_plan=[ExpectedStep("shell_tool", {"command": r"(?i)df"}), ExpectedStep("done_tool")]),
    EvalCase(task="make a folder called Reports on my desktop",
             expected_plan=[ExpectedStep("shell_tool", {"command": r"(?i)mkdir"}), ExpectedStep("done_tool")]),
    EvalCase(task="show me what's running",
             expected_plan=[ExpectedStep("shell_tool", {"command": r"(?i)(ps|top)"}), ExpectedStep("done_tool")]),
    EvalCase(task="what's my current directory",
             expected_plan=[ExpectedStep("shell_tool", {"command": r"(?i)pwd"}), ExpectedStep("done_tool")]),

    # ---- scroll_tool ----
    EvalCase(task="scroll down on this page",
             expected_plan=[ExpectedStep("scroll_tool", {"direction": r"(?i)down"}), ExpectedStep("done_tool")]),
    EvalCase(task="scroll back up",
             expected_plan=[ExpectedStep("scroll_tool", {"direction": r"(?i)up"}), ExpectedStep("done_tool")]),

    # ---- wait_tool ----
    EvalCase(task="hold on a few seconds while it loads",
             expected_plan=[ExpectedStep("wait_tool"), ExpectedStep("done_tool")]),

    # ---- done_tool: questions / chat (must NOT reach for a desktop action) ----
    EvalCase(task="what is the capital of France?",
             expected_plan=[ExpectedStep("done_tool", {"answer": r"(?i)paris"})]),
    EvalCase(task="who painted the Mona Lisa?",
             expected_plan=[ExpectedStep("done_tool", {"answer": r"(?i)(da vinci|leonardo)"})]),
    EvalCase(task="what's 15 times 4?",
             expected_plan=[ExpectedStep("done_tool", {"answer": r"60"})]),
    EvalCase(task="say hello",
             expected_plan=[ExpectedStep("done_tool")]),
    EvalCase(task="good morning Yuki",
             expected_plan=[ExpectedStep("done_tool")]),
    EvalCase(task="thanks, that's all",
             expected_plan=[ExpectedStep("done_tool")]),
    EvalCase(task="explain in one line what an API is",
             expected_plan=[ExpectedStep("done_tool")]),
    EvalCase(task="what can you do?",
             expected_plan=[ExpectedStep("done_tool")]),

    # ---- multi-step: graded on the FIRST step (the correct opening move) ----
    EvalCase(task="open calculator and type 5+5",
             expected_plan=[ExpectedStep("app_tool", {"name": r"calc"})], reactive=True),
    EvalCase(task="open Chrome and go to youtube.com",
             expected_plan=[ExpectedStep("app_tool", {"name": r"(chrome|google chrome)"})], reactive=True),
    EvalCase(task="open Spotify and play some jazz",
             expected_plan=[ExpectedStep("app_tool", {"name": r"spotify"})], reactive=True),

    # ---- reactive: need the screen to pick coords/target ----
    EvalCase(task="click the Submit button", reactive=True, ax_fixture="submit_button.txt",
             expected_plan=[ExpectedStep("click_tool")]),
    EvalCase(task="type my email into the username field", reactive=True, ax_fixture="login_form.txt",
             expected_plan=[ExpectedStep("type_tool", {"text": r".+"})]),
    EvalCase(task="go to github.com", reactive=True, ax_fixture="browser_address.txt",
             expected_plan=[ExpectedStep("type_tool", {"text": r"(?i)github"})]),
    EvalCase(task="open the first search result", reactive=True, ax_fixture="search_results.txt",
             expected_plan=[ExpectedStep("click_tool")]),
]


def load_fixture(name: str) -> str:
    """Read a canned AX-tree fixture from yuki/eval/fixtures/."""
    path = files("yuki.eval").joinpath("fixtures", name)
    if not path.is_file():
        raise FileNotFoundError(f"eval fixture not found: {name}")
    return path.read_text(encoding="utf-8")
