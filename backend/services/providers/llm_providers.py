"""
LLM Provider Implementations — OpenAI, Claude, Mistral, DeepSeek, Groq, Cohere.

Har bir provayder:
- is_available() — API kalit mavjudligini tekshirish
- health_check() — salomatlik tekshiruvi
- translate() — tarjima
- complete() — chat completion
"""

import time
import logging
from typing import Optional
from backend.services.providers.base import (
    LLMProvider,
    ProviderResponse,
    ProviderStatus,
    ProviderHealth,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI
# ─────────────────────────────────────────────────────────────────────────────

class OpenAILLMProvider(LLMProvider):
    """OpenAI GPT provayderi."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        light_model: str = "gpt-4o-mini",
    ):
        super().__init__("openai")
        self.api_key = api_key
        self.model = model
        self.light_model = light_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            client = self._get_client()
            start = time.monotonic()
            client.chat.completions.create(
                model=self.light_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                avg_latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        system_prompt: str = "",
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})

            start = time.monotonic()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.45,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="openai",
                model=self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="openai",
            )

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            start = time.monotonic()
            response = client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="openai",
                model=model or self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="openai",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic Claude
# ─────────────────────────────────────────────────────────────────────────────

class ClaudeLLMProvider(LLMProvider):
    """Anthropic Claude provayderi."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-3-5-haiku-20241022",
    ):
        super().__init__("claude")
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            client = self._get_client()
            start = time.monotonic()
            client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                avg_latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        system_prompt: str = "",
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            start = time.monotonic()
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt or "You are a professional translator.",
                messages=[{"role": "user", "content": text}],
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.content[0].text,
                provider="claude",
                model=self.model,
                latency_ms=latency,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="claude",
            )

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            # Convert OpenAI format to Claude format
            system_msg = ""
            claude_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                else:
                    claude_messages.append(msg)

            start = time.monotonic()
            response = client.messages.create(
                model=model or self.model,
                max_tokens=max_tokens,
                system=system_msg,
                messages=claude_messages,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.content[0].text,
                provider="claude",
                model=model or self.model,
                latency_ms=latency,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="claude",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Mistral
# ─────────────────────────────────────────────────────────────────────────────

class MistralLLMProvider(LLMProvider):
    """Mistral AI provayderi."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "mistral-small-latest",
    ):
        super().__init__("mistral")
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from mistralai import Mistral
            self._client = Mistral(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            client = self._get_client()
            start = time.monotonic()
            client.chat.complete(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                avg_latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        system_prompt: str = "",
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})

            start = time.monotonic()
            response = client.chat.complete(
                model=self.model,
                messages=messages,
                temperature=0.45,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="mistral",
                model=self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="mistral",
            )

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            start = time.monotonic()
            response = client.chat.complete(
                model=model or self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="mistral",
                model=model or self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="mistral",
            )


# ─────────────────────────────────────────────────────────────────────────────
# DeepSeek
# ─────────────────────────────────────────────────────────────────────────────

class DeepSeekLLMProvider(LLMProvider):
    """DeepSeek AI provayderi (arzon va tez)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
    ):
        super().__init__("deepseek")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            client = self._get_client()
            start = time.monotonic()
            client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                avg_latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        system_prompt: str = "",
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})

            start = time.monotonic()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.45,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="deepseek",
                model=self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="deepseek",
            )

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            start = time.monotonic()
            response = client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="deepseek",
                model=model or self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="deepseek",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Groq (tez inference)
# ─────────────────────────────────────────────────────────────────────────────

class GroqLLMProvider(LLMProvider):
    """Groq provayderi (eng tez inference — LPU chip)."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.1-8b-instant",
    ):
        super().__init__("groq")
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            client = self._get_client()
            start = time.monotonic()
            client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            latency = (time.monotonic() - start) * 1000
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                avg_latency_ms=latency,
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "uz",
        system_prompt: str = "",
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})

            start = time.monotonic()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.45,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="groq",
                model=self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="groq",
            )

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProviderResponse:
        try:
            client = self._get_client()
            start = time.monotonic()
            response = client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.choices[0].message.content,
                provider="groq",
                model=model or self.model,
                latency_ms=latency,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="groq",
            )
