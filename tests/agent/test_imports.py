"""Imports test — every public surface from Plan A imports cleanly."""


def test_top_level_imports() -> None:
    from yuki import Agent, Browser, __version__

    assert __version__ == "0.0.1"
    assert Agent.__name__ == "Agent"
    assert Browser.__name__ == "Browser"


def test_provider_imports() -> None:
    from yuki.providers.anthropic import ChatAnthropic
    from yuki.providers.openai import ChatOpenAI
    from yuki.providers.stub import ChatStub

    assert ChatStub.__name__ == "ChatStub"
    assert ChatAnthropic.__name__ == "ChatAnthropic"
    assert ChatOpenAI.__name__ == "ChatOpenAI"


def test_anthropic_default_model_is_sonnet_4_6() -> None:
    import inspect

    from yuki.providers.anthropic import ChatAnthropic

    sig = inspect.signature(ChatAnthropic.__init__)
    assert sig.parameters["model"].default == "claude-sonnet-4-6"


def test_no_telemetry_anywhere() -> None:
    """Sentinel: ensure we never reintroduce telemetry by accident."""
    import importlib

    for mod_name in ("yuki", "yuki.agent.service"):
        mod = importlib.import_module(mod_name)
        for attr in dir(mod):
            assert "telemetry" not in attr.lower(), (
                f"{mod_name} exposes telemetry-shaped attr: {attr}"
            )
