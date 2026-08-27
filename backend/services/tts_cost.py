"""TTS xarajat kuzatuvi — har bir muvaffaqiyatli sintez chaqiruvini
TTSUsageLog jadvaliga yozadi va provider bo'yicha narx taxminlarini beradi.

Maqsad: "1/10/100/1000 video dublyaj qilish bizga qancha turadi" savoliga
provider bo'yicha aniq javob (backend/models/database.py: TTSUsageLog).
"""
import logging
import subprocess
import json

from backend.models.database import SessionLocal, TTSUsageLog
from backend.services.tts.base import TTSProvider

logger = logging.getLogger(__name__)

# uzbekvoice — UZS'da narxlanadi (500 so'm/1000 belgi); qolgan barcha
# provayderlar (elevenlabs/azure/edge/openai/gemini) USD'da.
_UZS_PROVIDERS = {"uzbekvoice"}


def _get_audio_duration_seconds(path: str) -> float | None:
    """ffprobe orqali audio uzunligini aniqlaydi. Xato bo'lsa None."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True, text=True, check=True, timeout=10,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return None


def log_tts_usage(
    provider: TTSProvider,
    text: str,
    audio_path: str,
    video_id: str | None = None,
    user_id: str | None = None,
    cache_hit: bool = False,
) -> None:
    """Muvaffaqiyatli sintezdan keyin bitta TTSUsageLog yozuvi yaratadi.
    Xatolik bo'lsa (masalan DB vaqtincha mavjud emas) faqat log qiladi —
    dublyaj pipeline'ini hech qachon to'xtatmaydi (cost tracking ikkinchi
    darajali, asosiy pipeline birinchi).

    cache_hit=True bo'lsa (backend/services/tts_cache.py), haqiqiy sintez
    bo'lmagani uchun xarajat 0 — lekin keshning real ta'sirini ko'rish uchun
    baribir yoziladi (butunlay o'tkazib yuborilmaydi)."""
    try:
        chars = len(text or "")
        currency = "UZS" if provider.name in _UZS_PROVIDERS else "USD"
        cost = 0.0 if cache_hit else provider.estimate_cost(chars)
        duration = _get_audio_duration_seconds(audio_path)

        db = SessionLocal()
        try:
            db.add(TTSUsageLog(
                provider=provider.name,
                characters=chars,
                duration_seconds=duration,
                estimated_cost=cost,
                currency=currency,
                video_id=video_id,
                user_id=user_id,
                cache_hit=cache_hit,
            ))
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"TTS cost tracking yozishda xatolik (pipeline davom etadi): {exc}")


def estimate_video_cost(provider_name: str, avg_chars_per_video: int, num_videos: int) -> dict:
    """Berilgan provider uchun N ta video dublyaj qilish taxminiy narxini hisoblaydi.

    avg_chars_per_video — bitta videoning o'rtacha belgi soni (masalan
    o'rtacha 10 daqiqalik video uchun tarjima matni ~1500-2500 belgi/daqiqa).
    """
    from backend.services.tts.factory import get_provider

    provider = get_provider(provider_name)
    currency = "UZS" if provider_name in _UZS_PROVIDERS else "USD"
    total_chars = avg_chars_per_video * num_videos
    total_cost = provider.estimate_cost(total_chars)
    return {
        "provider": provider_name,
        "num_videos": num_videos,
        "avg_chars_per_video": avg_chars_per_video,
        "total_characters": total_chars,
        "total_cost": round(total_cost, 2),
        "currency": currency,
    }
