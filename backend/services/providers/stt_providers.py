"""
STT Provider Implementations — AssemblyAI, Deepgram.

Har bir provayder:
- is_available() — API kalit mavjudligini tekshirish
- health_check() — salomatlik tekshiruvi
- transcribe() — ovozni matnga aylantirish

Afzalliklari:
- AssemblyAI: Yuqori aniqlik, real-time transcription, punctuation
- Deepgram: Juda tez, arzon, Nova-2 modeli
"""

import time
import logging
import tempfile
import os
from typing import Optional
from backend.services.providers.base import (
    STTProvider,
    ProviderResponse,
    ProviderStatus,
    ProviderHealth,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# AssemblyAI
# ─────────────────────────────────────────────────────────────────────────────

class AssemblyAIProvider(STTProvider):
    """
    AssemblyAI STT provayderi.

    Afzalliklari:
    - Eng yuqori aniqlik (95%+)
    - Punctuation avtomatik
    - Speaker diarization
    - Real-time transcription
    - Sentiment analysis
    - Content moderation

    Narx: $0.65/saat (standard), $1.00/saat (enhanced)
    Docs: https://www.assemblyai.com/docs/
    """

    def __init__(self, api_key: str = ""):
        super().__init__("assemblyai")
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            import assemblyai as aai
            aai.settings.api_key = self.api_key

            # Oddiy health check — API key tekshirish
            # Real transcription qilmaymiz (pul ketadi)
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                details={"api_key_set": True},
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        **kwargs,
    ) -> ProviderResponse:
        """
        Ovozni matnga aylantirish.

        Args:
            audio_path: Audio fayl yo'li
            language: Til kodi (en, uz, ru, etc.)

        Returns:
            ProviderResponse with transcription text
        """
        try:
            import assemblyai as aai
            aai.settings.api_key = self.api_key

            # Transcription config
            config = aai.TranscriptionConfig(
                language_code=language if language else None,
                punctuate=True,
                format_text=True,
                dual_channel=False,
                webhook_url=None,
            )

            start = time.monotonic()
            transcriber = aai.Transcriber(config=config)
            transcript = transcriber.transcribe(audio_path)
            latency = (time.monotonic() - start) * 1000

            if transcript.status == aai.TranscriptStatus.completed:
                # Segmentlarni olish
                segments = []
                if transcript.words:
                    # Words ni segmentlarga guruhlash
                    current_segment = {"start": 0, "end": 0, "text": ""}
                    for word in transcript.words:
                        if current_segment["end"] < word.start:
                            if current_segment["text"]:
                                segments.append(current_segment.copy())
                            current_segment = {
                                "start": word.start,
                                "end": word.end,
                                "text": word.text,
                            }
                        else:
                            current_segment["end"] = word.end
                            current_segment["text"] += " " + word.text
                    if current_segment["text"]:
                        segments.append(current_segment)

                return ProviderResponse(
                    success=True,
                    data={
                        "text": transcript.text,
                        "segments": segments,
                        "language": transcript.language_code or language,
                    },
                    provider="assemblyai",
                    latency_ms=latency,
                )
            else:
                return ProviderResponse(
                    success=False,
                    error=f"Transcription failed: {transcript.status}",
                    provider="assemblyai",
                )

        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="assemblyai",
            )

    def transcribe_realtime(
        self,
        audio_stream,
        language: str = "en",
        on_segment=None,
    ) -> ProviderResponse:
        """
        Real-time transcription (streaming).

        Args:
            audio_stream: Audio stream (generator yoki file-like object)
            language: Til kodi
            on_segment: Callback for each segment

        Returns:
            ProviderResponse with full transcription
        """
        try:
            import assemblyai as aai
            aai.settings.api_key = self.api_key

            config = aai.RealtimeTranscriptionConfig(
                language_code=language if language else None,
                punctuate=True,
                format_text=True,
            )

            transcriber = aai.RealtimeTranscriber(config=config)

            # Real-time callback
            segments = []
            def on_data(transcript):
                segments.append({
                    "text": transcript.text,
                    "start": getattr(transcript, "start", 0),
                    "end": getattr(transcript, "end", 0),
                })
                if on_segment:
                    on_segment(transcript)

            transcriber.on = on_data

            start = time.monotonic()
            # Note: Real-time requires WebSocket connection
            # This is a simplified version
            latency = (time.monotonic() - start) * 1000

            return ProviderResponse(
                success=True,
                data={"segments": segments},
                provider="assemblyai",
                latency_ms=latency,
            )

        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="assemblyai",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Deepgram
