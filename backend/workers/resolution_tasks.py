from datetime import datetime
from celery import Task
from celery.utils.log import get_task_logger

from backend.workers.celery_app import celery_app
from backend.models.database import SessionLocal, DubbingJob, ResolutionVariant
from backend.services import resolution_variants
from backend.services.storage import generate_presigned_download_url
from backend.services.telegram_notify import send_telegram_message

logger = get_task_logger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30, time_limit=3600, soft_time_limit=3300)
def generate_resolution_variant_task(self: Task, job_id: str, resolution: str):
    db = SessionLocal()
    try:
        variant = (
            db.query(ResolutionVariant)
            .filter(ResolutionVariant.job_id == job_id, ResolutionVariant.resolution == resolution)
            .first()
        )
        if variant is None:
            logger.warning(f"ResolutionVariant topilmadi (job={job_id}, resolution={resolution}) -- bekor qilinadi.")
            return

        variant.status = "processing"
        variant.updated_at = datetime.utcnow()
        db.commit()

        job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
        if job is None:
            variant.status = "failed"
            variant.error_message = "Job topilmadi."
            db.commit()
            return

        try:
            s3_key = resolution_variants.generate_variant(job, resolution)
            variant.status = "ready"
            variant.s3_key = s3_key
            variant.error_message = None
            variant.updated_at = datetime.utcnow()
            db.commit()

            # Telegram orqali so'ralgan bo'lishi mumkin -- tugagach xabar
            # beramiz (tugma bosilganda darhol javob bo'lmagani uchun,
            # xuddi asosiy job tugagandagi bildirishnoma kabi).
            if job.user_id and job.user and job.user.telegram_chat_id:
                url = generate_presigned_download_url(s3_key)
                if url:
                    send_telegram_message(
                        job.user.telegram_chat_id,
                        f"\u2705 {resolution} versiyasi tayyor!\n\n\U0001F3AC {job.video_title or 'Video'}\n\n{url}",
                    )
        except Exception as exc:
            logger.error(f"Rezolyutsiya generatsiyasida xatolik (job={job_id}, resolution={resolution}): {exc}")
            variant.status = "failed"
            variant.error_message = str(exc)[:2000]
            variant.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
