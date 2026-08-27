import asyncio
import logging
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from backend.models.database import get_db, DubbingJob, JobStatus, User, ResolutionVariant, ContentViolation
from backend.models.payment import Payment, PaymentStatus, PaymentProvider
from backend.services.auth import get_current_user, get_optional_user
from backend.services.downloader import get_video_info
from backend.config import get_settings
from backend.services.rate_limiter import rate_limit
# Job yaratish mantig'i (video ma'lumot olish, Safety Gate, davomiylik
# chegarasi, kvota) shu yerda -- Telegram bot ham xuddi shu funksiyani
# chaqiradi, ikki joyda saqlanmaydi.
from backend.services.job_creation import (
    MAX_VIDEO_DURATION_MINUTES,
    is_valid_youtube_url as _is_valid_youtube_url,
    create_dubbing_job,
)
from backend.services.click_service import generate_payment_url
import time

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dubbing"])

LIBRARY_ACCESS_PRICE = 5_000  # so'm -- Ommaviy videolar kutubxonasiga bir martalik, umrbod kirish narxi


class CreateJobRequest(BaseModel):
    youtube_url: str
    target_language: str = "uz"
    voice_gender: str = "auto"   # auto / male / female
    audio_mix_mode: str = "dubbed_only"  # dubbed_only / ducked_mix


def _normalize_audio_mix_mode(value: str | None) -> str:
    return value if value in {"dubbed_only", "ducked_mix"} else "dubbed_only"


class VideoInfoResponse(BaseModel):
    title: str
    duration: float
    thumbnail: str
    uploader: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    status_message: Optional[str] = None
    youtube_url: Optional[str] = None
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    video_thumbnail: Optional[str] = None
    output_video_url: Optional[str] = None
    transcript_text: Optional[str] = None
    translated_text: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    created_at: Optional[str] = None
    speaker_gender: Optional[str] = None
    voice_gender_setting: Optional[str] = None
    audio_mix_mode: Optional[str] = None
    uzbek_srt_content: Optional[str] = None
    expected_end_time: Optional[str] = None
    rating: Optional[int] = None
    feedback_comment: Optional[str] = None
    feedback_voice_ok: Optional[bool] = None
    feedback_translation_ok: Optional[bool] = None
    feedback_speed_ok: Optional[bool] = None
    content_flagged: Optional[bool] = None
    fallback_available: bool = False
    fallback_reason: Optional[str] = None


# YouTube yuklab olish DOWNLOAD bosqichida muvaffaqiyatsiz bo'lgan (video
# hech qachon serverga tushmagan) job'lar uchun -- foydalanuvchi videoni
# to'g'ridan-to'g'ri yuklashi mumkinligini bildiradi (POST
# /jobs/{id}/upload-video). Aniqlanishi _job_to_response'da: shunchaki
# original_video_path bo'sh-ligi (boshqa bosqichda muvaffaqiyatsiz bo'lgan
# job uchun video allaqachon bor, qayta yuklash befoyda).


