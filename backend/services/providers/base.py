"""
Base classes for Multi-Provider System.

All providers inherit from these base classes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import time
import logging

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """Provider turlari."""
    LLM = "llm"           # Matn modeli (tarjima, tahlil)
    TTS = "tts"           # Matndan ovozga
    STT = "stt"           # Ovozdan matnga (transcription)


class ProviderStatus(Enum):
    """Provider holati."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProviderResponse:
    """Provayder javobi."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    provider: str = ""
    model: str = ""
    latency_ms: float = 0
    tokens_used: int = 0
    cost_usd: float = 0
    cached: bool = False


@dataclass
class ProviderHealth:
    """Provayder salomatligi."""
    status: ProviderStatus
    last_check: float = 0
    success_rate: float = 1.0  # 0.0 - 1.0
    avg_latency_ms: float = 0
    error_count: int = 0
    total_requests: int = 0
    details: dict = field(default_factory=dict)


class BaseProvider(ABC):
    """Barcha provayderlar uchun asos sinf."""

    def __init__(self, name: str, provider_type: ProviderType):
        self.name = name
        self.provider_type = provider_type
        self.health = ProviderHealth(status=ProviderStatus.UNKNOWN)
        self._request_count = 0
        self._error_count = 0
        self._total_latency = 0.0

    @abstractmethod
    def is_available(self) -> bool:
        """Provayder mavjudligini tekshirish (API kalit mavjudligi)."""
        pass

    @abstractmethod
    def health_check(self) -> ProviderHealth:
        """Salomatlik tekshiruvi."""
        pass

    def _record_request(self, latency_ms: float, success: bool):
        """So'rov natijasini qayd etish."""
        self._request_count += 1
        self._total_latency += latency_ms

        if not success:
            self._error_count += 1

        # Health update
        self.health.total_requests = self._request_count
        self.health.error_count = self._error_count
        self.health.success_rate = 1.0 - (self._error_count / self._request_count)
        self.health.avg_latency_ms = self._total_latency / self._request_count
        self.health.last_check = time.time()

        if self.health.success_rate >= 0.95:
            self.health.status = ProviderStatus.HEALTHY
        elif self.health.success_rate >= 0.80:
            self.health.status = ProviderStatus.DEGRADED
        else:
            self.health.status = ProviderStatus.UNHEALTHY


class LLMProvider(BaseProvider):
    """LLM provayderning asos sinfi (tarjima, tahlil, generatsiya)."""

    def __init__(self, name: str):
        super().__init__(name, ProviderType.LLM)

    @abstractmethod
    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        system_prompt: str = "",
        **kwargs,
    ) -> ProviderResponse:
        """Tarjima qilish."""
        pass

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        """Chat completion."""
        pass


class TTSProvider(BaseProvider):
    """TTS provayderning asos sinfi (matndan ovozga)."""

    def __init__(self, name: str):
        super().__init__(name, ProviderType.TTS)

    @abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str = None,
        **kwargs,
    ) -> ProviderResponse:
        """Ovoz yaratish."""
        pass

    @abstractmethod
    def list_voices(self, language: str = None) -> list[dict]:
        """Mavjud ovozlar ro'yxati."""
        pass


class STTProvider(BaseProvider):
    """STT provayderning asos sinfi (ovozdan matnga / transcription)."""

    def __init__(self, name: str):
        super().__init__(name, ProviderType.STT)

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        **kwargs,
    ) -> ProviderResponse:
        """Ovozni matnga aylantirish."""
        pass