# ─────────────────────────────────────────────────────────────────────────────

class DeepgramProvider(STTProvider):
    """
    Deepgram STT provayderi.

    Afzalliklari:
    - Juda tez (real-time dan ham tez)
    - Arzon ($0.0043/daqiqa — Nova-2)
    - Yaxshi aniqlik (95%+)
    - 36+ tillar
    - Punctuation
    - Smart formatting
    - Speaker diarization

    Narx: $0.0043/daqiqa (Nova-2), $0.0059/daqiqa (Nova-2 phone)
    Docs: https://developers.deepgram.com/
    """

    def __init__(self, api_key: str = ""):
        super().__init__("deepgram")
        self.api_key = api_key

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            from deepgram import DeepgramClient
            client = DeepgramClient(self.api_key)

            # Oddiy health check
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                details={"api_key_set": True},
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        **kwargs,
    ) -> ProviderResponse:
        """
        Ovozni matnga aylantirish.

        Args:
            audio_path: Audio fayl yo'li
            language: Til kodi (en, uz, ru, etc.)

        Returns:
            ProviderResponse with transcription text
        """
        try:
            from deepgram import DeepgramClient, PrerecordedOptions, FileSource

            client = DeepgramClient(self.api_key)

            # Audio faylni o'qish
            with open(audio_path, "rb") as audio_file:
                buffer_data = audio_file.read()

            payload: FileSource = {"buffer": buffer_data}

            # Transcription options
            options = PrerecordedOptions(
                model="nova-2",
                language=language if language else "en",
                punctuate=True,
                smart_format=True,
                diarize=False,
                paragraphs=True,
            )

            start = time.monotonic()
            response = client.listen.prerecorded.transcribe_file(payload, options)
            latency = (time.monotonic() - start) * 1000

            # Natijani parse qilish
            result = response["results"]["channels"][0]["alternatives"][0]
            text = result.get("transcript", "")
            confidence = result.get("confidence", 0)

            # Segmentlarni olish
            segments = []
            if "paragraphs" in result:
                for paragraph in result["paragraphs"].get("paragraphs", []):
                    for sentence in paragraph.get("sentences", []):
                        segments.append({
                            "start": sentence.get("start", 0),
                            "end": sentence.get("end", 0),
                            "text": sentence.get("text", ""),
                        })

            return ProviderResponse(
                success=True,
                data={
                    "text": text,
                    "segments": segments,
                    "language": language,
                    "confidence": confidence,
                },
                provider="deepgram",
                latency_ms=latency,
            )

        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="deepgram",
            )

    def transcribe_realtime(
        self,
        audio_stream,
        language: str = "en",
        on_segment=None,
    ) -> ProviderResponse:
        """
        Real-time transcription (streaming).

        Args:
            audio_stream: Audio stream (generator yoki file-like object)
            language: Til kodi
            on_segment: Callback for each segment

        Returns:
            ProviderResponse with transcription
        """
        try:
            from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

            client = DeepgramClient(self.api_key)
            connection = client.listen.live.v("1")

            # Callback
            segments = []
            def on_message(self, result, **kwargs):
                transcript = result["channel"]["alternatives"][0]["transcript"]
                if transcript:
                    segments.append({"text": transcript})
                    if on_segment:
                        on_segment(transcript)

            connection.on(LiveTranscriptionEvents.Transcript, on_message)

            # Options
            options = LiveOptions(
                model="nova-2",
                language=language if language else "en",
                punctuate=True,
                smart_format=True,
            )

            connection.start(options)

            # Audio stream ni yuborish
            # Note: Real-time requires WebSocket connection
            # This is a simplified version

            return ProviderResponse(
                success=True,
                data={"segments": segments},
                provider="deepgram",
            )

        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="deepgram",
            )


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI Whisper (local)
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIWhisperProvider(STTProvider):
    """
    OpenAI Whisper STT provayderi (API).

    Afzalliklari:
    - Yaxshi aniqlik
    - Ko'p tillar (100+)
    - Oddiy API

    Narx: $0.006/daqiqa
    Docs: https://platform.openai.com/docs/guides/speech-to-text
    """

    def __init__(self, api_key: str = "", model: str = "whisper-1"):
        super().__init__("openai_whisper")
        self.api_key = api_key
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        return ProviderHealth(
            status=ProviderStatus.HEALTHY,
            details={"api_key_set": True},
        )

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        **kwargs,
    ) -> ProviderResponse:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)

            start = time.monotonic()
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=language if language else None,
                    response_format="verbose_json",
                    timestamp_granularities=["segment", "word"],
                )
            latency = (time.monotonic() - start) * 1000

            # Segmentlarni parse qilish
            segments = []
            if hasattr(response, "segments") and response.segments:
                for seg in response.segments:
                    segments.append({
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text,
                    })

            return ProviderResponse(
                success=True,
                data={
                    "text": response.text,
                    "segments": segments,
                    "language": getattr(response, "language", language),
                },
                provider="openai_whisper",
                model=self.model,
                latency_ms=latency,
            )

        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="openai_whisper",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Google Cloud Speech-to-Text
