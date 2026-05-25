from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import REGISTRY, register


def _help(args: str) -> CommandResult:
    lines = ["Built-in slash commands:\n"]
    for name in sorted(REGISTRY):
        cmd = REGISTRY[name]
        lines.append(f"  /{name} — {cmd.description}")
    return CommandResult.local_text("\n".join(lines))


register(LocalCommand(name="help", run=_help, description="Show this help."))
