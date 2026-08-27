"""
backend.services.tts — TTS provider abstraction layer.

Tez boshlash:
    from backend.services.tts.factory import get_provider
    provider = get_provider()          # TTS_PROVIDER env asosida
    ok = provider.synthesize("Salom", "/tmp/out.wav")
"""
from backend.services.tts.base import TTSProvider, SynthesisResult
from backend.services.tts.factory import get_provider, get_fallback_provider, list_providers

__all__ = [
    "TTSProvider",
    "SynthesisResult",
    "get_provider",
    "get_fallback_provider",
    "list_providers",
]
