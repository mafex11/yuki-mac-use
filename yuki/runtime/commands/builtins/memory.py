from yuki.runtime.commands.base import PromptCommand
from yuki.runtime.commands.registry import register

register(
    PromptCommand(
        name="memory",
        prompt_template="Search memory for: {args}",
        description="Search the vault.",
    )
)
