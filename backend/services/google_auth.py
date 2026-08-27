"""Google Sign-In — frontend Google Identity Services token'ini tekshiradi.

Server-side auth-code almashinuvi ishlatilmaydi (shuning uchun
GOOGLE_CLIENT_SECRET kerak emas) — frontend Google Identity Services orqali
olingan ID token'ni backend shu funksiya orqali Google'ning ochiq kalitlariga
qarshi tekshiradi.
"""
import logging

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_request = google_requests.Request()


class GoogleTokenError(Exception):
    """Token yaroqsiz yoki tekshirib bo'lmadi."""


def verify_google_token(credential: str) -> dict:
    """ID token'ni tekshiradi, {sub, email, email_verified, name} qaytaradi.

    Yaroqsiz/eskirgan/soxta token bo'lsa GoogleTokenError ko'taradi.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleTokenError("GOOGLE_CLIENT_ID sozlanmagan.")

    # Web (frontend) va Android (mobile/) alohida OAuth mijozlar — ID token'ning
    # "aud"i qaysi mijozdan kelganiga qarab ikkisidan biri bo'lishi mumkin.
    # google-auth kutubxonasi audience'ni ro'yxat sifatida qabul qiladi.
    valid_audiences = [settings.GOOGLE_CLIENT_ID]
    if settings.GOOGLE_ANDROID_CLIENT_ID:
        valid_audiences.append(settings.GOOGLE_ANDROID_CLIENT_ID)

    try:
        payload = id_token.verify_oauth2_token(credential, _request, valid_audiences)
    except ValueError as exc:
        # Xom kutubxona xatosini (google-auth) foydalanuvchiga ko'rsatmaymiz.
        logger.warning(f"Google token tekshiruvi muvaffaqiyatsiz: {exc}")
        raise GoogleTokenError("Google token yaroqsiz yoki muddati o'tgan. Qaytadan urinib ko'ring.") from exc

    email_val = payload.get("email")
    if not email_val:
        raise GoogleTokenError("Google token'da email topilmadi.")

    raw_verified = payload.get("email_verified")
    is_verified = raw_verified is True or str(raw_verified).lower() == "true"

    return {
        "sub": payload["sub"],
        "email": str(email_val).lower().strip(),
        "email_verified": is_verified,
        "name": payload.get("name") or str(email_val).split("@")[0],
    }
