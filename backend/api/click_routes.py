from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import time
from backend.models.database import get_db, DubbingJob, JobStatus, User
from backend.models.payment import Payment, PaymentStatus, PaymentProvider
from backend.services.click_service import (
    generate_payment_url,
    validate_signature,
    ClickErrors,
    normalize_uzs_amount,
)
from backend.services.auth import get_current_user
from backend.config import get_settings
from backend.workers.tasks import process_video

router = APIRouter(prefix="/api/payments/click", tags=["click"])

class InitiatePaymentRequest(BaseModel):
    job_id: str

@router.post("/initiate")
def initiate_payment(
    req: InitiatePaymentRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    settings = get_settings()
    job = db.query(DubbingJob).filter(DubbingJob.id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job topilmadi.")

    # Eski (login majburiy bo'lishidan oldingi) anonim job'larni da'vo qilish —
    # yangi job'larda user_id doim create_job orqali o'rnatiladi.
    if not job.user_id:
        job.user_id = current_user.id
        db.commit()
    elif job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sizda bu videoga ruxsat yo'q.")

    # duration is required to calculate price
    if not job.video_duration:
        raise HTTPException(status_code=400, detail="Video davomiyligi aniqlanmadi.")

    duration_minutes = job.video_duration / 60.0
    # Tarif kvotasi bilan bir xil mantiq — create_job (routes.py) bilan mos
    # kelishi kerak, aks holda AWAITING_PAYMENT job noto'g'ri qayta narxlanishi mumkin.
    from backend.services.plans import check_quota, consume_quota, get_job_queue
    covered_by_quota, amount = check_quota(db, current_user.id, duration_minutes)
    if job.source_job_id and not covered_by_quota:
        # Kesh-hit job -- davomiylikka bog'liq narx emas, qat'iy arzon narx
        # (backend/services/job_creation.py: CACHE_HIT_PRICE bilan bir xil).
        from backend.services.job_creation import CACHE_HIT_PRICE
        amount = CACHE_HIT_PRICE

    if amount == 0:
        if covered_by_quota:
            consume_quota(db, current_user.id, duration_minutes)
            job.quota_consumed = True
        if job.status == JobStatus.AWAITING_PAYMENT:
            if job.source_job_id:
                from datetime import datetime
                job.status = JobStatus.COMPLETED
                job.status_message = "Dublyaj tayyor!"
                job.completed_at = datetime.utcnow()
                db.commit()
            else:
                job.status = JobStatus.PENDING
                job.status_message = "Navbatga qo'shildi"
                db.commit()
                process_video.apply_async(args=[str(job.id)], task_id=str(job.id), queue=get_job_queue(db, current_user.id))
        return {"success": True, "message": "Bepul video. Ishlov berish boshlandi.", "amount": 0}

    # Check if already paid
    existing_approved = db.query(Payment).filter(
        Payment.job_id == job.id,
        Payment.status == PaymentStatus.APPROVED
    ).first()
    if existing_approved:
        return {"success": True, "message": "To'lov allaqachon amalga oshirilgan.", "amount": 0}

    # Find or create pending payment
    payment = db.query(Payment).filter(
        Payment.job_id == job.id,
        Payment.status == PaymentStatus.PENDING
    ).first()

    if not payment:
        payment = Payment(
            user_id=current_user.id,
            job_id=job.id,
            amount=amount,
            provider=PaymentProvider.CLICK,
            status=PaymentStatus.PENDING,
            click_create_time=int(time.time())
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
    elif normalize_uzs_amount(payment.amount) != amount:
        payment.amount = amount
        payment.click_create_time = int(time.time())
        db.commit()
        db.refresh(payment)

    merchant_id = settings.CLICK_MERCHANT_ID or "56653"
    service_id = settings.CLICK_SERVICE_ID or "108780"
    merchant_user_id = getattr(settings, "CLICK_MERCHANT_USER_ID", "") or "89102"
    
    origin_header = request.headers.get("origin") or request.headers.get("referer")
    if origin_header:
        from urllib.parse import urlparse
        parsed = urlparse(origin_header)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        return_url = f"{base_origin}/video/{job.id}"
    else:
        frontend_url = settings.FRONTEND_URL or "https://gapirai.uz"
        return_url = f"{frontend_url.rstrip('/')}/video/{job.id}"

    payment_url = generate_payment_url(
        merchant_id=merchant_id,
        service_id=service_id,
        transaction_param=str(payment.id),
        amount=amount,
        return_url=return_url,
        merchant_user_id=merchant_user_id,
    )

    return {
        "success": True,
        "payment_url": payment_url,
        "payment_id": str(payment.id),
        "amount": amount
    }

@router.post("/prepare")
async def click_prepare(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    data = dict(form_data)
    print(f">>> [CLICK PREPARE WEBHOOK RECEIVED]: {data}", flush=True)
    
    settings = get_settings()
    secret_key = settings.CLICK_SECRET_KEY
    
    if not validate_signature(data, secret_key):
        return {"error": ClickErrors.SIGN_CHECK_FAILED, "error_note": "Invalid signature"}

    action = int(data.get("action", -1))
    if action != 0:
        return {"error": ClickErrors.ACTION_NOT_FOUND, "error_note": "Invalid action"}

    merchant_trans_id = data.get("merchant_trans_id")
    amount = normalize_uzs_amount(data.get("amount", 0))
    click_trans_id = data.get("click_trans_id")

    payment = db.query(Payment).filter(Payment.id == merchant_trans_id).first()
    if not payment:
        return {"error": ClickErrors.TRANSACTION_NOT_FOUND, "error_note": "Payment not found"}

    if payment.status == PaymentStatus.APPROVED:
        return {"error": ClickErrors.ALREADY_PAID, "error_note": "Already paid"}

    if normalize_uzs_amount(payment.amount) != amount:
        return {"error": ClickErrors.INVALID_AMOUNT, "error_note": "Amount mismatch"}

    import zlib
    prep_id = zlib.crc32(payment.id.bytes)
    click_trans_val = int(click_trans_id) if str(click_trans_id).isdigit() else 0

    payment.click_transaction_id = str(click_trans_id)
    payment.click_prepare_id = prep_id
    payment.click_status = 0
    db.commit()

    return {
        "error": ClickErrors.SUCCESS,
        "error_note": "Success",
        "click_trans_id": click_trans_val,
        "merchant_trans_id": merchant_trans_id,
        "merchant_prepare_id": prep_id
    }


@router.post("/complete")
async def click_complete(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    data = dict(form_data)
    print(f">>> [CLICK COMPLETE WEBHOOK RECEIVED]: {data}", flush=True)
    
    settings = get_settings()
    secret_key = settings.CLICK_SECRET_KEY
    
    if not validate_signature(data, secret_key):
        return {"error": ClickErrors.SIGN_CHECK_FAILED, "error_note": "Invalid signature"}

    action = int(data.get("action", -1))
    if action != 1:
        return {"error": ClickErrors.ACTION_NOT_FOUND, "error_note": "Invalid action"}

    merchant_trans_id = data.get("merchant_trans_id")
    click_error = int(data.get("error", 0))
    error_note = data.get("error_note", "")
    click_trans_id = data.get("click_trans_id")

    payment = db.query(Payment).filter(Payment.id == merchant_trans_id).first()
    if not payment:
        return {"error": ClickErrors.TRANSACTION_NOT_FOUND, "error_note": "Payment not found"}

    if click_error < 0:
        payment.status = PaymentStatus.CANCELLED
        payment.click_status = click_error
        
        # update job status too
        job = db.query(DubbingJob).filter(DubbingJob.id == payment.job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.error_message = f"To'lov bekor qilindi: {error_note}"
            
        db.commit()
        return {
            "error": ClickErrors.TRANSACTION_CANCELLED,
            "error_note": "Payment cancelled by Click",
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id
        }

    import zlib
    confirm_id = zlib.crc32(payment.id.bytes)
    click_trans_val = int(click_trans_id) if str(click_trans_id).isdigit() else 0

    if payment.status == PaymentStatus.APPROVED:
        return {
            "error": ClickErrors.SUCCESS,
            "error_note": "Already completed",
            "click_trans_id": click_trans_val,
            "merchant_trans_id": merchant_trans_id,
            "merchant_confirm_id": confirm_id
        }

    payment.status = PaymentStatus.APPROVED
    payment.click_status = 1
    payment.click_complete_time = int(time.time())

    from backend.services.payment_fulfillment import apply_successful_payment
    apply_successful_payment(db, payment)

    db.commit()

    return {
        "error": ClickErrors.SUCCESS,
        "error_note": "Success",
        "click_trans_id": click_trans_val,
        "merchant_trans_id": merchant_trans_id,
        "merchant_confirm_id": confirm_id
    }

