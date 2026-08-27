"""GapirAI.uz Telegram bot -- to'liq dublyaj xizmati Telegram ichida.

Web bilan bir xil hisob: foydalanuvchi telefon raqamini ulashadi (Telegram
o'zi tasdiqlaydi, SMS kod shart emas), va agar shu raqam saytda ham
ro'yxatdan o'tgan bo'lsa -- kvota/obuna ikkalasida ham baravar ishlaydi
(backend/models/database.py: User.phone, User.telegram_chat_id).

Job yaratish mantig'i backend/services/job_creation.py'da -- web API
(routes.py) bilan bir xil, ikki joyda saqlanmaydi (Safety Gate, kvota,
davomiylik chegarasi -- barchasi avtomatik shu orqali ishlaydi).

Video tayyor bo'lganda xabar backend/workers/tasks.py'dan (job yakunlanganda)
keladi -- bu jarayon faqat kiruvchi xabarlarni tinglaydi, holatni o'zi
so'rovda kutib turmaydi.

Ishga tushirish: alohida Docker Compose xizmati (docker-compose.yml:
telegram_bot), long-polling rejimida.
"""
import logging
import re

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from backend.config import get_settings
from backend.models.database import SessionLocal, User, DubbingJob, JobStatus
from backend.services.job_creation import (
    create_dubbing_job,
    create_click_payment,
    is_valid_youtube_url,
)
from backend.services.resolution_variants import request_resolution

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("telegram_bot")

settings = get_settings()

_PHONE_RE = re.compile(r"^\+998\d{9}$")


def _normalize_uz_phone(raw: str) -> str | None:
    """Telegram contact.phone_number odatda '+' belgisisiz keladi
    ('998901234567'). auth_routes.py bilan bir xil formatga (+998XXXXXXXXX)
    keltiradi, mos kelmasa None qaytaradi."""
    digits = re.sub(r"[^\d]", "", raw)
    if digits.startswith("998") and len(digits) == 12:
        candidate = f"+{digits}"
    elif len(digits) == 9:
        candidate = f"+998{digits}"
    else:
        candidate = f"+{digits}" if not raw.startswith("+") else raw
    return candidate if _PHONE_RE.match(candidate) else None


