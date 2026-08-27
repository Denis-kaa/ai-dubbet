"""
Cohere Provider — Cohere AI provayderi (arzon va sifatli).

Afzalliklari:
- Arzon (Command R narxi: $0.15/1M input, $0.60/1M output)
- Tez inference
- Yaxshi tarjima sifati
- RAG (Retrieval-Augmented Generation) qo'llab-quvvatlaydi
- Multilingual (100+ tillar)

Models:
- command-r-plus: Eng kuchli (sifat yuqori)
- command-r: O'rtacha (tezroq)
- command-light: Eng tez (arzonroq)

API docs: https://docs.cohere.com/
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


class CohereLLMProvider(LLMProvider):
    """Cohere AI provayderi."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "command-r-plus",
        light_model: str = "command-r",
    ):
        super().__init__("cohere")
        self.api_key = api_key
        self.model = model
        self.light_model = light_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import cohere
            self._client = cohere.Client(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            client = self._get_client()
            start = time.monotonic()
            client.generate(
                model=self.light_model,
                prompt="ping",
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

            # Cohere uchun prompt format
            prompt = f"Translate the following text from {source_lang} to {target_lang}:\n\n{text}"
            if system_prompt:
                prompt = f"{system_prompt}\n\n{prompt}"

            start = time.monotonic()
            response = client.generate(
                model=self.model,
                prompt=prompt,
                temperature=0.45,
                max_tokens=4096,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.generations[0].text.strip(),
                provider="cohere",
                model=self.model,
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="cohere",
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

            # Convert OpenAI format to Cohere format
            # Cohere uses chat API for newer models
            chat_history = []
            preamble = ""

            for msg in messages:
                if msg["role"] == "system":
                    preamble = msg["content"]
                elif msg["role"] == "user":
                    chat_history.append({"role": "USER", "message": msg["content"]})
                elif msg["role"] == "assistant":
                    chat_history.append({"role": "CHATBOT", "message": msg["content"]})

            # Get the last user message (query)
            query = chat_history.pop()["message"] if chat_history else ""

            start = time.monotonic()
            response = client.chat(
                model=model or self.model,
                message=query,
                chat_history=chat_history,
                preamble=preamble,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.text,
                provider="cohere",
                model=model or self.model,
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="cohere",
            )

    def embed(
        self,
        texts: list[str],
        input_type: str = "search_document",
    ) -> ProviderResponse:
        """
        Matnlarni embedding qilish (RAG uchun).

        Args:
            texts: Embedding qilinadigan matnlar
            input_type: "search_document" | "search_query" | "classification" | "clustering"

        Returns:
            ProviderResponse with embeddings as data
        """
        try:
            client = self._get_client()
            start = time.monotonic()
            response = client.embed(
                texts=texts,
                input_type=input_type,
                model="embed-english-v3.0",
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.embeddings,
                provider="cohere",
                model="embed-english-v3.0",
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="cohere",
            )

    def summarize(
        self,
        text: str,
        length: str = "medium",
        format: str = "paragraph",
    ) -> ProviderResponse:
        """
        Matnni qisqartirish.

        Args:
            text: Qisqartiriladigan matn
            length: "short" | "medium" | "long"
            format: "paragraph" | "bullets"

        Returns:
            ProviderResponse with summary as data
        """
        try:
            client = self._get_client()
            start = time.monotonic()
            response = client.summarize(
                text=text,
                length=length,
                format=format,
                model=self.model,
            )
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data=response.summary,
                provider="cohere",
                model=self.model,
                latency_ms=latency,
            )
        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="cohere",
            )