def _job_to_response(job: DubbingJob) -> JobResponse:
    raw_status = job.status.value if hasattr(job.status, "value") else job.status
    status_str = str(raw_status).lower() if raw_status else "pending"
    
    expected_end_time = None
    if status_str not in ("completed", "failed", "awaiting_payment"):
        duration = job.video_duration or 300.0
        baseline_dt = job.updated_at or job.created_at
        progress = job.progress or 0.0
        remaining_factor = max(0.1, (100.0 - progress) / 100.0)
        est_seconds = (30 + 0.3 * duration) * remaining_factor
        expected_dt = baseline_dt + timedelta(seconds=est_seconds)
        expected_end_time = expected_dt.isoformat() + "Z"

    return JobResponse(
        job_id=str(job.id),
        status=status_str,
        progress=job.progress or 0.0,
        status_message=job.status_message,
        youtube_url=job.youtube_url,
        video_title=job.video_title,
        video_duration=job.video_duration,
        video_thumbnail=job.video_thumbnail,
        output_video_url=job.output_video_url,
        transcript_text=job.transcript_text,
        translated_text=job.translated_text,
        error_message=job.error_message,
        error_code=job.error_code,
        created_at=job.created_at.isoformat() if job.created_at else None,
        speaker_gender=job.speaker_gender,
        voice_gender_setting=job.voice_gender_setting,
        audio_mix_mode=job.audio_mix_mode or settings.AUDIO_MIX_MODE,
        uzbek_srt_content=job.uzbek_srt_content,
        expected_end_time=expected_end_time,
        rating=job.rating,
        feedback_comment=job.feedback_comment,
        feedback_voice_ok=job.feedback_voice_ok,
        feedback_translation_ok=job.feedback_translation_ok,
        feedback_speed_ok=job.feedback_speed_ok,
        content_flagged=job.content_flagged,
        # "Video hech qachon serverga tushmadi" -- error_code'ning aniq
        # qaysi so'z bilan yozilganiga qaramasdan, o'zi to'liq va ishonchli
        # signal (agar TRANSCRIBE yoki keyingi bosqichda muvaffaqiyatsiz
        # bo'lgan bo'lsa, original_video_path allaqachon to'ldirilgan
        # bo'ladi). error_code ro'yxatiga qarab tekshirish - eski,
        # klassifikatordan OLDINGI "DOWNLOAD_FAILED" kabi qiymatlarni
        # noto'g'ri chetlab qo'ygan edi (2026-08-23 aniqlangan).
        fallback_available=status_str == "failed" and not job.original_video_path,
        fallback_reason="YOUTUBE_DOWNLOAD_FAILED" if status_str == "failed" and not job.original_video_path else None,
    )


@router.get("/video-info", dependencies=[Depends(rate_limit("video_info", 20, 600))])
async def video_info(url: str) -> VideoInfoResponse:
    try:
        # get_video_info bloklovchi (yt-dlp tarmoq so'rovlari + bot-check
        # qayta urinishlarida time.sleep) — thread'ga chiqarilmasa, butun
        # asyncio event loop'ni to'sib qo'yadi va HATTO /health kabi
        # bog'liqsiz so'rovlar ham javob bermay qoladi (2026-08-13
        # productionda haqiqiy uzilish orqali tasdiqlangan).
        info = await asyncio.to_thread(get_video_info, url)
        return VideoInfoResponse(**info)
    except Exception as e:
        # Xom kutubxona xatosini (yt-dlp/YouTube API) foydalanuvchiga
        # ko'rsatmaymiz -- faqat serverda log qilamiz.
        logger.exception(f"video_info xato: {url}")
        raise HTTPException(status_code=400, detail="Video ma'lumotlarini olib bo'lmadi. Havola to'g'riligini tekshiring yoki birozdan so'ng qaytadan urinib ko'ring.")


