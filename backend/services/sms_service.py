"""
SMS Service — Eskiz.uz orqali telefon tasdiqlash kodlarini yuborish
(https://notify.eskiz.uz/api).

Resend'ning statik API key'idan farqli — Eskiz email+parol orqali login
qilib bearer token oladi (~30 kun amal qiladi). Bir nechta worker jarayoni
bo'lgani uchun token Redis'da keshlanadi (har bir jarayon alohida login
qilib, Eskiz'ning login-so'rov limitiga urilib qolmasligi uchun).
"""
import logging

import httpx
from redis import Redis

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

CODE_TTL_MINUTES = 10
ESKIZ_BASE_URL = "https://notify.eskiz.uz/api"
_TOKEN_KEY = "eskiz:auth_token"
_TOKEN_TTL_SECONDS = 25 * 24 * 3600  # ~25 kun — Eskiz tokeni ~30 kun amal qiladi, ehtiyot chorasi bilan qisqaroq keshlanadi

_redis: Redis | None = None


def _get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _login_to_eskiz() -> str | None:
    """Eskiz'ga email+parol bilan login qilib, yangi bearer token oladi."""
    try:
        response = httpx.post(
            f"{ESKIZ_BASE_URL}/auth/login",
            data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
            timeout=15,
        )
    except httpx.RequestError as exc:
        logger.error(f"Eskiz login xatosi (ulanish): {exc}")
        return None

    if response.status_code != 200:
        logger.error(f"Eskiz login xatosi: {response.status_code} {response.text[:200]}")
        return None

    token = (response.json().get("data") or {}).get("token")
    if not token:
        logger.error("Eskiz login javobida token topilmadi.")
        return None
    return token


def _get_token(force_refresh: bool = False) -> str | None:
    r = _get_redis()
    if not force_refresh:
        cached = r.get(_TOKEN_KEY)
        if cached:
            return cached

    token = _login_to_eskiz()
    if token:
        r.setex(_TOKEN_KEY, _TOKEN_TTL_SECONDS, token)
    return token


def send_otp_sms(phone: str, code: str) -> bool:
    """Tasdiqlash kodini SMS orqali yuboradi. ESKIZ_EMAIL/PASSWORD
    sozlanmagan bo'lsa, xatolik bermay False qaytaradi (Resend bilan bir
    xil ehtiyotkor naqsh — chaqiruvchi buni foydalanuvchiga aniq xatolik
    sifatida ko'rsatadi)."""
    if not settings.ESKIZ_EMAIL or not settings.ESKIZ_PASSWORD:
        logger.warning("ESKIZ_EMAIL/ESKIZ_PASSWORD sozlanmagan — SMS yuborilmadi.")
        return False

    message = f"GapirAI.uz tasdiqlash kodi: {code}"

    for attempt in range(2):
        token = _get_token(force_refresh=(attempt == 1))
        if not token:
            return False

        try:
            response = httpx.post(
                f"{ESKIZ_BASE_URL}/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={"mobile_phone": phone.lstrip("+"), "message": message, "from": settings.ESKIZ_FROM},
                timeout=15,
            )
        except httpx.RequestError as exc:
            logger.error(f"Eskiz SMS yuborishda ulanish xatosi ({phone}): {exc}")
            return False

        if response.status_code == 200:
            return True
        if response.status_code == 401 and attempt == 0:
            logger.warning("Eskiz token eskirgan — qayta login qilinmoqda.")
            continue

        logger.error(f"Eskiz SMS xatoligi ({phone}): {response.status_code} {response.text[:200]}")
        return False

    return False
