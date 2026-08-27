"""UzbekVoiceAI TTS Provider (https://uzbekvoice.ai/videos/api-docs/tts).

API kontrakti (jonli hujjatdan va haqiqiy so'rovdan tasdiqlangan):
    POST {base_url}/tts
    Headers: Authorization: <API_KEY> (xom kalit, "Bearer" prefiksisiz)
    Body:    {"text": str, "model": str, "blocking": true}
    Javob (blocking=true, sinxron):
        {"id": str, "model": str, "model_substituted": bool, "progress": float,
         "requested_model": str, "result": {"url": "<vaqtinchalik S3 .wav havolasi>"},
         "status": "SUCCESS"}
    Narxi: 500 so'm / 1000 belgi (https://uzbekvoice.ai/pricing).

Natija — WAV fayl havolasi. Sample rate/kanal soni hujjatlashtirilmagan bo'lgani
uchun, boshqa provayderlar kabi (Azure/OpenAI) yuklab olingan audio ffmpeg orqali
pipeline kutayotgan 24kHz mono PCM WAV formatiga majburan keltiriladi.
"""
import logging
import os
import random
import subprocess
import tempfile
import time
from contextlib import contextmanager

import requests
from redis import Redis

from backend.services.tts.base import TTSProvider, PermanentTTSError
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class _ConcurrencyGate:
    """
    Redis-backed semaphore capping simultaneous UzbekVoiceAI requests across
    ALL celery worker processes/threads (not just within one job) — same
    pattern as elevenlabs_provider.py's gate.

    Confirmed via a real production job (2026-08-12): UzbekVoiceAI rejects
    concurrent requests beyond an account-specific limit with a 400
    "Too many active requests" error. synthesizer.py fires up to 5 segments
    in parallel (ThreadPoolExecutor), which blew straight past that limit and
    killed the whole job. Exact account limit is undocumented ("contact
    support to increase"), so MAX_CONCURRENT starts at 1 until confirmed.
    """

    KEY = "uzbekvoice:concurrent"
    MAX_CONCURRENT = 1
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
        pipe.expire(self.KEY, 90)
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
    def slot(self, timeout: float = 40.0):
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

# UzbekVoiceAI hujjatida tasdiqlangan ismlar bo'yicha jins taxmini (API hozircha
# jinsni alohida qaytarmaydi) — mavjud _is_female() ovoz tanlash yo'liga mos kelishi
# uchun kerak.
_VOICES = [
    {"id": "shoira", "gender": "female", "language": "uz"},
    {"id": "lola", "gender": "female", "language": "uz"},
    {"id": "kamola", "gender": "female", "language": "uz"},
    {"id": "sevinch", "gender": "female", "language": "uz"},
    {"id": "jasur", "gender": "male", "language": "uz"},
]
_FEMALE_VOICE = "kamola"
_MALE_VOICE = "jasur"


