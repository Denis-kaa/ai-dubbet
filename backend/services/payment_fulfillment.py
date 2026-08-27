"""To'lov muvaffaqiyatli tasdiqlangandan keyin bajariladigan yagona mantiq --
Click (click_routes.py) va Payme (payme_routes.py) ikkalasi ham shu yerdan
foydalanadi, ikki joyda saqlanmaydi (2026-08-19, Payme integratsiyasi
qo'shilganda click_routes.py'dan ajratib olindi)."""
from datetime import datetime

from backend.models.database import DubbingJob, JobStatus, User
from backend.workers.tasks import process_video


def apply_successful_payment(db, payment) -> None:
    """payment.status allaqachon APPROVED qilib qo'yilgan bo'lishi kerak --
    bu funksiya faqat SHU to'lov nimaga tegishli ekaniga qarab (kutubxona
    kirish huquqi / obuna / job) tegishli holatni faollashtiradi."""
    if payment.is_library_access:
        user = db.query(User).filter(User.id == payment.user_id).first()
        if user and user.library_access_purchased_at is None:
            user.library_access_purchased_at = datetime.utcnow()
    elif payment.plan:
        from backend.services.plans import activate_subscription
        activate_subscription(db, payment.user_id, payment.plan)
    else:
        job = db.query(DubbingJob).filter(DubbingJob.id == payment.job_id).first()
        if job:
            if job.source_job_id:
                # Kesh-hit job -- qayta ishlov shart emas, natija allaqachon
                # asl job'da tayyor (backend/services/job_creation.py).
                job.status = JobStatus.COMPLETED
                job.status_message = "Dublyaj tayyor!"
                job.completed_at = datetime.utcnow()
            else:
                job.status = JobStatus.PENDING
                job.status_message = "To'lov tasdiqlandi. Dublyaj navbatga qo'shildi."
                from backend.services.plans import get_job_queue
                process_video.apply_async(args=[str(job.id)], task_id=str(job.id), queue=get_job_queue(db, payment.user_id))
