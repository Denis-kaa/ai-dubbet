"""
ElevenLabs TTS Provider.

Konfiguratsiya (.env orqali):
  ELEVENLABS_API_KEY            — API kalit
  ELEVENLABS_VOICE_ID_MALE      — erkak ovoz ID (default: Adam)
  ELEVENLABS_VOICE_ID_FEMALE    — ayol ovoz ID (default: Rachel)
  ELEVENLABS_MODEL              — model (default: eleven_multilingual_v2)
  ELEVENLABS_STABILITY          — 0.0–1.0 (default: 0.5)
  ELEVENLABS_SIMILARITY_BOOST   — 0.0–1.0 (default: 0.75)
  ELEVENLABS_STYLE              — 0.0–1.0 (default: 0.0)
  ELEVENLABS_SPEED              — 0.7–1.2 (default: 1.0)
  ELEVENLABS_FALLBACK_TO_EDGE   — xatolikda Edge TTS ga o'tish (default: True)
"""
import logging
import os
import random
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager

from redis import Redis

from backend.services.tts.base import TTSProvider
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class _ConcurrencyGate:
    """
    Redis-backed semaphore capping simultaneous ElevenLabs requests across
    ALL celery worker processes/threads (not just within one job).

    ElevenLabs hard-caps concurrent requests per account (429
    concurrent_limit_exceeded once exceeded). Without a cross-process gate,
    several segments/jobs synthesizing in parallel silently blow past that
    cap and fall back to a different-sounding TTS engine mid-dub — the
    exact "two different voices in one video" bug this guards against.
    """

    KEY = "elevenlabs:concurrent"
    MAX_CONCURRENT = 2  # account limit is 3 — stay one under for safety margin
    POLL_INTERVAL = 0.3

    def __init__(self, redis_url: str):
        self._redis: Redis | None = None
        self._redis_url = redis_url

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _try_acquire(self) -> bool:
        pipe = self.redis.pipeline()
        pipe.incr(self.KEY)
        pipe.expire(self.KEY, 60)
        val = pipe.execute()[0]
        if val <= self.MAX_CONCURRENT:
            return True
        self.redis.decr(self.KEY)
        return False

    def release(self) -> None:
        try:
            self.redis.decr(self.KEY)
        except Exception:
            pass

    @contextmanager
    def slot(self, timeout: float = 25.0):
        deadline = time.monotonic() + timeout
        acquired = False
        try:
            while time.monotonic() < deadline:
                if self._try_acquire():
                    acquired = True
                    break
                time.sleep(self.POLL_INTERVAL + random.uniform(0, 0.2))
            yield acquired
        finally:
            if acquired:
                self.release()


_gate = _ConcurrencyGate(settings.REDIS_URL)


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs Text-to-Speech provider (eleven_multilingual_v2)."""

    # Will (Relaxed Optimist — yengil va shirali erkak ovozi)
    DEFAULT_VOICE_ID_MALE = "bIHbv24MWmeRgasZH58o"
    # Sarah (Mature, Reassuring, Confident — tabiiy va yoqimli ayol ovozi)
    DEFAULT_VOICE_ID_FEMALE = "EXAVITQu4vr4xnSDxMaL"

    @property
    def name(self) -> str:
        return "elevenlabs"

    @property
    def cost_per_1k(self) -> float:
        return 0.30

    def _get_voice_id(self, voice_name: str | None) -> str:
        if self._is_female(voice_name):
            return settings.ELEVENLABS_VOICE_ID_FEMALE or self.DEFAULT_VOICE_ID_FEMALE
        return settings.ELEVENLABS_VOICE_ID_MALE or self.DEFAULT_VOICE_ID_MALE

    def _normalize_uzbek_text(self, text: str) -> str:
        """g' va o' harflaridagi har xil Unicode apostroflarni standartlashtirish."""
        if not text:
            return text
        # HTML taglarni olib tashlash
        text = re.sub(r"<[^>]+>", "", text)
        # Barcha turdagi apostroflarni standart ' ga o'tkazish
        text = text.replace("‘", "'").replace("’", "'").replace("ʻ", "'").replace("`", "'")
        # Keraksiz ko'p bo'shliqlarni tozalash
        return re.sub(r"\s+", " ", text).strip()

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str | None = None,
    ) -> bool:
        api_key = settings.ELEVENLABS_API_KEY or os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            logger.warning("ELEVENLABS_API_KEY topilmadi — ElevenLabs o'tkazib yuborildi.")
            return False

        clean_text = self._normalize_uzbek_text(text)
        if not clean_text:
            return False

        voice_id = self._get_voice_id(voice_name)
        model_id = settings.ELEVENLABS_MODEL or "eleven_multilingual_v2"

        # Stability 0.80 bo'lsa har bir segment bitta bir xil ohang va tonda chiqadi
        stability = float(settings.ELEVENLABS_STABILITY or 0.80)
        similarity_boost = float(settings.ELEVENLABS_SIMILARITY_BOOST or 0.85)

        max_retries = 3
        for attempt in range(max_retries):
            with _gate.slot(timeout=25.0) as acquired:
                if not acquired:
                    logger.warning(
                        f"ElevenLabs concurrency slot bo'shamadi (urinish {attempt+1}/{max_retries})."
                    )
                    time.sleep(2 ** attempt)
                    continue

                try:
                    from elevenlabs.client import ElevenLabs
                    from elevenlabs.types import VoiceSettings

                    client = ElevenLabs(api_key=api_key)

                    audio_gen = client.text_to_speech.convert(
                        voice_id=voice_id,
                        text=clean_text,
                        model_id=model_id,
                        voice_settings=VoiceSettings(
                            stability=stability,
                            similarity_boost=similarity_boost,
                            style=float(settings.ELEVENLABS_STYLE or 0.0),
                            use_speaker_boost=True,
                        ),
                        output_format="mp3_44100_128",
                    )

                    audio_bytes = b"".join(audio_gen)

                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                        tmp.write(audio_bytes)
                        tmp_mp3_path = tmp.name

                    try:
                        if os.path.getsize(tmp_mp3_path) < 100:
                            raise ValueError("ElevenLabs: bo'sh audio qaytarildi")

                        subprocess.run(
                            [
                                "ffmpeg", "-y",
                                "-i", tmp_mp3_path,
                                "-acodec", "pcm_s16le",
                                "-ar", "24000",
                                "-ac", "1",
                                output_path,
                            ],
                            check=True,
                            capture_output=True,
                        )
                        logger.info(
                            f"ElevenLabs TTS: voice={voice_id}, model={model_id}, "
                            f"chars={len(clean_text)}, attempt={attempt+1}"
                        )
                        return True
                    finally:
                        if os.path.exists(tmp_mp3_path):
                            try:
                                os.remove(tmp_mp3_path)
                            except Exception:
                                pass

                except Exception as exc:
                    logger.warning(f"ElevenLabs urinish {attempt+1}/{max_retries} xato: {exc}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)

        return False