@router.post("/jobs", status_code=201, dependencies=[Depends(rate_limit("create_job", 8, 600))])
async def create_job(
    request: CreateJobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Yaratish mantig'i backend/services/job_creation.py'da -- Telegram bot
    # ham xuddi shu funksiyani chaqiradi, ikki joyda saqlanmaydi.
    result = await create_dubbing_job(
        db,
        current_user,
        request.youtube_url,
        request.voice_gender,
        _normalize_audio_mix_mode(request.audio_mix_mode),
    )

    if result.outcome == "invalid_url":
        raise HTTPException(status_code=400, detail="Faqat YouTube URL qabul qilinadi.")
    if result.outcome == "fetch_error":
        raise HTTPException(status_code=400, detail=f"Video ma'lumotlarini olishda xatolik: {result.error_detail}")
    if result.outcome == "blocked":
        raise HTTPException(
            status_code=403,
            detail="Ushbu video GapirAI.uz kontent siyosatiga mos kelmagani sababli dublaj qilinmaydi.",
        )
    if result.outcome == "too_long":
        raise HTTPException(
            status_code=400,
            detail=f"Video juda uzun ({result.duration_minutes:.0f} daqiqa). Maksimal ruxsat etilgan davomiylik — {MAX_VIDEO_DURATION_MINUTES} daqiqa.",
        )
    if result.outcome == "queued":
        return {"job_id": result.job_id, "status": "pending"}
    if result.outcome == "ready":
        # Kesh-hit, bepul/kvota bilan qoplangan -- darhol tayyor (job DB'da
        # allaqachon COMPLETED, backend/services/job_creation.py).
        return {"job_id": result.job_id, "status": "completed"}

    # "awaiting_payment"
    return {"job_id": result.job_id, "status": "awaiting_payment", "amount": result.amount}


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobResponse:
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job topilmadi.")
    return _job_to_response(job)


@router.get("/jobs")
def list_jobs(
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobResponse]:
    """Foydalanuvchining o'z joblari."""
    jobs = (
        db.query(DubbingJob)
        .filter(DubbingJob.user_id == current_user.id)
        .order_by(DubbingJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_job_to_response(j) for j in jobs]


# Faqat DOWNLOAD bosqichida haqiqatan ham to'xtagan job'lar uchun mo'ljallangan
# fallback -- backend/services/downloader.py'ning MAX_DOWNLOAD_SIZE_BYTES bilan
# bir xil chegara.
MAX_UPLOAD_SIZE_BYTES = 3 * 1024 * 1024 * 1024  # 3 GB


def _existing_local_media_path(path: str | None) -> Path | None:
    """Локальный media-файл, если он доступен как резерв S3.

    Пути в PostgreSQL могут быть относительными (например,
    ``outputs/<job>/dubbed_final.mp4``), поэтому разрешаем их относительно
    текущего каталога сервиса. Это позволяет пережить удаление S3-объекта
    lifecycle-политикой, пока локальная копия ещё существует.
    """
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        if candidate.is_file() and os.access(candidate, os.R_OK):
            return candidate
    except OSError:
        pass
    return None
_ALLOWED_UPLOAD_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm"}


def _get_media_duration_seconds(path: str) -> float | None:
    """ffprobe orqali video/audio davomiyligini aniqlaydi. Xato bo'lsa None."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True, text=True, check=True, timeout=10,
        )
        import json as _json
        return float(_json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return None


@router.post("/jobs/{job_id}/upload-video", dependencies=[Depends(rate_limit("upload_video", 10, 600))])
async def upload_video_fallback(
    job_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """YouTube yuklab olish DOWNLOAD bosqichida muvaffaqiyatsiz bo'lgan job
    uchun fallback -- foydalanuvchi video faylini to'g'ridan-to'g'ri yuklaydi.

    Mavjud pipeline'ga MINIMAL diff bilan ulanadi: backend/workers/tasks.py
    process_video()'ning o'zi allaqachon "agar original_video_path va
    audio.wav mavjud bo'lsa, DOWNLOAD bosqichini o'tkazib yuborish"
    checkpoint'iga ega edi (checkpoint retry uchun yozilgan, lekin bu yerda
    ham to'g'ridan-to'g'ri ishlaydi) -- process_video'ning o'zi o'zgarmadi,
    faqat shu ikki faylni to'g'ri joyga qo'yib, job'ni qayta navbatga
    qo'yamiz. 2026-08-23, Webshare proksi balansi tugashi natijasida ko'p
    YouTube yuklab olish muvaffaqiyatsiz bo'lgani sababli qo'shildi."""
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job topilmadi.")
    if job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sizda bu job uchun ruxsat yo'q.")
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Bu funksiya faqat muvaffaqiyatsiz job'lar uchun mavjud.")
    if job.original_video_path:
        raise HTTPException(
            status_code=400,
            detail="Bu job uchun video allaqachon yuklab olingan edi — muammo YouTube yuklab olishda emas.",
        )
    if file.content_type not in _ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Faqat MP4, MOV, MKV yoki WebM formatlar qabul qilinadi.")

    job_dir = Path(settings.UPLOAD_DIR) / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    video_path = job_dir / f"video{ext}"

    size = 0
    try:
        with open(video_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Fayl hajmi {MAX_UPLOAD_SIZE_BYTES // (1024 ** 3)} GB dan katta bo'lmasligi kerak.",
                    )
                f.write(chunk)
    except HTTPException:
        video_path.unlink(missing_ok=True)
        raise

    # Audio ajratish -- backend/services/downloader.py'dagi bilan bir xil
    # ffmpeg buyrug'i (transkripsiya aynan shu formatdagi WAV faylni kutadi).
    audio_path = job_dir / "audio.wav"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        video_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Video faylini o'qib bo'lmadi — fayl buzilgan yoki qo'llab-quvvatlanmaydigan bo'lishi mumkin.",
        )

    duration = _get_media_duration_seconds(str(video_path))

    job.original_video_path = str(video_path)
    if duration:
        job.video_duration = duration
    job.status = JobStatus.PENDING
    job.status_message = "Video qabul qilindi. Navbatga qo'shildi."
    job.error_message = None
    job.error_code = None
    job.updated_at = datetime.utcnow()
    db.commit()

    from backend.workers.tasks import process_video
    from backend.services.plans import get_job_queue
    process_video.apply_async(args=[str(job_id)], task_id=str(job_id), queue=get_job_queue(db, current_user.id))

    return {"success": True, "message": "Video qabul qilindi, ishlov berish boshlandi."}


class LibraryItem(BaseModel):
    job_id: str
    youtube_url: str
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    video_thumbnail: Optional[str] = None
    speaker_gender: Optional[str] = None
    created_at: Optional[str] = None


@router.get("/library", dependencies=[Depends(rate_limit("library", 60, 600))])
def list_public_library(
    limit: int = Query(24, le=60),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[LibraryItem]:
    """Ommaviy katalog -- barcha tugallangan, ASL (source_job_id yo'q,
    ya'ni kesh-nusxa emas) joblar, hech qanday login talab qilinmaydi.
    ContentViolation'da qayd etilgan (hatto faqat ogohlantirish darajasida
    ham) URL'lar bu ro'yxatda ko'rinmaydi -- ochiq kashfiyot ro'yxati
    to'g'ridan-to'g'ri so'ralgan (bilingan URL) qayta yuklashdan farqli
    o'laroq ancha kengroq auditoriyaga chiqadi, shuning uchun bu yerda
    ehtiyotkorroq filtr qo'llaymiz."""
    flagged_urls = db.query(ContentViolation.youtube_url).distinct()
    jobs = (
        db.query(DubbingJob)
        .filter(
            DubbingJob.status == JobStatus.COMPLETED,
            DubbingJob.source_job_id.is_(None),
            DubbingJob.content_flagged.is_(False),
            DubbingJob.youtube_url.notin_(flagged_urls),
        )
        .order_by(DubbingJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        LibraryItem(
            job_id=str(j.id),
            youtube_url=j.youtube_url,
            video_title=j.video_title,
            video_duration=j.video_duration,
            video_thumbnail=j.video_thumbnail,
            speaker_gender=j.speaker_gender,
            created_at=j.created_at.isoformat() if j.created_at else None,
        )
        for j in jobs
    ]


@router.get("/library/{job_id}/eligible")
def library_item_eligible(job_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Bitta job hozir ham ommaviy kutubxonaga mos keladimi -- tomosha
    sahifasi (/library/[id]) to'g'ridan-to'g'ri havola orqali ochilganda
    ham kontent xavfsizligi bo'yicha keyinchalik bayroqlangan videoni
    ko'rsatmaslik uchun ishlatiladi (GET /api/library ro'yxati o'zi bunday
    videoni ko'rsatmaydi, lekin uni bilgan odam to'g'ridan-to'g'ri havola
    bilan ochib olishi mumkin edi -- shu bo'shliqni yopadi)."""
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or job.status != JobStatus.COMPLETED or job.source_job_id is not None or job.content_flagged:
        return {"eligible": False}
    flagged = db.query(ContentViolation).filter(ContentViolation.youtube_url == job.youtube_url).first()
    return {"eligible": flagged is None}


@router.get("/library/{job_id}/resolutions")
def list_library_resolutions(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """list_resolutions bilan bir xil, lekin sifat cheklovi TOMOSHABIN
    (current_user) tarifiga qarab hisoblanadi, video egasiniki emas --
    kutubxonada tomosha qilayotgan odam ko'pincha video egasi emas
    (2026-08-19, foydalanuvchi so'rovi).

    2026-08-21: bu yerda ilgari FAQAT current_user borligi tekshirilardi --
    kutubxona kirish to'lovini (5 000 so'm) qilmagan har qanday login qilgan
    foydalanuvchi ham to'liq ro'yxatni (barcha rezolyutsiyalar "available")
    ko'ra olardi. Frontend sahifasi (/library/[id]) to'lovni tekshirib
    yo'naltiradi, lekin API'ning o'zi tekshirmagani uchun to'g'ridan-to'g'ri
    chaqirilsa bo'shliq bo'lardi."""
    if current_user.library_access_purchased_at is None:
        raise HTTPException(status_code=403, detail="Kutubxonaga kirish huquqi yo'q — avval 5 000 so'm to'lovini amalga oshiring.")

    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Video hali tayyor emas.")

    from backend.services.plans import RESOLUTION_ORDER
    # 2026-08-19: foydalanuvchi so'rovi bilan kutubxonada 1080p VAQTINCHA barcha
    # tomoshabinlar uchun bepul -- get_max_resolution_for_user() chaqiruvi
    # o'chirilgan, qaytarish uchun uni tiklash kifoya.
    max_idx = len(RESOLUTION_ORDER) - 1

    variant_status = {
        v.resolution: v.status
        for v in db.query(ResolutionVariant).filter(ResolutionVariant.job_id == job.storage_id).all()
    }

    master_missing = False
    if settings.AWS_BUCKET_NAME:
        from backend.services.storage import s3_object_exists
        master_missing = (
            not s3_object_exists(f"dubber/{job.storage_id}/dubbed_final.mp4")
            and _existing_local_media_path(job.output_video_path) is None
        )

    resolutions = []
    for i, res in enumerate(RESOLUTION_ORDER):
        available = i <= max_idx
        status = "ready" if res == "720p" else variant_status.get(res, "not_requested")
        if master_missing and status == "ready":
            status = "expired"
        resolutions.append({"resolution": res, "available": available, "status": status})

    return {"resolutions": resolutions}


@router.post("/library/{job_id}/resolutions/{resolution}")
def request_library_resolution(
    job_id: uuid.UUID,
    resolution: str,
    download: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """request_resolution bilan bir xil, lekin TOMOSHABIN tarifi bo'yicha
    (yuqoridagi list_library_resolutions bilan bir xil sabab). To'lov
    tekshiruvi ham xuddi shu funksiyada bir xil sababga ko'ra kerak edi."""
    if current_user.library_access_purchased_at is None:
        raise HTTPException(status_code=403, detail="Kutubxonaga kirish huquqi yo'q — avval 5 000 so'm to'lovini amalga oshiring.")

    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Video hali tayyor emas.")

    from backend.services.resolution_variants import request_resolution as _request_resolution
    # 2026-08-19: yuqoridagi list_library_resolutions bilan bir xil sabab --
    # kutubxonada 1080p vaqtincha barcha tomoshabinlar uchun bepul.
    result = _request_resolution(
        db,
        job,
        resolution,
        max_resolution_override="1080p",
        download=download,
    )

    if result.outcome == "invalid":
        raise HTTPException(status_code=400, detail="Noto'g'ri rezolyutsiya.")
    if result.outcome == "forbidden":
        raise HTTPException(status_code=403, detail="Bu sifat sizning tarif rejangizda mavjud emas.")
    if result.outcome == "expired":
        raise HTTPException(status_code=410, detail="Bu video fayli endi mavjud emas — saqlash muddati tugagan.")
    if result.outcome == "ready":
        return {"status": "ready", "download_url": result.download_url}
    return {"status": "processing"}


@router.get("/library/access")
def get_library_access(
    current_user: User = Depends(get_current_user),
) -> dict:
    return {"has_access": current_user.library_access_purchased_at is not None}


@router.post("/library/purchase")
def purchase_library_access(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Ommaviy videolar kutubxonasiga bir martalik kirish to'lovi -- job_id
    yoki plan bilan bog'liq emas (Payment.is_library_access orqali
    ajratiladi, backend/api/click_routes.py:click_complete)."""
    if current_user.library_access_purchased_at is not None:
        return {"success": True, "message": "Kirish huquqi allaqachon mavjud.", "amount": 0}

    existing_pending = db.query(Payment).filter(
        Payment.user_id == current_user.id,
        Payment.is_library_access.is_(True),
        Payment.status == PaymentStatus.PENDING,
    ).first()

    if not existing_pending:
        payment = Payment(
            user_id=current_user.id,
            is_library_access=True,
            amount=LIBRARY_ACCESS_PRICE,
            provider=PaymentProvider.CLICK,
            status=PaymentStatus.PENDING,
            click_create_time=int(time.time()),
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
    else:
        payment = existing_pending

    merchant_id = settings.CLICK_MERCHANT_ID or "56653"
    service_id = settings.CLICK_SERVICE_ID or "108780"
    merchant_user_id = getattr(settings, "CLICK_MERCHANT_USER_ID", "") or "89102"

    origin_header = request.headers.get("origin") or request.headers.get("referer")
    if origin_header:
        parsed = urlparse(origin_header)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        return_url = f"{base_origin}/library"
    else:
        frontend_url = settings.FRONTEND_URL or "https://gapirai.uz"
        return_url = f"{frontend_url.rstrip('/')}/library"

    payment_url = generate_payment_url(
        merchant_id=merchant_id,
        service_id=service_id,
        transaction_param=str(payment.id),
        amount=LIBRARY_ACCESS_PRICE,
        return_url=return_url,
        merchant_user_id=merchant_user_id,
    )

    return {
        "success": True,
        "payment_url": payment_url,
        "payment_id": str(payment.id),
        "amount": LIBRARY_ACCESS_PRICE,
    }


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(DubbingJob).filter(
        DubbingJob.id == job_id,
        DubbingJob.user_id == current_user.id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job topilmadi.")
    db.delete(job)
    db.commit()


@router.get("/jobs/{job_id}/subtitles.vtt")
def get_subtitles(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """O'zbekcha subtitrlarni WebVTT formatida qaytarish."""
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or not job.uzbek_srt_content:
        raise HTTPException(status_code=404, detail="Subtitrlar topilmadi.")
    return Response(
        content=job.uzbek_srt_content,
        media_type="text/vtt",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get("/outputs/{job_id}/audio")
def download_audio(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Dublyaj qilingan audioni WAV formatida yuklab olish."""
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Audio hali tayyor emas.")

    settings = get_settings()
    if settings.AWS_BUCKET_NAME:
        from backend.services.storage import generate_presigned_download_url, s3_object_exists
        s3_key = f"dubber/{job.storage_id}/dubbed_audio.wav"
        if s3_object_exists(s3_key):
            presigned_url = generate_presigned_download_url(s3_key)
            if presigned_url:
                return Response(status_code=307, headers={"Location": presigned_url})

    audio_path = _existing_local_media_path(job.dubbed_audio_path)
    if audio_path is None:
        raise HTTPException(status_code=410, detail="Audio fayl endi mavjud emas — saqlash muddati tugagan.")
    safe_title = re.sub(r'[^\w\s-]', '', job.video_title or str(job_id))[:50].strip()
    filename = f"{safe_title or job_id}_audio.wav"
    return FileResponse(path=audio_path, media_type="audio/wav", filename=filename)


@router.get("/outputs/{job_id}/video")
def download_video(
    job_id: uuid.UUID,
    download: bool = Query(False),
    db: Session = Depends(get_db),
):
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Video hali tayyor emas.")

    settings = get_settings()
    if settings.AWS_BUCKET_NAME:
        from backend.services.storage import generate_presigned_download_url, s3_object_exists
        s3_key = f"dubber/{job.storage_id}/dubbed_final.mp4"
        if s3_object_exists(s3_key):
            presigned_url = generate_presigned_download_url(s3_key, download=download)
            if presigned_url:
                return Response(status_code=307, headers={"Location": presigned_url})

    video_path = _existing_local_media_path(job.output_video_path)
    if video_path is None:
        raise HTTPException(status_code=410, detail="Video fayl endi mavjud emas — saqlash muddati tugagan.")
    safe_title = re.sub(r'[^\w\s-]', '', job.video_title or str(job_id))[:50].strip()
    filename = f"dubbed_{safe_title or job_id}.mp4"
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )


@router.get("/jobs/{job_id}/resolutions")
def list_resolutions(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Tarif bo'yicha ruxsat etilgan va tayyor rezolyutsiyalar ro'yxati.
    720p har doim "ready" -- u master fayl, alohida generatsiya kerak emas."""
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Video hali tayyor emas.")

    from backend.services.plans import get_max_resolution_for_job, RESOLUTION_ORDER
    max_idx = RESOLUTION_ORDER.index(get_max_resolution_for_job(db, job))

    variant_status = {
        v.resolution: v.status
        for v in db.query(ResolutionVariant).filter(ResolutionVariant.job_id == job.storage_id).all()
    }

    # Master S3 lifecycle (3 kun) bo'yicha allaqachon o'chirilgan bo'lishi
    # mumkin -- shu holatda 720p "ready" ko'rsatib, bosilganda 410 bilan
    # yiqilishidan ko'ra, ro'yxatning o'zida "expired" ko'rsatish yaxshiroq.
    master_missing = False
    if settings.AWS_BUCKET_NAME:
        from backend.services.storage import s3_object_exists
        master_missing = (
            not s3_object_exists(f"dubber/{job.storage_id}/dubbed_final.mp4")
            and _existing_local_media_path(job.output_video_path) is None
        )

    resolutions = []
    for i, res in enumerate(RESOLUTION_ORDER):
        available = i <= max_idx
        status = "ready" if res == "720p" else variant_status.get(res, "not_requested")
        if master_missing and status == "ready":
            status = "expired"
        resolutions.append({"resolution": res, "available": available, "status": status})

    return {"resolutions": resolutions}


@router.post("/jobs/{job_id}/resolutions/{resolution}")
def request_resolution(
    job_id: uuid.UUID,
    resolution: str,
    download: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Berilgan rezolyutsiyani so'raydi -- 720p darhol qaytadi (master fayl),
    360p/1080p mavjud bo'lmasa Celery task navbatga qo'yiladi va "processing"
    qaytariladi (frontend buni pollaydi). Mantiq resolution_variants.py'da --
    Telegram bot ham xuddi shu funksiyani chaqiradi, ikki joyda saqlanmaydi."""
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job or job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Video hali tayyor emas.")

    from backend.services.resolution_variants import request_resolution as _request_resolution
    result = _request_resolution(db, job, resolution, download=download)

    if result.outcome == "invalid":
        raise HTTPException(status_code=400, detail="Noto'g'ri rezolyutsiya.")
    if result.outcome == "forbidden":
        raise HTTPException(status_code=403, detail="Bu sifat sizning tarif rejangizda mavjud emas.")
    if result.outcome == "expired":
        raise HTTPException(status_code=410, detail="Bu video fayli endi mavjud emas — saqlash muddati tugagan.")
    if result.outcome == "ready":
        return {"status": "ready", "download_url": result.download_url}
    return {"status": "processing"}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job topilmadi.")
    
    active_statuses = [
        JobStatus.PENDING,
        JobStatus.AWAITING_PAYMENT,
        JobStatus.DOWNLOADING,
        JobStatus.TRANSCRIBING,
        JobStatus.TRANSLATING,
        JobStatus.SYNTHESIZING,
        JobStatus.SYNCING,
        JobStatus.MERGING
    ]
    if job.status not in active_statuses:
        return {"success": False, "message": "Job active holatda emas, bekor qilib bo'lmaydi."}

    from backend.workers.celery_app import celery_app
    try:
        celery_app.control.revoke(str(job_id), terminate=True)
    except Exception:
        pass
    
    job.status = JobStatus.FAILED
    job.status_message = "Foydalanuvchi tomonidan bekor qilindi."
    job.error_message = "User cancelled the job."
    job.updated_at = datetime.utcnow()
    db.commit()

    # Bekor qilingan job hech qachon yakunlanmaydi — yarim qolgan yuklama
    # va sintez fayllarini darhol tozalaymiz.
    for base_dir in (settings.UPLOAD_DIR, settings.OUTPUT_DIR):
        job_dir = Path(base_dir) / str(job_id)
        if job_dir.exists():
            try:
                shutil.rmtree(job_dir)
            except Exception:
                pass

    return {"success": True, "message": "Dublyaj bekor qilindi."}


class PlatformFeedbackRequest(BaseModel):
    message: str
    rating: Optional[int] = None


@router.post("/platform-feedback", dependencies=[Depends(rate_limit("platform_feedback", 10, 600))])
def submit_platform_feedback(
    req: PlatformFeedbackRequest,
    current_user: Optional[User] = Depends(get_optional_user),
):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Fikr matni bo'sh bo'lmasligi kerak.")
    if req.rating is not None and (req.rating < 1 or req.rating > 5):
        raise HTTPException(status_code=400, detail="Baho 1 va 5 orasida bo'lishi kerak.")

    try:
        from backend.services.telegram_service import send_telegram_platform_feedback
        send_telegram_platform_feedback(
            message=message,
            rating=req.rating,
            user_email=current_user.email if current_user else None,
        )
    except Exception:
        pass

    return {"success": True, "message": "Fikringiz uchun rahmat!"}


class FeedbackRequest(BaseModel):
    rating: int  # 1 to 5
    comment: Optional[str] = None
    chat_id: Optional[str] = None
    voice_ok: Optional[bool] = None
    translation_ok: Optional[bool] = None
    speed_ok: Optional[bool] = None


@router.post("/jobs/{job_id}/feedback", dependencies=[Depends(rate_limit("feedback", 20, 600))])
def submit_feedback(
    job_id: uuid.UUID,
    req: FeedbackRequest,
    db: Session = Depends(get_db),
):
    if req.rating < 1 or req.rating > 5:
        raise HTTPException(status_code=400, detail="Baho 1 va 5 orasida bo'lishi kerak.")

    job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job topilmadi.")

    job.rating = req.rating
    job.feedback_comment = req.comment
    job.feedback_created_at = datetime.utcnow()
    job.feedback_voice_ok = req.voice_ok
    job.feedback_translation_ok = req.translation_ok
    job.feedback_speed_ok = req.speed_ok
    db.commit()

    # Telegram xabarnoma yuborish
    try:
        from backend.services.telegram_service import send_telegram_feedback
        send_telegram_feedback(
            job_id=str(job.id),
            video_title=job.video_title or "Video",
            rating=req.rating,
            comment=req.comment,
            chat_id=req.chat_id,
            voice_ok=req.voice_ok,
            translation_ok=req.translation_ok,
            speed_ok=req.speed_ok,
        )
    except Exception as err:
        pass

    return {"success": True, "message": "Fikringiz va baholashingiz uchun rahmat!"}


