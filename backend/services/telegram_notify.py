"""Telegram'ga chiquvchi xabarlar -- botning o'zidan mustaqil, oddiy HTTP
so'rov (Telegram Bot API). backend/workers/tasks.py job yakunlanganda
(COMPLETED/FAILED) shu yerdan foydalanadi -- interaktiv bot jarayonining
o'zi ishlab turishi shart emas, faqat token kerak.
"""
import logging

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)


def _api_url(method: str) -> str:
    settings = get_settings()
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def send_telegram_message(chat_id: str, text: str, reply_markup: dict | None = None) -> bool:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN or not chat_id:
        return False
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        resp = httpx.post(
            _api_url("sendMessage"),
            json=payload,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"Telegram xabar yuborilmadi (chat_id={chat_id}): {resp.status_code} {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram xabar yuborishda xato (chat_id={chat_id}): {e}")
        return False
