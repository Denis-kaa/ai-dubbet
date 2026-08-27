"""Tarif rejalar — narx, kvota, ustuvorlik va TTS sifat darajasi.

Reja ta'riflari kod konstantasi (bazada emas) — MAX_VIDEO_DURATION_MINUTES bilan
bir xil pattern: narx o'zgarsa, bitta qator tahrirlanadi, bazaviy migratsiya kerak
emas. Bu yerda faqat "kim qaysi tarifda va qachongacha" holati (Subscription
jadvali) saqlanadi.

Muhim moslik qoidasi: 45 daqiqadan qisqa videolar HAR DOIM bepul — bu
click_service.calculate_price()'ning bugungi (tarif tizimigacha bo'lgan)
xatti-harakati, va shu holicha saqlanadi. Tarif kvotasi (videos_per_period,
free_minutes) faqat 45+ daqiqali (pullik bo'lishi mumkin) videolarga tegishli —
"free_minutes" past kvotani emas, balki kvota ichida QAYSI davomiylikdagi
video "bepul hisoblanadi"ni bildiradi.

Yillik tariflar (standard_yearly/pro_yearly) alohida PLANS yozuvlari — xuddi
shu tier xususiyatlari (videos_per_period/free_minutes/priority/tts_tier) bilan,
faqat narxi va to'lov davri (period_days=365) boshqacha. `Subscription.plan`
ustuni faqat TIER'ni saqlaydi (standard/pro) — oylik/yillik farqi yo'q, chunki
xususiyatlar bir xil. Kvota oynasi (videos_used_this_period) har doim 30 kunda
qayta boshlanadi, to'lov davridan (period_days) MUSTAQIL — aks holda yillik
foydalanuvchi butun yil uchun faqat bir martalik kvota olardi.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.models.database import Subscription, PlanTier
from backend.services.click_service import calculate_price

QUOTA_RESET_DAYS = 30  # video-soni kvotasi har doim shuncha kunda qayta boshlanadi
_FREE_THRESHOLD_MINUTES = 45.0  # click_service.calculate_price bilan bir xil chegara

# Celery navbat nomlari — worker ikkalasini ham tinglaydi (docker-compose.yml,
# "-Q video_processing_priority,video_processing"), lekin ustuvor navbat
# BIRINCHI ko'rsatilgan: Redis transport BRPOP bilan navbatlarni shu tartibda
# tekshiradi, shuning uchun priority navbatidagi job doim birinchi olinadi.
PRIORITY_QUEUE = "video_processing_priority"
DEFAULT_QUEUE = "video_processing"


@dataclass(frozen=True)
class PlanDef:
    id: str
    name: str
    price: int  # UZS / to'lov davri
    videos_per_period: int  # oyiga nechta 45+ daqiqali video BEPUL kiritilgan
    free_minutes: float  # kiritilgan videoning maksimal davomiyligi (undan uzuni odatdagidek to'lanadi)
    priority: bool
    tts_tier: str  # "edge" | "premium"
    tier: PlanTier  # Subscription.plan ustuniga yoziladigan haqiqiy tier
    max_resolution: str  # "360p" | "720p" | "1080p" -- yuklab olish uchun maksimal ruxsat etilgan sifat
    period_days: int = 30  # to'lov davri: 30 = oylik, 365 = yillik


PLANS: dict[str, PlanDef] = {
    "free": PlanDef(id="free", name="Bepul", price=0, videos_per_period=1, free_minutes=5.0, priority=False, tts_tier="edge", tier=PlanTier.FREE, max_resolution="360p"),
    "standard": PlanDef(id="standard", name="Standart", price=49_000, videos_per_period=8, free_minutes=60.0, priority=False, tts_tier="edge", tier=PlanTier.STANDARD, max_resolution="720p"),
    "standard_yearly": PlanDef(id="standard_yearly", name="Standart (yillik)", price=490_000, videos_per_period=8, free_minutes=60.0, priority=False, tts_tier="edge", tier=PlanTier.STANDARD, max_resolution="720p", period_days=365),
    "pro": PlanDef(id="pro", name="Pro", price=149_000, videos_per_period=30, free_minutes=90.0, priority=True, tts_tier="premium", tier=PlanTier.PRO, max_resolution="1080p"),
    "pro_yearly": PlanDef(id="pro_yearly", name="Pro (yillik)", price=1_490_000, videos_per_period=30, free_minutes=90.0, priority=True, tts_tier="premium", tier=PlanTier.PRO, max_resolution="1080p", period_days=365),
}

RESOLUTION_ORDER = ["360p", "720p", "1080p"]


def get_max_resolution_for_job(db, job) -> str:
    """Job egasining JORIY tarifiga qarab -- login qilmagan/egasiz job uchun
    "free" deb hisoblanadi. Yuklab olish havolasi odatda login holatisiz ham
    ochiladi (mavjud /outputs endpointlari auth talab qilmaydi), shuning
    uchun REQUESTER emas, JOB EGASI tarifi tekshiriladi."""
    if job.user_id is None:
        return "360p"
    sub = get_or_create_subscription(db, job.user_id)
    return PLANS[sub.plan.value].max_resolution


def get_max_resolution_for_user(db, user_id) -> str:
    """get_max_resolution_for_job'ning tomoshabin-versiyasi -- Ommaviy
    videolar kutubxonasida (2026-08-19) sifat cheklovi VIDEO EGASI emas,
    TOMOSHA QILAYOTGAN odamning tarifiga qarab belgilanishi kerak (login
    kutubxonada shart, shuning uchun requester har doim ma'lum)."""
    sub = get_or_create_subscription(db, user_id)
    return PLANS[sub.plan.value].max_resolution


def get_or_create_subscription(db, user_id) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if sub is None:
        sub = Subscription(user_id=user_id, plan=PlanTier.FREE, period_started_at=datetime.utcnow())
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    # Muddati o'tgan pullik obuna -> FREE'ga qaytadi, davr qayta boshlanadi.
    if sub.plan != PlanTier.FREE and sub.expires_at and sub.expires_at < datetime.utcnow():
        sub.plan = PlanTier.FREE
        sub.expires_at = None
        sub.period_started_at = datetime.utcnow()
        sub.videos_used_this_period = 0
        db.commit()
        db.refresh(sub)
        return sub

    # "Oyiga N video" kvotasi har doim 30 kunda qayta boshlanadi — to'lov
    # davridan mustaqil, shu jumladan yillik obunalarda ham (aks holda
    # yillik foydalanuvchi butun yil uchun faqat bir martalik kvota olardi).
    if sub.period_started_at and (datetime.utcnow() - sub.period_started_at) > timedelta(days=QUOTA_RESET_DAYS):
        sub.period_started_at = datetime.utcnow()
        sub.videos_used_this_period = 0
        db.commit()
        db.refresh(sub)

    return sub


def check_quota(db, user_id, duration_minutes: float) -> tuple[bool, int]:
    """Berilgan video uchun to'lov kerakmi tekshiradi.

    Returns: (covered_without_payment, price_uzs)
    - 45 daqiqadan qisqa video: har doim (True, 0) — bugungi xatti-harakat, tarifdan mustaqil.
    - 45+ daqiqa, BEPUL tarif: faqat free_minutes ichiga sig'sa va oylik video-soni
      kvotasidan oshmasa (True, 0) — free_minutes shu yerda haqiqiy chegara.
    - 45+ daqiqa, PULLIK tarif (standard/pro): video davomiyligi CHEKLANMAYDI —
      faqat oylik video-soni kvotasi (videos_per_period) tekshiriladi. Foydalanuvchi
      tarifga pul to'lagandan keyin uzun video uchun yana to'lov so'ralishi kutilmagan
      va noto'g'ri edi (aniq foydalanuvchi talabi, 2026-08-13) — free_minutes bu yerda
      faqat pricing sahifasidagi ko'rsatkich, haqiqiy cheklov emas.
    """
    if duration_minutes < _FREE_THRESHOLD_MINUTES:
        return True, 0

    sub = get_or_create_subscription(db, user_id)
    plan = PLANS[sub.plan.value]

    if sub.plan == PlanTier.FREE:
        covered = duration_minutes <= plan.free_minutes and sub.videos_used_this_period < plan.videos_per_period
    else:
        covered = sub.videos_used_this_period < plan.videos_per_period

    if covered:
        return True, 0

    price = calculate_price(duration_minutes, is_first_video=False)
    return False, price


def consume_quota(db, user_id, duration_minutes: float) -> None:
    """45+ daqiqali video kvota ichida (pullik bo'lmasdan) qoplanganda chaqiriladi."""
    if duration_minutes < _FREE_THRESHOLD_MINUTES:
        return  # qisqa videolar kvotaga kirmaydi
    sub = get_or_create_subscription(db, user_id)
    sub.videos_used_this_period += 1
    db.commit()


def refund_quota(db, user_id) -> None:
    """consume_quota() bilan sarflangan kvotani qaytaradi -- job pipeline
    5 marta urinib ham muvaffaqiyatsiz tugasa chaqiriladi
    (backend/workers/tasks.py). DubbingJob.quota_consumed=True bo'lgandagina
    chaqiriladi, shuning uchun qisqa (kvotasiz) videolar bu yerga kelmaydi."""
    sub = get_or_create_subscription(db, user_id)
    if sub.videos_used_this_period > 0:
        sub.videos_used_this_period -= 1
        db.commit()


def activate_subscription(db, user_id, plan_id: str) -> Subscription:
    """To'lov muvaffaqiyatli bo'lgandan keyin chaqiriladi — obunani tanlangan
    tarifning to'lov davriga (plan.period_days: oylik=30, yillik=365) ko'ra
    faollashtiradi/uzaytiradi va kvota hisoblagichini nolga tushiradi."""
    if plan_id not in PLANS or plan_id == "free":
        raise ValueError(f"Noto'g'ri tarif: {plan_id}")

    plan = PLANS[plan_id]
    sub = get_or_create_subscription(db, user_id)
    now = datetime.utcnow()

    # Agar shu tier'da hali faol muddat qolgan bo'lsa (muddati tugashidan oldin
    # yangilangan), o'sha muddatdan uzaytiramiz — to'langan kunlar yo'qolmasin.
    base = sub.expires_at if (sub.plan == plan.tier and sub.expires_at and sub.expires_at > now) else now

    sub.plan = plan.tier
    sub.expires_at = base + timedelta(days=plan.period_days)
    sub.period_started_at = now
    sub.videos_used_this_period = 0
    db.commit()
    db.refresh(sub)
    return sub


def get_job_queue(db, user_id) -> str:
    """Foydalanuvchining joriy tarifiga qarab qaysi Celery navbatiga
    yuborilishi kerakligini aniqlaydi — Pro/Premium (priority=True)
    PRIORITY_QUEUE'ga, qolganlari DEFAULT_QUEUE'ga tushadi. Muddati
    o'tgan/topilmagan obuna FREE deb hisoblanadi (get_or_create_subscription
    o'zi shuni bajaradi). Anonim job (user_id=None) — Subscription.user_id
    NOT NULL bo'lgani uchun bazaga tegmasdan darhol DEFAULT_QUEUE."""
    if user_id is None:
        return DEFAULT_QUEUE
    sub = get_or_create_subscription(db, user_id)
    plan = PLANS[sub.plan.value]
    return PRIORITY_QUEUE if plan.priority else DEFAULT_QUEUE