class UzbekVoiceProvider(TTSProvider):
    """UzbekVoiceAI — native o'zbek TTS."""

    @property
    def name(self) -> str:
        return "uzbekvoice"

    @property
    def cost_per_1k(self) -> float:
        # 500 so'm / 1000 belgi — UZS, boshqa provayderlardek USD emas.
        # synthesizer.py cost-tracking yozuvida currency="UZS" bilan belgilaydi.
        return 500.0

    def get_voices(self) -> list[dict]:
        return list(_VOICES)

    def _poll_task(self, task_id: str | None, api_key: str, max_wait_s: float = 45.0, interval_s: float = 2.0) -> dict | None:
        """GET /tasks?id=... orqali natija tayyor bo'lguncha so'raydi (blocking=true
        PENDING qaytargan holat uchun). None — poll muvaffaqiyatsiz bo'lsa."""
        if not task_id:
            logger.warning("UzbekVoiceAI TTS: PENDING holatida task id yo'q — poll qilib bo'lmaydi.")
            return None
        import time
        waited = 0.0
        while waited < max_wait_s:
            time.sleep(interval_s)
            waited += interval_s
            try:
                resp = requests.get(
                    f"{settings.UZBEKVOICE_BASE_URL}/tasks",
                    headers={"Authorization": api_key, "Content-Type": "application/json"},
                    params={"id": task_id},
                    timeout=15,
                )
            except (requests.Timeout, requests.ConnectionError):
                continue
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()
            except ValueError:
                continue
            if data.get("status") in ("SUCCESS", "FAILED", "ERROR"):
                return data
        logger.warning(f"UzbekVoiceAI TTS: task {task_id} {max_wait_s}s ichida tugallanmadi.")
        return None

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str | None = None,
    ) -> bool:
        api_key = settings.UZBEKVOICE_API_KEY
        if not api_key:
            logger.warning("UZBEKVOICE_API_KEY topilmadi — UzbekVoiceAI o'tkazib yuborildi.")
            return False

        clean_text = (text or "").strip()
        if not clean_text:
            return False

        model = voice_name if voice_name in {v["id"] for v in _VOICES} else (
            _FEMALE_VOICE if self._is_female(voice_name) else _MALE_VOICE
        )

        with _gate.slot(timeout=40.0) as acquired:
            if not acquired:
                logger.warning("UzbekVoiceAI TTS: concurrency slot bo'shamadi (40s kutildi).")
                return False

            try:
                response = requests.post(
                    f"{settings.UZBEKVOICE_BASE_URL}/tts",
                    headers={
                        "Authorization": api_key,
                        "Content-Type": "application/json",
                    },
                    json={"text": clean_text, "model": model, "blocking": True},
                    timeout=60,
                )
            except requests.Timeout:
                logger.warning("UzbekVoiceAI TTS: so'rov muddati tugadi (timeout).")
                return False
            except requests.ConnectionError as exc:
                logger.warning(f"UzbekVoiceAI TTS: ulanish xatosi: {exc}")
                return False

        if response.status_code in (401, 403):
            raise PermanentTTSError(f"UzbekVoiceAI: autentifikatsiya xatosi ({response.status_code}) — API kalitni tekshiring.")
        if response.status_code == 400:
            # UzbekVoiceAI concurrency-limit xatosini ham 400 bilan qaytaradi
            # (429 emas) — bu vaqtinchalik holat, _gate uni oldini olishi
            # kerak, lekin ehtiyot chorasi sifatida bu yerda ham False
            # qaytaramiz (PermanentTTSError emas), toza fallbackka o'tsin.
            if "too many active requests" in response.text.lower():
                logger.warning(f"UzbekVoiceAI TTS: concurrency limit (400): {response.text[:200]}")
                return False
            raise PermanentTTSError(f"UzbekVoiceAI: yaroqsiz so'rov (400): {response.text[:200]}")
        if response.status_code == 429:
            logger.warning("UzbekVoiceAI TTS: rate limit (429).")
            return False
        if response.status_code >= 500:
            logger.warning(f"UzbekVoiceAI TTS: server xatosi ({response.status_code}).")
            return False
        if response.status_code != 200:
            logger.warning(f"UzbekVoiceAI TTS: kutilmagan status {response.status_code}: {response.text[:200]}")
            return False

        try:
            data = response.json()
        except ValueError:
            logger.warning("UzbekVoiceAI TTS: javob JSON emas (malformed response).")
            return False

        # blocking=true har doim ham darhol SUCCESS bilan qaytmaydi — uzunroq
        # matnda server PENDING yoki STARTED holatida ish identifikatorini
        # qaytarishi kuzatilgan (haqiqiy so'rov bilan tasdiqlangan — bir xil
        # concurrency-test'da ikkalasi ham chiqqan). Har qanday nihoyaviy
        # bo'lmagan holatda /tasks?id=... orqali natija tayyor bo'lguncha
        # so'raymiz (nihoyaviy holatlar _poll_task bilan bir xil ro'yxat).
        if data.get("status") not in ("SUCCESS", "FAILED", "ERROR"):
            data = self._poll_task(data.get("id"), api_key)
            if data is None:
                return False

        if data.get("status") != "SUCCESS":
            logger.warning(f"UzbekVoiceAI TTS: muvaffaqiyatsiz holat: {data.get('status')}")
            return False

        audio_url = (data.get("result") or {}).get("url")
        if not audio_url:
            logger.warning("UzbekVoiceAI TTS: javobda audio havolasi yo'q (empty audio).")
            return False

        tmp_wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_wav_path = tmp.name
            audio_resp = requests.get(audio_url, timeout=60)
            if audio_resp.status_code != 200 or not audio_resp.content:
                logger.warning(f"UzbekVoiceAI TTS: audio yuklab olinmadi (status={audio_resp.status_code}).")
                return False
            with open(tmp_wav_path, "wb") as f:
                f.write(audio_resp.content)

            if os.path.getsize(tmp_wav_path) < 100:
                logger.warning("UzbekVoiceAI TTS: bo'sh yoki juda kichik audio fayl.")
                return False

            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", tmp_wav_path,
                    "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
                    output_path,
                ],
                check=True, capture_output=True,
            )
            logger.info(f"UzbekVoiceAI TTS: model={model}, chars={len(clean_text)}")
            return True
        except requests.Timeout:
            logger.warning("UzbekVoiceAI TTS: audio yuklab olishda timeout.")
            return False
        except subprocess.CalledProcessError as exc:
            logger.warning(f"UzbekVoiceAI TTS: ffmpeg konvertatsiya xatosi: {exc.stderr}")
            return False
        except Exception as exc:
            logger.warning(f"UzbekVoiceAI TTS: kutilmagan xato: {exc}")
            return False
        finally:
            if tmp_wav_path and os.path.exists(tmp_wav_path):
                try:
                    os.remove(tmp_wav_path)
                except Exception:
                    pass
