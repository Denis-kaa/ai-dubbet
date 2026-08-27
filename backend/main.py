from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import os
import uuid

# Root logger sozlanmagan bo'lsa, backend/services/**'dagi 25+ modulning
# logger.info/warning/error() chaqiruvlari jim yo'qolib ketadi (faqat
# WARNING+ logging.lastResort orqali stderr'ga chiqadi) -- worker
# konteyneridan farqli o'laroq (Celery o'zi logging'ni sozlaydi), FastAPI
# jarayoni buni hech qachon o'z-o'zidan sozlamagan. telegram_bot.py'dagi
# bilan bir xil format ishlatiladi (2026-08-20).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from backend.config import get_settings
from backend.models.database import create_tables
from backend.api.routes import router
from backend.api.auth_routes import router as auth_router
from backend.api.click_routes import router as click_router
from backend.api.payme_routes import router as payme_router
from backend.api.paynet_routes import router as paynet_router
from backend.api.uzum_routes import router as uzum_router
from backend.api.admin_routes import router as admin_router
from backend.api.video_analysis_routes import router as video_analysis_router
from backend.api.plans_routes import router as plans_router

settings = get_settings()

# RECOVERY_STUCK_MINUTES — "qotib qolgan" job hisoblanadigan chegara:
# aktive-status job `updated_at`'si shu daqiqadan ko'p eskirgan bo'lsa,
# crashdan keyin qayta ishga tushiriladi. 15 daqiqadan kam — worker hali
# ishlab turgan (yangilanayotgan) joblarni re-enqueue qilishdan saqlaydi.
RECOVERY_STUCK_MINUTES = 15


def recover_stuck_jobs():
    """Crash'dan keyin qotib qolgan (aktive-status, lekin `updated_at`
    STALE — `RECOVERY_STALE_MINUTES` dan ortiq yangilanmagan) joblarni
    PENDING ga qaytarib re-enqueue qiladi.

    FILTER (AUDIT_STABILITY.md §3 P0-1): ilgari barcha aktive-status
    joblar qayta ishga tushirilardi — backend/qayta ishga tushganda
    worker hali ishlab turgan job ham re-enqueue qilinardi, xuddi shu
    `task_id` bilan ikkinchi parallellashtirish paydo bo'lib, ikki marta
    bajarilish (download/LLM xarajat 2x, fayl gonalari) hosil qilar edi.
    Endi faqat `updated_at` eskirganlar qayta yuboriladi — bu "haqiqiy
    tiki" (oqim jonli ishlab turgan job updated_at'ni yangilab turadi).
    """
    from datetime import timedelta
    from datetime import datetime
    from backend.models.database import SessionLocal, DubbingJob, JobStatus
    from backend.workers.tasks import process_video
    from backend.services.plans import get_job_queue
    db = SessionLocal()
    try:
        active_statuses = [
            JobStatus.PENDING,
            JobStatus.DOWNLOADING,
            JobStatus.TRANSCRIBING,
            JobStatus.TRANSLATING,
            JobStatus.SYNTHESIZING,
            JobStatus.SYNCING,
            JobStatus.MERGING
        ]
        cutoff = datetime.utcnow() - timedelta(minutes=RECOVERY_STUCK_MINUTES)
        stuck_jobs = (
            db.query(DubbingJob)
            .filter(DubbingJob.status.in_(active_statuses))
            .filter(DubbingJob.updated_at < cutoff)   # kluch: faqat haqiqiyan tikiplib qotganlar
            .all()
        )
        if stuck_jobs:
            for job in stuck_jobs:
                print(f"[RECOVERY] Re-enqueueing stuck job {job.id} (updated_at={job.updated_at})")
                job.status = JobStatus.PENDING
                job.status_message = "Tizim qayta ishga tushgandan so'ng jarayon qayta tiklandi."
                db.commit()
                process_video.apply_async(args=[str(job.id)], task_id=str(job.id), queue=get_job_queue(db, job.user_id))
    except Exception as e:
        print(f"[RECOVERY ERROR] Error during job recovery: {e}")
    finally:
        db.close()


def recover_stuck_resolution_variants():
    """360p/1080p generatsiyasi ham xuddi shu muammoga duchor bo'lishi
    mumkin -- vazifa worker qayta ishga tushishi (deploy) yoki servis
    ishdan chiqishi paytida uzilib qolsa, status "processing"da abadiy
    qotib qoladi (request_resolution faqat status "processing" BO'LMASA
    yangi vazifa navbatga qo'yadi, shuning uchun o'zi hech qachon
    tuzalmaydi). 2026-08-21 aniqlangan -- ikkita haqiqiy job'da kunlar
    davomida qotib qolgan holat topilgan."""
    from backend.models.database import SessionLocal, ResolutionVariant
    from backend.workers.resolution_tasks import generate_resolution_variant_task
    db = SessionLocal()
    try:
        stuck = db.query(ResolutionVariant).filter(ResolutionVariant.status == "processing").all()
        for variant in stuck:
            print(f"[RECOVERY] Re-enqueueing stuck resolution variant {variant.job_id}/{variant.resolution}")
            generate_resolution_variant_task.apply_async(args=[str(variant.job_id), variant.resolution])
    except Exception as e:
        print(f"[RECOVERY ERROR] Error during resolution variant recovery: {e}")
    finally:
        db.close()


