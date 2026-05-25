from yuki.runtime.commands.base import CommandResult, LocalCommand
from yuki.runtime.commands.registry import register

register(
    LocalCommand(
        name="compact",
        run=lambda args: CommandResult.local_text(
            "Compaction will run on next turn (autocompact threshold reached)."
        ),
        description="Force-compact the conversation now.",
    )
)
