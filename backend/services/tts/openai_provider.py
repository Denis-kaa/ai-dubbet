"""OpenAI TTS Provider (tts-1 / tts-1-hd)."""
import logging
import os
import re
import subprocess
import tempfile

from backend.services.tts.base import TTSProvider
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OpenAIProvider(TTSProvider):
    """OpenAI TTS — studio-grade, lekin Uzbek uchun maxsus ovoz yo'q."""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def cost_per_1k(self) -> float:
        # tts-1: $15/1M chars = $0.015/1K
        return 0.015

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str | None = None,
    ) -> bool:
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return False

        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        if not clean_text:
            return False

        openai_voice = "nova" if self._is_female(voice_name) else "onyx"

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_mp3_path = tmp.name

            try:
                response = client.audio.speech.create(
                    model="tts-1",
                    voice=openai_voice,
                    input=clean_text,
                    response_format="mp3",
                )
                response.stream_to_file(tmp_mp3_path)

                if os.path.exists(tmp_mp3_path) and os.path.getsize(tmp_mp3_path) > 100:
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-i", tmp_mp3_path,
                            "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
                            output_path,
                        ],
                        check=True, capture_output=True,
                    )
                    logger.info(f"OpenAI TTS: voice={openai_voice}, chars={len(clean_text)}")
                    return True
            finally:
                if os.path.exists(tmp_mp3_path):
                    try:
                        os.remove(tmp_mp3_path)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning(f"OpenAI TTS xato: {exc}")

        return False
