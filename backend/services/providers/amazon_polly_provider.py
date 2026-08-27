"""
Amazon Polly TTS Provider — AWS TTS service.

Afzalliklari:
- Professional sifat
- Ko'p tillar (60+)
- Neural voices (yangi avlod)
- SSML qo'llab-quvvatlaydi
- Arzon ($0.004/1000 chars standard, $0.016/1000 neural)

Models/Engines:
- standard: Arzon, tez
- neural: Sifatli, sekinroq
- long-form: Uzoq matnlar uchun

O'zbek tillari:
- O'zbek (uz-UZ) — faqat standard engine
- Filiz voice (erkak/ayol)

API docs: https://docs.aws.amazon.com/polly/
Pricing: https://aws.amazon.com/polly/pricing/
"""

import time
import logging
import boto3
from typing import Optional
from backend.services.providers.base import (
    TTSProvider,
    ProviderResponse,
    ProviderStatus,
    ProviderHealth,
)

logger = logging.getLogger(__name__)


class AmazonPollyProvider(TTSProvider):
    """
    Amazon Polly TTS provayderi.

    Afzalliklari:
    - AWS ecosystem bilan integratsiya
    - Neural voices (eng tabiiy ovoz)
    - SSML (Speech Synthesis Markup Language)
    - Real-time streaming
    - Batch processing
    - Pronunciation lexicon

    Narx:
    - Standard: $0.004/1000 chars (~$0.04/daqiqa)
    - Neural: $0.016/1000 chars (~$0.16/daqiqa)
    - Long-form: $0.016/1000 chars

    O'zbek ovozlari:
    - Filiz (standard engine only)
    """

    # O'zbek ovozlari (standard engine)
    UZBEK_VOICES = {
        "male": "Filiz",    # O'zbek erkak ovozi
        "female": "Filiz",  # O'zbek ayol ovozi (hali yo'q, Filiz ishlatiladi)
    }

    # Neural ovozlar (ingliz tili uchun)
    NEURAL_VOICES = {
        "en-US": {"male": "Matthew", "female": "Joanna"},
        "en-GB": {"male": "Brian", "female": "Amy"},
        "ru-RU": {"male": "Maxim", "female": "Tatyana"},
        "uz-UZ": {"male": "Filiz", "female": "Filiz"},
    }

    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        voice_male: str = "Filiz",
        voice_female: str = "Filiz",
        engine: str = "standard",  # standard | neural | long-form
    ):
        super().__init__("amazon_polly")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.voice_male = voice_male
        self.voice_female = voice_female
        self.engine = engine
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "polly",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def health_check(self) -> ProviderHealth:
        if not self.is_available():
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)

        try:
            client = self._get_client()
            # Oddiy health check — voice list olish
            start = time.monotonic()
            client.describe_voices(LanguageCode="en-US")
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

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str = None,
        **kwargs,
    ) -> ProviderResponse:
        """
        Matnni ovozga aylantirish.

        Args:
            text: Sintez qilinadigan matn
            output_path: Chiqish fayl yo'li (.mp3 yoki .wav)
            voice_name: Ovoz nomi (masalan "Filiz")

        Returns:
            ProviderResponse with audio file path
        """
        try:
            client = self._get_client()

            # Ovozni tanlash
            if voice_name:
                voice_id = voice_name
            else:
                voice_id = self.voice_male  # Default

            # Engine tekshirish (O'zbek faqat standard)
            engine = self.engine
            if "uz" in (voice_name or "").lower() or voice_id == "Filiz":
                engine = "standard"  # O'zbek faqat standard

            # SSML yaratish (kerak bo'lsa)
            ssml_text = None
            if kwargs.get("use_ssml", False):
                ssml_text = self._wrap_ssml(text, **kwargs)

            start = time.monotonic()

            if ssml_text:
                # SSML bilan
                response = client.synthesize_speech(
                    OutputFormat="mp3",
                    Text=ssml_text,
                    TextType="ssml",
                    VoiceId=voice_id,
                    Engine=engine,
                )
            else:
                # Oddiy matn
                response = client.synthesize_speech(
                    OutputFormat="mp3",
                    Text=text,
                    TextType="text",
                    VoiceId=voice_id,
                    Engine=engine,
                )

            latency = (time.monotonic() - start) * 1000

            # Audio stream'ni faylga yozish
            if "AudioStream" in response:
                with open(output_path, "wb") as f:
                    f.write(response["AudioStream"].read())

                # audio_duration ni hisoblash
                duration = self._get_audio_duration(output_path)

                return ProviderResponse(
                    success=True,
                    data={
                        "path": output_path,
                        "duration": duration,
                        "voice": voice_id,
                        "engine": engine,
                    },
                    provider="amazon_polly",
                    latency_ms=latency,
                )
            else:
                return ProviderResponse(
                    success=False,
                    error="No AudioStream in response",
                    provider="amazon_polly",
                )

        except Exception as e:
            return ProviderResponse(
                success=False,
                error=str(e),
                provider="amazon_polly",
            )

    def _wrap_ssml(
        self,
        text: str,
        pitch: str = "+0%",
        rate: str = "+0%",
        volume: str = "+0%",
        **kwargs,
    ) -> str:
        """SSML wrap qilish."""
        return f"""<speak>
            <prosody pitch="{pitch}" rate="{rate}" volume="{volume}">
                {text}
            </prosody>
        </speak>"""

    def _get_audio_duration(self, audio_path: str) -> float:
        """Audio davomiyligini olish (soniya)."""
        try:
            import subprocess
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True, text=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def list_voices(self, language: str = None) -> list[dict]:
        """Mavjud ovozlar ro'yxati."""
        try:
            client = self._get_client()
            kwargs = {}
            if language:
                kwargs["LanguageCode"] = language

            response = client.describe_voices(**kwargs)
            voices = []

            for voice in response.get("Voices", []):
                voices.append({
                    "id": voice["Id"],
                    "name": voice["Name"],
                    "language": voice["LanguageCode"],
                    "gender": voice.get("Gender", ""),
                    "engine": voice.get("SupportedEngines", []),
                })

            return voices
        except Exception as e:
            logger.error(f"Failed to list voices: {e}")
            return []

    def synthesize_long_form(
        self,
        text: str,
        output_path: str,
        voice_name: str = None,
    ) -> ProviderResponse:
        """
        Uzoq matn uchun sintez (podcast, audiobook).

        Long-form engine 10 daqiqagacha matnni qayta ishlaydi.
        """
        return self.synthesize(
            text=text,
            output_path=output_path,
            voice_name=voice_name,
            engine="long-form",
        )

    def synthesize_ssml(
        self,
        ssml: str,
        output_path: str,
        voice_name: str = None,
    ) -> ProviderResponse:
        """SSML bilan sintez."""
        return self.synthesize(
            text=ssml,
            output_path=output_path,
            voice_name=voice_name,
            use_ssml=True,
        )
