"""Segment darajasidagi TTS audio keshi — bir xil matn+ovoz+provider
kombinatsiyasi qayta sintez qilinmasdan (haqiqiy pul to'lanmasdan) S3'dagi
mavjud audio qaytariladi (backend/models/database.py: TTSCache).

Nega S3, nega lokal disk emas — job tugagach mahalliy fayllar o'chiriladi
(backend/workers/tasks.py), shuning uchun kesh S3'da yashashi shart, aks
holda birinchi job tugashi bilan o'zining keshini o'chirib qo'yardi.

tts_cost.py'ning shakliga o'xshaydi — xatolik hech qachon dublyaj
pipeline'ini to'xtatmaydi, faqat log qilinadi va oddiy sintezga o'tiladi.
"""
import hashlib
import logging
import os
import tempfile

from backend.models.database import SessionLocal, TTSCache
from backend.services.storage import upload_file_to_s3, download_file_from_s3

logger = logging.getLogger(__name__)

_CACHE_S3_PREFIX = "dubber-cache/tts"


def _cache_key(text: str, voice_name: str | None, provider: str) -> str:
    raw = f"{text}|{voice_name or ''}|{provider}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached(text: str, voice_name: str | None, provider: str, output_path: str) -> bool:
    """Kesh'da mavjud bo'lsa, audio'ni output_path'ga yuklab, True qaytaradi.
    Topilmasa yoki S3 sozlanmagan bo'lsa (yoki xatolik) — False, pipeline
    oddiy sintezga o'tadi."""
    key = _cache_key(text, voice_name, provider)
    db = SessionLocal()
    try:
        entry = db.query(TTSCache).filter(TTSCache.cache_key == key).first()
        if not entry:
            return False
        if not download_file_from_s3(entry.s3_key, output_path):
            return False
        entry.hit_count += 1
        db.commit()
        return True
    except Exception as exc:
        logger.warning(f"TTS keshni o'qishda xatolik (oddiy sintezga o'tiladi): {exc}")
        return False
    finally:
        db.close()


def store_cached(text: str, voice_name: str | None, provider: str, audio_path: str) -> None:
    """Yangi sintez qilingan audio'ni keshga yozadi. Xatolik bo'lsa faqat
    log qilinadi — kesh yozish ikkinchi darajali, asosiy pipeline birinchi."""
    if not os.path.exists(audio_path):
        return

    key = _cache_key(text, voice_name, provider)
    s3_key = f"{_CACHE_S3_PREFIX}/{key}.wav"

    try:
        if not upload_file_to_s3(audio_path, s3_key):
            return

        db = SessionLocal()
        try:
            existing = db.query(TTSCache).filter(TTSCache.cache_key == key).first()
            if existing:
                return
            db.add(TTSCache(cache_key=key, provider=provider, s3_key=s3_key))
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"TTS keshga yozishda xatolik (pipeline davom etadi): {exc}")
