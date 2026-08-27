"""
Multi-Provider System — barcha asosiy AI provayderlarni qo'llab-quvvatlash.

Provayderlar:
- LLM: OpenAI, Gemini, Claude, Mistral, DeepSeek, Groq, Cohere
- TTS: Edge, ElevenLabs, Azure, Gemini, OpenAI, Amazon Polly, Play.ht, Bark
- STT: OpenAI Whisper, Gemini, AssemblyAI, Deepgram

Har bir provayder uchun:
- Avtomatik fallback
- Health check
- Rate limiting
- Cost tracking
"""

from backend.services.providers.base import (
    LLMProvider,
    TTSProvider,
    STTProvider,
    ProviderResponse,
    ProviderHealth,
)
from backend.services.providers.registry import ProviderRegistry
from backend.services.providers.fallback import FallbackChain
from backend.services.providers.llm_providers import (
    OpenAILLMProvider,
    ClaudeLLMProvider,
    MistralLLMProvider,
    DeepSeekLLMProvider,
    GroqLLMProvider,
)
from backend.services.providers.cohere_provider import CohereLLMProvider

__all__ = [
    "LLMProvider",
    "TTSProvider",
    "STTProvider",
    "ProviderResponse",
    "ProviderHealth",
    "ProviderRegistry",
    "FallbackChain",
    # LLM Providers
    "OpenAILLMProvider",
    "ClaudeLLMProvider",
    "MistralLLMProvider",
    "DeepSeekLLMProvider",
    "GroqLLMProvider",
    "CohereLLMProvider",
]