def _looks_like_youtube_url(text: str) -> str | None:
    """Matn ichidan birinchi YouTube havolasini topadi (foydalanuvchi
    ba'zan 'mana bu video: <link>' deb yozadi)."""
    for token in text.split():
        if is_valid_youtube_url(token):
            return token
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    finally:
        db.close()

    if user:
        await update.message.reply_text(
            f"Xush kelibsiz, {user.name or ''}! 👋\n\n"
            "Menga istalgan YouTube havolasini yuboring — o'zbek tiliga dublyaj qilib beraman."
        )
        return

    button = KeyboardButton("📱 Telefon raqamimni ulashish", request_contact=True)
    await update.message.reply_text(
        "Assalomu alaykum! GapirAI.uz botiga xush kelibsiz. 🎬\n\n"
        "YouTube videolarni o'zbek tiliga avtomatik dublyaj qilib beraman.\n\n"
        "Boshlash uchun telefon raqamingizni ulashing (agar saytda ro'yxatdan o'tgan bo'lsangiz, "
        "hisobingiz avtomatik tanilib, obuna/kvotangiz shu yerda ham ishlaydi):",
        reply_markup=ReplyKeyboardMarkup([[button]], one_time_keyboard=True, resize_keyboard=True),
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = update.message.contact
    if contact.user_id != update.effective_user.id:
        await update.message.reply_text("Iltimos, faqat o'zingizning telefon raqamingizni ulashing.")
        return

    phone = _normalize_uz_phone(contact.phone_number)
    if not phone:
        await update.message.reply_text(
            "Uzr, hozircha faqat O'zbekiston raqamlari (+998) qo'llab-quvvatlanadi.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    chat_id = str(update.effective_chat.id)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            user = User(
                phone=phone,
                name=update.effective_user.first_name or phone,
                is_verified=True,  # Telegram contact-share o'zi tasdiqlaydi -- SMS kod shart emas.
                auth_provider="phone",
                telegram_chat_id=chat_id,
            )
            db.add(user)
        else:
            user.telegram_chat_id = chat_id
            if not user.is_verified:
                user.is_verified = True
        db.commit()
        name = user.name
    finally:
        db.close()

    await update.message.reply_text(
        f"Rahmat, {name}! Hisobingiz ulandi. ✅\n\n"
        "Endi menga istalgan YouTube havolasini yuboring — dublyajni boshlayman.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    text = (update.message.text or "").strip()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    finally:
        db.close()

    if not user:
        await update.message.reply_text("Avval /start buyrug'ini yuborib, telefon raqamingizni ulashing.")
        return

    url = _looks_like_youtube_url(text)
    if not url:
        await update.message.reply_text("Iltimos, YouTube video havolasini yuboring (masalan: https://youtube.com/watch?v=...).")
        return

    await update.message.reply_text("⏳ Video tekshirilmoqda...")

    db = SessionLocal()
    try:
        # DB user'ni shu sessiyada qayta olish kerak -- yuqoridagi `user`
        # boshqa (yopilgan) sessiyaga bog'langan edi.
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        result = await create_dubbing_job(db, user, url, voice_gender="auto")

        if result.outcome == "invalid_url":
            await update.message.reply_text("Bu YouTube havolasi noto'g'ri ko'rinadi.")
        elif result.outcome == "fetch_error":
            await update.message.reply_text(f"Video ma'lumotlarini olishda xatolik: {result.error_detail}")
        elif result.outcome == "blocked":
            await update.message.reply_text(
                "🚫 Ushbu video GapirAI.uz kontent siyosatiga mos kelmagani sababli dublaj qilinmaydi."
            )
        elif result.outcome == "too_long":
            await update.message.reply_text(
                f"Video juda uzun ({result.duration_minutes:.0f} daqiqa). "
                "Maksimal ruxsat etilgan davomiylik bilan qayta urinib ko'ring."
            )
        elif result.outcome == "queued":
            await update.message.reply_text(
                f"✅ \"{result.video_title}\" navbatga qo'shildi.\n\nTayyor bo'lganda shu yerga xabar yuboraman."
            )
        elif result.outcome == "ready":
            frontend_url = (settings.FRONTEND_URL or "https://gapirai.uz").rstrip("/")
            await update.message.reply_text(
                f"✅ \"{result.video_title}\" allaqachon tayyor!\n\n{frontend_url}/video/{result.job_id}"
            )
        elif result.outcome == "awaiting_payment":
            job = db.query(DubbingJob).filter(DubbingJob.id == result.job_id).first()
            payment_url = create_click_payment(
                db, job, result.amount,
                return_url=f"{(settings.FRONTEND_URL or 'https://gapirai.uz').rstrip('/')}/dashboard",
            )
            await update.message.reply_text(
                f"\"{result.video_title}\" uchun to'lov kerak: {result.amount:,} so'm.\n\n"
                f"To'lov havolasi: {payment_url}\n\n"
                "To'lovni yakunlagach, dublyaj avtomatik boshlanadi va tayyor bo'lganda shu yerga xabar yuboraman."
            )
    finally:
        db.close()


async def handle_resolution_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dublyaj tayyor bo'lganda yuborilgan xabardagi 360p/720p/1080p
    tugmalaridan biri bosilganda ishga tushadi -- veb bilan bir xil
    resolution_variants.request_resolution() orqali (backend/api/routes.py
    ham shu funksiyani chaqiradi, mantiq bitta joyda)."""
    query = update.callback_query
    await query.answer()

    try:
        _, job_id, resolution = (query.data or "").split(":", 2)
    except ValueError:
        return

    db = SessionLocal()
    try:
        job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
        if not job or job.status != JobStatus.COMPLETED:
            await query.message.reply_text("Video topilmadi yoki hali tayyor emas.")
            return

        result = request_resolution(db, job, resolution)

        if result.outcome == "forbidden":
            await query.message.reply_text(
                "Bu sifat sizning tarif rejangizda mavjud emas. Tarifni oshirish uchun saytga o'ting."
            )
        elif result.outcome == "ready":
            await query.message.reply_text(f"✅ {resolution}:\n\n{result.download_url}")
        elif result.outcome == "processing":
            await query.message.reply_text(
                f"⏳ {resolution} versiyasi tayyorlanmoqda. Tayyor bo'lganda shu yerga xabar beraman."
            )
        else:
            await query.message.reply_text("Noto'g'ri so'rov.")
    finally:
        db.close()


def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN sozlanmagan -- bot ishga tushmaydi.")
        return

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_resolution_callback, pattern=r"^res:"))

    logger.info("Telegram bot ishga tushdi (long polling).")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
