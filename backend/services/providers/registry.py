"""
Provider Registry — barcha provayderlarni ro'yxatga olish va boshqarish.

Usage:
    registry = ProviderRegistry()

    # LLM provayderlar
    registry.register_llm("openai", OpenAIProvider(api_key="..."))
    registry.register_llm("claude", ClaudeProvider(api_key="..."))
    registry.register_llm("gemini", GeminiProvider(api_key="..."))

    # TTS provayderlar
    registry.register_tts("edge", EdgeProvider())
    registry.register_tts("elevenlabs", ElevenLabsProvider(api_key="..."))

    # STT provayderlar
    registry.register_stt("whisper", WhisperProvider(api_key="..."))

    # Fallback chain
    chain = registry.get_fallback_chain("llm", ["openai", "claude", "gemini"])
"""

import logging
from typing import Optional
from backend.services.providers.base import (
    LLMProvider,
    TTSProvider,
    STTProvider,
    ProviderType,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Barcha provayderlarni ro'yxatga olish va boshqarish."""

    def __init__(self):
        self._llm_providers: dict[str, LLMProvider] = {}
        self._tts_providers: dict[str, TTSProvider] = {}
        self._stt_providers: dict[str, STTProvider] = {}

    # ─────────────────────────────────────────────────────────────────
    # Register
    # ─────────────────────────────────────────────────────────────────

    def register_llm(self, name: str, provider: LLMProvider):
        """LLM provayderni ro'yxatga olish."""
        self._llm_providers[name] = provider
        logger.info(f"Registered LLM provider: {name}")

    def register_tts(self, name: str, provider: TTSProvider):
        """TTS provayderni ro'yxatga olish."""
        self._tts_providers[name] = provider
        logger.info(f"Registered TTS provider: {name}")

    def register_stt(self, name: str, provider: STTProvider):
        """STT provayderni ro'yxatga olish."""
        self._stt_providers[name] = provider
        logger.info(f"Registered STT provider: {name}")

    # ─────────────────────────────────────────────────────────────────
    # Get
    # ─────────────────────────────────────────────────────────────────

    def get_llm(self, name: str) -> Optional[LLMProvider]:
        """LLM provayderni olish."""
        return self._llm_providers.get(name)

    def get_tts(self, name: str) -> Optional[TTSProvider]:
        """TTS provayderni olish."""
        return self._tts_providers.get(name)

    def get_stt(self, name: str) -> Optional[STTProvider]:
        """STT provayderni olish."""
        return self._stt_providers.get(name)

    def list_llm(self) -> list[str]:
        """Barcha LLM provayderlar nomi."""
        return list(self._llm_providers.keys())

    def list_tts(self) -> list[str]:
        """Barcha TTS provayderlar nomi."""
        return list(self._tts_providers.keys())

    def list_stt(self) -> list[str]:
        """Barcha STT provayderlar nomi."""
        return list(self._stt_providers.keys())

    # ─────────────────────────────────────────────────────────────────
    # Health
    # ─────────────────────────────────────────────────────────────────

    def health_check_all(self) -> dict:
        """Barcha provayderlarning salomatligini tekshirish."""
        results = {}

        for name, provider in self._llm_providers.items():
            try:
                health = provider.health_check()
                results[f"llm:{name}"] = {
                    "status": health.status.value,
                    "success_rate": health.success_rate,
                    "avg_latency_ms": health.avg_latency_ms,
                }
            except Exception as e:
                results[f"llm:{name}"] = {"status": "error", "error": str(e)}

        for name, provider in self._tts_providers.items():
            try:
                health = provider.health_check()
                results[f"tts:{name}"] = {
                    "status": health.status.value,
                    "success_rate": health.success_rate,
                    "avg_latency_ms": health.avg_latency_ms,
                }
            except Exception as e:
                results[f"tts:{name}"] = {"status": "error", "error": str(e)}

        for name, provider in self._stt_providers.items():
            try:
                health = provider.health_check()
                results[f"stt:{name}"] = {
                    "status": health.status.value,
                    "success_rate": health.success_rate,
                    "avg_latency_ms": health.avg_latency_ms,
                }
            except Exception as e:
                results[f"stt:{name}"] = {"status": "error", "error": str(e)}

        return results

    def get_available_providers(self, provider_type: ProviderType) -> list[str]:
        """Mavjud provayderlar ro'yxati (faqat Healthy/Unknown)."""
        available = []

        if provider_type == ProviderType.LLM:
            for name, provider in self._llm_providers.items():
                if provider.is_available():
                    available.append(name)
        elif provider_type == ProviderType.TTS:
            for name, provider in self._tts_providers.items():
                if provider.is_available():
                    available.append(name)
        elif provider_type == ProviderType.STT:
            for name, provider in self._stt_providers.items():
                if provider.is_available():
                    available.append(name)

        return available


# ─────────────────────────────────────────────────────────────────────
# Global registry (singleton)
# ─────────────────────────────────────────────────────────────────────

_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """Global registry olish (singleton)."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
