"""
Fallback Chain — provayderlar ketma-ketligi bilan avtomatik fallback.

Usage:
    chain = FallbackChain([
        ("openai", openai_provider),
        ("claude", claude_provider),
        ("gemini", gemini_provider),
    ])

    # Birinchi ishlaydigan provayderni topish
    result = chain.translate("Hello", source_lang="en", target_lang="uz")

    # Agar birinchisi xato bersa — keyingisiga o'tadi
    # Agar hammasi xato bersa — oxirgi xatoni qaytaradi
"""

import time
import logging
from typing import Callable, Any, Optional
from backend.services.providers.base import (
    LLMProvider,
    TTSProvider,
    STTProvider,
    ProviderResponse,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class FallbackChain:
    """
    Provayderlar ketma-ketligi bilan avtomatik fallback.

    Agar birinchi provayder xato bersa — keyingisiga o'tadi.
    Agar hammasi xato bersa — oxirgi xatoni qaytaradi.
    """

    def __init__(self, providers: list[tuple[str, Any]]):
        """
        Args:
            providers: [(name, provider), ...] — ketma-ketlikda
        """
        self.providers = providers
        self._last_used_index = 0

    def _get_next_provider(self) -> tuple[str, Any]:
        """Keyingi ishlaydigan provayderni olish (round-robin)."""
        if not self.providers:
            raise ValueError("No providers in fallback chain")

        # Round-robin: har safar keyingi provayderdan boshlash
        start_index = self._last_used_index
        for i in range(len(self.providers)):
            index = (start_index + i) % len(self.providers)
            name, provider = self.providers[index]

            # Provayder mavjudligini tekshirish
            if provider.is_available():
                self._last_used_index = (index + 1) % len(self.providers)
                return name, provider

        # Hammasi band — birinchisini qaytarish
        self._last_used_index = (start_index + 1) % len(self.providers)
        return self.providers[0]

    def execute_with_fallback(
        self,
        func_name: str,
        **kwargs,
    ) -> ProviderResponse:
        """
        Fallback bilan bajarish.

        Args:
            func_name: Chaqiriladigan funksiya nomi (masalan "translate")
            **kwargs: Funksiya argumentlari

        Returns:
            ProviderResponse — birinchi muvaffaqiyatli natija yoki oxirgi xato
        """
        last_error = None

        for name, provider in self.providers:
            if not provider.is_available():
                logger.debug(f"Skipping {name}: not available")
                continue

            try:
                func = getattr(provider, func_name)
                if not func:
                    logger.warning(f"Provider {name} has no method {func_name}")
                    continue

                start_time = time.monotonic()
                result = func(**kwargs)
                latency_ms = (time.monotonic() - start_time) * 1000

                if result.success:
                    result.provider = name
                    result.latency_ms = latency_ms
                    provider._record_request(latency_ms, True)
                    logger.info(f"Success with {name} ({latency_ms:.0f}ms)")
                    return result
                else:
                    logger.warning(f"Provider {name} returned error: {result.error}")
                    last_error = result.error
                    provider._record_request(latency_ms, False)

            except Exception as e:
                logger.warning(f"Provider {name} exception: {e}")
                last_error = str(e)
                provider._record_request(0, False)

        # Hammasi xato — oxirgi xatoni qaytarish
        return ProviderResponse(
            success=False,
            error=f"All providers failed. Last error: {last_error}",
            provider="fallback_chain",
        )


class LLMFallbackChain(FallbackChain):
    """LLM uchun fallback chain."""

    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        system_prompt: str = "",
        **kwargs,
    ) -> ProviderResponse:
        return self.execute_with_fallback(
            "translate",
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            system_prompt=system_prompt,
            **kwargs,
        )

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        return self.execute_with_fallback(
            "complete",
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )


class TTSFallbackChain(FallbackChain):
    """TTS uchun fallback chain."""

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str = None,
        **kwargs,
    ) -> ProviderResponse:
        return self.execute_with_fallback(
            "synthesize",
            text=text,
            output_path=output_path,
            voice_name=voice_name,
            **kwargs,
        )


class STTFallbackChain(FallbackChain):
    """STT uchun fallback chain."""

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        **kwargs,
    ) -> ProviderResponse:
        return self.execute_with_fallback(
            "transcribe",
            audio_path=audio_path,
            language=language,
            **kwargs,
        )
