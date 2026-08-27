"""Tarif bo'yicha yuklab olish sifati (360p/720p/1080p) uchun qo'shimcha
video versiyalarini yaratadi. 720p uchun bu modul chaqirilmaydi -- u
allaqachon master fayl (dubber/{job_id}/dubbed_final.mp4), chunki
downloader.py manba videoni shu chegarada yuklab oladi.

360p -- masterdan arzon KICHRAYTIRISH (audio qayta aralashtirilmaydi).
1080p -- masterda haqiqiy 1080p tafsilot yo'q (manba 720p da yuklab
olingan), shuning uchun YouTube manbasi qayta 1080p gacha yuklab olinadi va
merger.merge_video_audio() bilan qayta birlashtiriladi -- lekin dublyaj
audiosi ALLAQACHON mavjud (lokal diskda yoki S3'da; transkripsiya/tarjima/
TTS bosqichlari QAYTA bajarilmaydi, faqat video yuklab olish + ffmpeg merge
takrorlanadi).
"""
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.config import get_settings
from backend.services import downloader, merger
from backend.services.storage import (
    upload_file_to_s3,
    download_file_from_s3,
    generate_presigned_download_url,
    s3_object_exists,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _local_master_path(job) -> Path | None:
    """Возвращает локальный master, если S3-копия недоступна."""
    path = Path(job.output_video_path) if job.output_video_path else None
    if path is not None and not path.is_absolute():
        path = Path.cwd() / path
    if path is not None and path.is_file() and os.access(path, os.R_OK):
        return path
    return None


def _local_audio_path(job) -> Path | None:
    """Возвращает локальный файл дублированного аудио (dubbed_audio.wav).

    При не настроенном S3 tasks.py НЕ удаляет локальную копию после
    неудачного upload_file_to_s3() — поэтому файл остаётся на диске и
    является источником истины для 1080p-генерации. Путь в PostgreSQL
    может быть относительным (outputs/<job>/dubbed_audio.wav), поэтому
    разрешаем его относительно cwd, как в _local_master_path."""
    path = Path(job.dubbed_audio_path) if job.dubbed_audio_path else None
    if path is not None and not path.is_absolute():
        path = Path.cwd() / path
    if path is not None and path.is_file() and os.access(path, os.R_OK):
        return path
    return None


def _local_variant_path(job, resolution: str) -> Path | None:
    """Локальный файл готового варианта качества (360p/1080p).
    Локальная копия — источник истины: отдаётся same-origin URL'ом
    /api/outputs/{id}/video/{resolution}, S3 — только опциональная
    копия (2026-08-27: S3-ключи не настроены, варианты не должны падать)."""
    path = Path(settings.OUTPUT_DIR) / str(job.storage_id) / f"dubbed_{resolution}.mp4"
    if path.is_file() and os.access(path, os.R_OK):
        return path
    return None


def _upload_best_effort(local_path: str, s3_key: str) -> bool:
    """S3-загрузка без фатальных ошибок: локальный файл остаётся
    источником истины, S3 — только если настроен и доступен."""
    try:
        ok = upload_file_to_s3(local_path, s3_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"S3 yuklashda xatolik ({s3_key}): {exc}")
        return False
    if not ok:
        logger.warning(f"S3 yuklash imkonsiz ({s3_key}) — lokal fayl ishlatiladi.")
    return ok


def generate_360p(job) -> str:
    job_id = job.storage_id
    master_key = f"dubber/{job_id}/dubbed_final.mp4"
    master_url = None
    if s3_object_exists(master_key):
        master_url = generate_presigned_download_url(master_key)
    if not master_url:
        local_master = _local_master_path(job)
        if local_master is None:
            raise RuntimeError("Master video S3 yoki lokal diskda topilmadi.")
        master_url = str(local_master)

    out_dir = Path(settings.OUTPUT_DIR) / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    local_out = str(out_dir / "dubbed_360p.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", master_url,
        "-vf", "scale=-2:360",
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-c:a", "copy",
        "-movflags", "+faststart",
        local_out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"360p kichraytirishda ffmpeg xatoligi:\n{result.stderr[-1500:]}")

    s3_key = f"dubber/{job_id}/dubbed_360p.mp4"
    _upload_best_effort(local_out, s3_key)
    return s3_key


def generate_1080p(job) -> str:
    job_id = job.storage_id
    tmp_job_id = f"{job_id}_1080p"
    tmp_dir = Path(settings.UPLOAD_DIR) / tmp_job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Локальный dubbed_audio.wav — приоритет (S3-ключи могут быть не
        # настроены; в этом случае tasks.py оставляет локальную копию).
        # S3 — только fallback. 2026-08-27: без этого 1080p падал с
        # "Dublyaj audiosi S3'da topilmadi" при выключенном S3.
        local_audio = _local_audio_path(job)
        if local_audio is not None:
            local_audio_path = str(local_audio)
        else:
            audio_s3_key = f"dubber/{job_id}/dubbed_audio.wav"
            local_audio_path = str(tmp_dir / "dubbed_audio.wav")
            if not download_file_from_s3(audio_s3_key, local_audio_path):
                raise RuntimeError("Dublyaj audiosi lokal diskda ham, S3'da ham topilmadi.")

        download_result = downloader.download_video(job.youtube_url, tmp_job_id, max_height=1080)
        video_path = download_result["video_path"]

        out_dir = Path(settings.OUTPUT_DIR) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        local_out = str(out_dir / "dubbed_1080p.mp4")

        merger.merge_video_audio(
            video_path=video_path,
            dubbed_audio_path=local_audio_path,
            output_path=local_out,
            audio_mix_mode=getattr(job, "audio_mix_mode", None),
        )

        s3_key = f"dubber/{job_id}/dubbed_1080p.mp4"
        _upload_best_effort(local_out, s3_key)
        return s3_key
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def generate_variant(job, resolution: str) -> str:
    if resolution == "360p":
        return generate_360p(job)
    if resolution == "1080p":
        return generate_1080p(job)
    raise ValueError(f"Qo'llab-quvvatlanmaydigan rezolyutsiya: {resolution}")


@dataclass
class ResolutionRequestResult:
    outcome: str  # "ready" | "processing" | "forbidden" | "invalid" | "expired"
    download_url: str | None = None


def request_resolution(
    db,
    job,
    resolution: str,
    max_resolution_override: str | None = None,
    download: bool = True,
) -> ResolutionRequestResult:
    """Web (routes.py) va Telegram bot (telegram_bot.py) ikkalasi ham
    chaqiradigan yagona kirish nuqtasi -- tarif tekshiruvi, 720p uchun
    darhol javob, 360p/1080p uchun keshdan yoki Celery task orqali
    generatsiya faqat BITTA joyda yozilgan (job_creation.py bilan bir xil
    naqsh).

    max_resolution_override -- Ommaviy videolar kutubxonasida tomosha
    qilayotgan odam job egasi bo'lmasligi mumkin (2026-08-19); shu holatda
    routes.py TOMOSHABIN tarifini shu orqali uzatadi, aks holda odatdagidek
    job egasining tarifi tekshiriladi (get_max_resolution_for_job)."""
    from backend.models.database import ResolutionVariant
    from backend.services.plans import get_max_resolution_for_job, RESOLUTION_ORDER

    if resolution not in RESOLUTION_ORDER:
        return ResolutionRequestResult(outcome="invalid")

    max_res = max_resolution_override or get_max_resolution_for_job(db, job)
    if RESOLUTION_ORDER.index(resolution) > RESOLUTION_ORDER.index(max_res):
        return ResolutionRequestResult(outcome="forbidden")

    job_id = job.storage_id
    master_key = f"dubber/{job_id}/dubbed_final.mp4"

    # Barcha rezolyutsiyalar (720p ham, kesh'dagi tayyor variant ham) shu bitta
    # master fayl ustida qurilgan -- agar u S3 lifecycle (3 kun) bo'yicha
    # o'chirilgan bo'lsa, boshqa hech narsa ham ishlamaydi (2026-08-21: avval
    # bu tekshirilmasdan "ready" qaytarilardi, keyin yuklab olishda jim 404
    # bo'lardi yoki 360p generatsiyasi tushunarsiz ffmpeg xatosi bilan
    # yiqilardi).
    local_master = _local_master_path(job)
    if settings.AWS_BUCKET_NAME and not s3_object_exists(master_key) and local_master is None:
        return ResolutionRequestResult(outcome="expired")

    if resolution == "720p":
        if settings.AWS_BUCKET_NAME:
            presigned_url = generate_presigned_download_url(master_key, download=download)
            if presigned_url:
                return ResolutionRequestResult(outcome="ready", download_url=presigned_url)
        suffix = "?download=1" if download else ""
        return ResolutionRequestResult(outcome="ready", download_url=f"/api/outputs/{job_id}/video{suffix}")

    variant = (
        db.query(ResolutionVariant)
        .filter(ResolutionVariant.job_id == job.storage_id, ResolutionVariant.resolution == resolution)
        .first()
    )
    if variant is None:
        variant = ResolutionVariant(job_id=job.storage_id, resolution=resolution, status="pending")
        db.add(variant)
        db.commit()
        db.refresh(variant)

    if variant.status == "ready" and variant.s3_key:
        # Локальный файл — приоритет (same-origin, без CORS): вариант
        # генерируется локально и локальная копия остаётся даже после
        # S3-загрузки. S3-presigned — только если локального файла нет.
        local_variant = _local_variant_path(job, resolution)
        if local_variant is not None:
            suffix = "?download=1" if download else ""
            return ResolutionRequestResult(
                outcome="ready",
                download_url=f"/api/outputs/{job_id}/video/{resolution}{suffix}",
            )
        if s3_object_exists(variant.s3_key):
            presigned_url = generate_presigned_download_url(variant.s3_key, download=download)
            if presigned_url:
                return ResolutionRequestResult(outcome="ready", download_url=presigned_url)
        variant.status = "pending"  # lokal ham, S3 ham yo'q -- qayta yaratamiz

    if variant.status != "processing":
        variant.status = "processing"
        variant.error_message = None
        db.commit()
        from backend.workers.resolution_tasks import generate_resolution_variant_task
        generate_resolution_variant_task.apply_async(args=[job_id, resolution])

    return ResolutionRequestResult(outcome="processing")
