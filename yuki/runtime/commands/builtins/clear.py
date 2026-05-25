from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register

register(
    LocalCommand(
        name="clear",
        run=lambda args: CommandResult.local_text("Conversation cleared."),
        description="Clear the current conversation.",
    )
)
