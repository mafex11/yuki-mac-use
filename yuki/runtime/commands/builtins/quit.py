from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register

register(
    LocalCommand(
        name="quit",
        run=lambda args: CommandResult.skip(),
        description="Stop the current conversation without sending a turn.",
    )
)
