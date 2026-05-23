"""Yuki — a macOS-native personal AI assistant that learns who you are.

Public agent surface (this module):

    from yuki import Agent, Browser
    from yuki.providers.stub import ChatStub  # for tests
    from yuki.providers.anthropic import ChatAnthropic  # production

    agent = Agent(llm=ChatAnthropic())
    result = agent.invoke(task="Open Notes and write a haiku.")

Public plugin SDK (Plan G Task 18):

    from yuki import tool, DangerLevel

    @tool(name="hello", danger=DangerLevel.READ_ONLY)
    async def hello(name: str) -> str:
        '''Say hello.'''
        return f"Hi {name}"
"""

__version__ = "0.0.1"

from yuki.agent.desktop.views import Browser
from yuki.agent.service import Agent

__all__ = ["Agent", "Browser", "__version__"]