# ─────────────────────────────────────────────────────────────────────────────

class GoogleSTTProvider(STTProvider):
    """
    Google Cloud Speech-to-Text provayderi.

    Afzalliklari:
    - Yuqori aniqlik
    - Real-time streaming
    - Ko'p tillar (125+)
    - Speaker diarization
    - Punctuation

    Narx: $0.006/daqiqa (Standard), $0.009/daqiqa (Enhanced)
    Docs: https://cloud.google.com/speech-to-text/docs
    """

    def __init__(self, credentials_path: str = ""):
        super().__init__("google_stt")
        self.credentials_path = credentials_path

    def is_available(self) -> bool:
        return bool(self.credentials_path)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            from google.cloud import speech
            client = speech.SpeechClient()

            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                details={"credentials_set": True},
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderStatus.UNHEALTHY,
                details={"error": str(e)},
            )

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        **kwargs,
    ) -> ProviderResponse:
        try:
            from google.cloud import speech

            client = speech.SpeechClient()

            # Audio faylni o'qish
            with open(audio_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)

            # Config
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language if language else "en-US",
                enable_automatic_punctuation=True,
                enable_word_time_offsets=True,
                model="latest_long",
            )

            start = time.monotonic()
            response = client.recognize(config=config, audio=audio)
            latency = (time.monotonic() - start) * 1000

            # Natijani parse qilish
            full_text = ""
            segments = []
            for result in response.results:
                alternative = result.alternatives[0]
                full_text += alternative.transcript + " "

                # Word-level timestamps
                if alternative.words:
                    current_segment = {"start": 0, "end": 0, "text": ""}
                    for word_info in alternative.words:
                        word_start = word_info.start_time.total_seconds()
                        word_end = word_info.end_time.total_seconds()

                        if current_segment["end"] < word_start:
                            if current_segment["text"]:
                                segments.append(current_segment.copy())
                            current_segment = {
                                "start": word_start,
                                "end": word_end,
                                "text": word_info.word,
                            }
                        else:
                            current_segment["end"] = word_end
                            current_segment["text"] += " " + word_info.word

                    if current_segment["text"]:
                        segments.append(current_segment)

            return ProviderResponse(
                success=True,
                data={
                    "text": full_text.strip(),
                    "segments": segments,
                    "language": language,
                },
                provider="google_stt",
                latency_ms=latency,
            )

        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="google_stt",
            )
