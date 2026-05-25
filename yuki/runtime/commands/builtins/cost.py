from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register


def _cost(args: str) -> CommandResult:
    return CommandResult.local_text(
        "Cost tracking: see ~/Library/Application Support/Yuki/sessions/"
        "<id>.cost.json"
    )


register(
    LocalCommand(
        name="cost",
        run=_cost,
        description="Show this session's token usage.",
    )
)