def recover_stuck_analyses():
    """recover_stuck_jobs bilan bir xil FILTER — eskirgan VideoAnalysis'lar
    qayta enqueue qilinadi, jonli ishlab turganlariga tegmaydi."""
    from datetime import timedelta
    from datetime import datetime
    from backend.models.database import SessionLocal, VideoAnalysis, AnalysisStatus
    from backend.workers.analysis_tasks import analyze_video_task
    db = SessionLocal()
    try:
        active_statuses = [
            AnalysisStatus.PENDING,
            AnalysisStatus.DOWNLOADING,
            AnalysisStatus.EXTRACTING_AUDIO,
            AnalysisStatus.TRANSCRIBING,
            AnalysisStatus.ANALYZING,
            AnalysisStatus.GENERATING_RESULTS,
        ]
        cutoff = datetime.utcnow() - timedelta(minutes=RECOVERY_STUCK_MINUTES)
        stuck = (
            db.query(VideoAnalysis)
            .filter(VideoAnalysis.status.in_(active_statuses))
            .filter(VideoAnalysis.updated_at < cutoff)
            .all()
        )
        for analysis in stuck:
            print(f"[RECOVERY] Re-enqueueing stuck analysis {analysis.id} (updated_at={analysis.updated_at})")
            analysis.status = AnalysisStatus.PENDING
            analysis.status_message = "Tizim qayta ishga tushgandan so'ng jarayon qayta tiklandi."
            db.commit()
            analyze_video_task.apply_async(args=[str(analysis.id)], task_id=str(analysis.id))
    except Exception as e:
        print(f"[RECOVERY ERROR] Error during analysis recovery: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    create_tables()
    
    # Clear stale concurrent download locks
    try:
        from redis import Redis
        r = Redis.from_url(settings.REDIS_URL)
        r.delete("yt_dl:concurrent")
        print("[STARTUP] Cleared stale yt-dlp concurrency lock from Redis.")
    except Exception as e:
        print(f"[STARTUP ERROR] Could not clear Redis locks: {e}")

    recover_stuck_jobs()
    recover_stuck_resolution_variants()
    recover_stuck_analyses()
    yield
    # Shutdown (agar kerak bo'lsa)


app = FastAPI(
    title="GapirAI.uz API",
    description="YouTube videolarini sun'iy intellekt yordamida o'zbek tiliga dublyaj va tarjima qilish platformasi API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — Next.js frontendi uchun. Ilgari "*" (istalgan sayt) edi -- 2026-08-20
# audit paytida wildcard CORS aniqlanib, haqiqiy ruxsat etilgan originlar
# ro'yxatiga almashtirildi (www ham gapirai.uz bilan bir xil saytni
# ko'rsatadi -- nginx/DNS orqali tasdiqlangan, shuning uchun ro'yxatda).
_allowed_origins = [
    settings.FRONTEND_URL,
    "https://www.gapirai.uz",
    "https://admin.gapirai.uz",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_allowed_origins)),  # tartibni saqlab dublikatlarni olib tashlaydi
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Barcha ushlanmagan xatoliklar shu yerga tushadi. Avval bu yerda
    xom `str(exc)` to'g'ridan-to'g'ri foydalanuvchiga qaytarilardi (ichki
    xato matnini, ba'zan fayl yo'llari yoki kutubxona ichki tafsilotlarini
    ochib qo'yardi) va hech qayerda log qilinmasdi. Endi: to'liq
    traceback serverda log qilinadi (qisqa xato ID bilan, docker compose
    logs orqali ko'rinadi), foydalanuvchiga esa faqat xavfsiz umumiy xabar
    + shu ID qaytariladi."""
    error_id = uuid.uuid4().hex[:8]
    logger.exception(f"[{error_id}] Ushlanmagan xatolik: {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Kutilmagan xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring. (Xato ID: {error_id})"},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Credentials": "true",
        },
    )

# API routerlar
app.include_router(auth_router)
app.include_router(router)
app.include_router(click_router)
app.include_router(payme_router)
app.include_router(paynet_router)
app.include_router(uzum_router)
app.include_router(admin_router)
app.include_router(video_analysis_router)
app.include_router(plans_router)

# Tayyor videolarni statik fayl sifatida serve qilish
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "GapirAI.uz"}
