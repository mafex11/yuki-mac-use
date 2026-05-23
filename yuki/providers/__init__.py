"""
Unified provider package for Macos-Use.

Each provider lives in its own sub-package (e.g. ``providers.google``)
and exposes all capabilities (LLM, STT, TTS) it supports.

Shared base protocols and data models:
    - ``BaseChatLLM``  — LLM provider protocol
    - ``BaseSTT``      — Speech-to-Text provider protocol
    - ``BaseTTS``      — Text-to-Speech provider protocol
    - ``TokenUsage``, ``Metadata`` — LLM data models
"""

# Base protocols & data models
from yuki.providers.base import BaseChatLLM, BaseSTT, BaseTTS
from yuki.providers.views import TokenUsage, Metadata
from yuki.providers.events import Thinking, LLMEvent, LLMStreamEvent, ToolCall

# LLM providers
from yuki.providers.anthropic import ChatAnthropic
from yuki.providers.google import ChatGoogle
from yuki.providers.openai import ChatOpenAI
from yuki.providers.ollama import ChatOllama
from yuki.providers.groq import ChatGroq
from yuki.providers.mistral import ChatMistral
from yuki.providers.cerebras import ChatCerebras
from yuki.providers.open_router import ChatOpenRouter
from yuki.providers.azure_openai import ChatAzureOpenAI
from yuki.providers.litellm import ChatLiteLLM
from yuki.providers.vllm import ChatVLLM
from yuki.providers.nvidia import ChatNvidia
from yuki.providers.deepseek import ChatDeepSeek

# STT providers
from yuki.providers.openai import STTOpenAI
from yuki.providers.google import STTGoogle
from yuki.providers.groq import STTGroq
try:
    from yuki.providers.elevenlabs import STTElevenLabs
except ImportError:
    pass

try:
    from yuki.providers.deepgram import STTDeepgram
except ImportError:
    pass

# TTS providers
from yuki.providers.openai import TTSOpenAI
from yuki.providers.google import TTSGoogle
from yuki.providers.groq import TTSGroq

try:
    from yuki.providers.elevenlabs import TTSElevenLabs
except ImportError:
    pass

try:
    from yuki.providers.deepgram import TTSDeepgram
except ImportError:
    pass

# Misc
from yuki.providers.google.tts import GOOGLE_TTS_VOICES

__all__ = [
    # Base
    "BaseChatLLM",
    "BaseSTT",
    "BaseTTS",
    "TokenUsage",
    "Metadata",
    "Thinking",
    "LLMEvent",
    "LLMStreamEvent",
    "ToolCall",
    # LLM providers
    "ChatAnthropic",
    "ChatGoogle",
    "ChatOpenAI",
    "ChatOllama",
    "ChatGroq",
    "ChatMistral",
    "ChatCerebras",
    "ChatOpenRouter",
    "ChatAzureOpenAI",
    "ChatLiteLLM",
    "ChatVLLM",
    "ChatNvidia",
    "ChatDeepSeek",
    # STT providers
    "STTOpenAI",
    "STTGoogle",
    "STTGroq",
    "STTElevenLabs",
    "STTDeepgram",
    # TTS providers
    "TTSOpenAI",
    "TTSGoogle",
    "TTSGroq",
    "TTSElevenLabs",
    "TTSDeepgram",
    "GOOGLE_TTS_VOICES",
]
