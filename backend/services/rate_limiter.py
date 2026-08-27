"""
Public API rate limiting — Redis fixed-window counter, keyed by client IP.

Bir xil naqsh backend/services/downloader.py (YoutubeRateLimiter) va
backend/services/tts/elevenlabs_provider.py (_ConcurrencyGate) da
ishlatilgan: yangi tashqi kutubxona qo'shmasdan, mavjud Redis orqali.

Maqsad: bitta odam (yoki bot) `/api/jobs`, `/auth/*` kabi ochiq
endpointlarni cheksiz urib, Celery navbatini yoki emailga kod yuborish
tizimini egallab olmasligi. Redis mavjud bo'lmasa yoki xato bersa,
so'rov TO'SILMAYDI — faqat log qilinadi (rate limiter ishlamasligi
saytni butunlay to'xtatib qo'ymasligi kerak).
"""
import logging
from redis import Redis
from fastapi import Request, HTTPException

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis: Redis | None = None


def _get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _client_ip(request: Request) -> str:
    """Nginx orqasida ishlaganda haqiqiy IP'ni X-Forwarded-For'dan olamiz."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    """
    FastAPI dependency factory: `dependencies=[Depends(rate_limit("jobs", 8, 600))]`

    key_prefix ayni endpoint uchun; har bir IP mustaqil hisoblanadi.
    Belgilangan oyna (window_seconds) ichida max_requests dan oshsa 429
    qaytaradi.
    """
    def _dependency(request: Request) -> None:
        ip = _client_ip(request)
        key = f"ratelimit:{key_prefix}:{ip}"
        try:
            r = _get_redis()
            current = r.incr(key)
            if current == 1:
                r.expire(key, window_seconds)
            if current > max_requests:
                ttl = r.ttl(key)
                wait_s = ttl if ttl and ttl > 0 else window_seconds
                raise HTTPException(
                    status_code=429,
                    detail=f"Juda ko'p so'rov yuborildi. {wait_s} soniyadan so'ng qayta urinib ko'ring.",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(f"Rate limiter ishlamadi ({key_prefix}): {exc}")

    return _dependency
