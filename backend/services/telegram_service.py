"""
Telegram notification service for feedback and system alerts.
Sends star ratings and comments to Telegram bot.
"""
import os
import logging
import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _format_ok(label: str, value: bool | None) -> str | None:
    if value is None:
        return None
    return f"{'✅' if value else '❌'} <b>{label}</b>: {'Yaxshi' if value else 'Yomon'}"


def send_telegram_feedback(
    job_id: str,
    video_title: str,
    rating: int,
    comment: str | None = None,
    chat_id: str | None = None,
    voice_ok: bool | None = None,
    translation_ok: bool | None = None,
    speed_ok: bool | None = None,
) -> bool:
    """
    Dublyaj bahosi va fikrini Telegram bot orqali guruh/kanal/admin chatiga yuboradi.
    """
    token = settings.TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    target_chat = chat_id or settings.TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", "")

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN sozlanmagan.")
        return False

    if not target_chat:
        logger.warning("TELEGRAM_CHAT_ID sozlanmagan — xabar yuborilmadi.")
        return False

    stars_str = "⭐" * rating
    comment_clean = comment.strip() if comment and comment.strip() else "Fikr qoldirilmadi"
    title_clean = video_title or "Noma'lum video"

    detail_lines = [
        line for line in (
            _format_ok("Ovoz sifati", voice_ok),
            _format_ok("Tarjima sifati", translation_ok),
            _format_ok("Tezlik", speed_ok),
        ) if line
    ]
    details_block = ("\n" + "\n".join(detail_lines) + "\n") if detail_lines else ""

    text = (
        f"⭐️ <b>YANGI FIKR VA BAHOLASH (GapirAI.uz)</b> ⭐️\n\n"
        f"📹 <b>Video</b>: {title_clean}\n"
        f"⭐ <b>Baho</b>: {stars_str} ({rating} / 5)\n"
        f"{details_block}"
        f"💬 <b>Fikr</b>: \"{comment_clean}\"\n\n"
        f"🆔 <b>Job ID</b>: <code>{job_id}</code>\n"
        f"🔗 <b>Havola</b>: https://gapirai.uz/video/{job_id}"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        res = httpx.post(url, json=payload, timeout=10.0)
        if res.status_code == 200:
            logger.info(f"Telegram feedback notification sent for job {job_id}")
            return True
        logger.warning(f"Telegram API response {res.status_code}: {res.text}")
    except Exception as exc:
        logger.error(f"Failed to send Telegram notification: {exc}")
    return False


def send_telegram_platform_feedback(
    message: str,
    rating: int | None = None,
    user_email: str | None = None,
) -> bool:
    """
    Saytga umumiy (biror videoga bog'liq bo'lmagan) fikr-mulohaza — istalgan
    tashrif buyuruvchi qoldirishi mumkin bo'lgan "Platforma haqida fikringiz"
    formasi orqali kelgan xabarni Telegram guruh/kanal/admin chatiga yuboradi.
    """
    token = settings.TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    target_chat = settings.TELEGRAM_CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not target_chat:
        logger.warning("TELEGRAM_BOT_TOKEN yoki TELEGRAM_CHAT_ID sozlanmagan — platforma fikri yuborilmadi.")
        return False

    rating_line = f"⭐ <b>Baho</b>: {'⭐' * rating} ({rating} / 5)\n" if rating else ""
    user_line = f"👤 <b>Foydalanuvchi</b>: {user_email}\n" if user_email else "👤 <b>Foydalanuvchi</b>: Anonim\n"

    text = (
        f"💬 <b>PLATFORMA HAQIDA FIKR (GapirAI.uz)</b> 💬\n\n"
        f"{rating_line}"
        f"{user_line}"
        f"📝 <b>Xabar</b>: \"{message.strip()}\""
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        res = httpx.post(url, json=payload, timeout=10.0)
        if res.status_code == 200:
            logger.info("Telegram platform feedback notification sent")
            return True
        logger.warning(f"Telegram API response {res.status_code}: {res.text}")
    except Exception as exc:
        logger.error(f"Failed to send Telegram platform feedback notification: {exc}")
    return False
