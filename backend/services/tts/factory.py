"""
TTS Provider Factory — TTS_PROVIDER env asosida to'g'ri providerni yaratadi.

Ishlatish:
    from backend.services.tts.factory import get_provider, get_fallback_provider

    provider = get_provider()          # settings.TTS_PROVIDER asosida
    provider = get_provider("azure")   # aniq provider
    fallback = get_fallback_provider() # har doim Edge (bepul)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.config import get_settings

if TYPE_CHECKING:
    from backend.services.tts.base import TTSProvider

logger = logging.getLogger(__name__)
settings = get_settings()

_REGISTRY: dict[str, type] = {}


def _load_registry() -> dict[str, type]:
    global _REGISTRY
    if _REGISTRY:
        return _REGISTRY

    from backend.services.tts.elevenlabs_provider import ElevenLabsProvider
    from backend.services.tts.azure_provider import AzureProvider
    from backend.services.tts.edge_provider import EdgeProvider
    from backend.services.tts.openai_provider import OpenAIProvider
    from backend.services.tts.gemini_provider import GeminiProvider
    from backend.services.tts.uzbekvoice_provider import UzbekVoiceProvider

    _REGISTRY = {
        "elevenlabs": ElevenLabsProvider,
        "azure":      AzureProvider,
        "edge":       EdgeProvider,
        "openai":     OpenAIProvider,
        "gemini":     GeminiProvider,
        "uzbekvoice": UzbekVoiceProvider,
    }
    return _REGISTRY


def get_provider(name: str | None = None) -> "TTSProvider":
    """
    TTS provider instansini qaytaradi.

    Args:
        name: "elevenlabs" | "azure" | "edge" | "openai" | "gemini" | None
              None bo'lsa settings.TTS_PROVIDER ishlatiladi.
    """
    registry = _load_registry()
    chosen = (name or settings.TTS_PROVIDER or "elevenlabs").lower().strip()

    if chosen not in registry:
        logger.warning(
            f"Noma'lum TTS_PROVIDER='{chosen}'. "
            f"Mavjudlar: {list(registry.keys())}. Edge ga o'tildi."
        )
        chosen = "edge"

    cls = registry[chosen]
    logger.debug(f"TTS provider: {chosen}")
    return cls()


def get_fallback_provider() -> "TTSProvider":
    """Asosiy provider vaqtinchalik xatolik bilan ishlamasa ishlatiladi.
    settings.TTS_FALLBACK_PROVIDER orqali sozlanadi (default: "edge" — bepul)."""
    registry = _load_registry()
    chosen = (settings.TTS_FALLBACK_PROVIDER or "edge").lower().strip()
    if chosen not in registry:
        logger.warning(f"Noma'lum TTS_FALLBACK_PROVIDER='{chosen}'. Edge ga o'tildi.")
        chosen = "edge"
    return registry[chosen]()


def list_providers() -> list[str]:
    """Barcha ro'yxatdan o'tgan provider nomlarini qaytaradi."""
    return list(_load_registry().keys())
