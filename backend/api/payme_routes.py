"""Payme (Paycom) to'lov integratsiyasi -- ikki xil yo'nalish:

1. Bizning backend Payme'ga so'rov yuboradi (/initiate*): foydalanuvchi
   to'lovni boshlaydi, biz Payment(provider=PAYME, status=PENDING) yozib,
   checkout.paycom.uz havolasini qaytaramiz (Click'dagi /initiate bilan
   bir xil naqsh).

2. Payme bizning backendga so'rov yuboradi (/): foydalanuvchi to'lovni
   checkout sahifasida yakunlagach, Payme serveri Merchant API orqali
   (JSON-RPC 2.0, Basic Auth) CheckPerformTransaction -> CreateTransaction
   -> PerformTransaction ketma-ketligini chaqiradi. Bu yo'nalish Click'ning
   prepare/complete webhooklaridan farqli -- bitta endpoint, method maydoni
   orqali tarmoqlanadi. To'liq spetsifikatsiya (2026-08-19 o'qildi):
   https://developer.help.paycom.uz/protokol-merchant-api
"""
import time
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db, DubbingJob, JobStatus, User
from backend.models.payment import Payment, PaymentStatus, PaymentProvider
from backend.services.auth import get_current_user
from backend.services.payme_service import (
    PaymeErrors,
    payme_error,
    payme_result,
    verify_payme_auth,
    generate_payme_checkout_url,
    now_ms,
)
from backend.config import get_settings

router = APIRouter(prefix="/api/payments/payme", tags=["payme"])

ACCOUNT_FIELD = "payment_id"  # Click'dagi transaction_param bilan bir xil naqsh -- Payment.id


def _amount_tiyin(so_um_amount: float) -> int:
    return int(round(so_um_amount * 100))


def _build_checkout_url(request: Request, payment: Payment, return_path: str) -> str:
    settings = get_settings()
    origin_header = request.headers.get("origin") or request.headers.get("referer")
    if origin_header:
        from urllib.parse import urlparse
        parsed = urlparse(origin_header)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
    else:
        base_origin = (settings.FRONTEND_URL or "https://gapirai.uz").rstrip("/")
    return_url = f"{base_origin}{return_path}"
    return generate_payme_checkout_url(
        merchant_id=settings.PAYME_MERCHANT_ID,
        account_field=ACCOUNT_FIELD,
        account_value=str(payment.id),
        amount_tiyin=_amount_tiyin(payment.amount),
        return_url=return_url,
        # Kassa Payme kabinetida production uchun hali faollashtirilmagan
        # bo'lsa (PAYME_SANDBOX_MODE=True), checkout sandbox (test.paycom.uz)
        # domeniga yo'naltiriladi -- aks holda Payme "Поставщик не найден"
        # deb rad etadi (2026-08-19, haqiqiy checkoutda tasdiqlangan). Bu
        # PAYME_KEY to'ldirilgan-to'ldirilmaganidan MUSTAQIL -- key mavjud
        # bo'lishi kassa faollashganini anglatmaydi.
        sandbox=settings.PAYME_SANDBOX_MODE,
    )


# ─────────────────────────────────────────────────────────────────────────
# 1. Initiatsiya (bizning backend -> Payme checkout havolasi)
# ─────────────────────────────────────────────────────────────────────────

class InitiateJobPaymentRequest(BaseModel):
    job_id: str


@router.post("/initiate")
def initiate_job_payment(
    req: InitiateJobPaymentRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """click_routes.py:initiate_payment bilan bir xil narxlash mantig'i --
    faqat Payme checkout havolasi qaytariladi."""
    job = db.query(DubbingJob).filter(DubbingJob.id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job topilmadi.")
    if not job.user_id:
        job.user_id = current_user.id
        db.commit()
    elif job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sizda bu videoga ruxsat yo'q.")
    if not job.video_duration:
        raise HTTPException(status_code=400, detail="Video davomiyligi aniqlanmadi.")

    duration_minutes = job.video_duration / 60.0
    from backend.services.plans import check_quota, consume_quota, get_job_queue
    covered_by_quota, amount = check_quota(db, current_user.id, duration_minutes)
    if job.source_job_id and not covered_by_quota:
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
                from backend.workers.tasks import process_video
                process_video.apply_async(args=[str(job.id)], task_id=str(job.id), queue=get_job_queue(db, current_user.id))
        return {"success": True, "message": "Bepul video. Ishlov berish boshlandi.", "amount": 0}

    existing_approved = db.query(Payment).filter(
        Payment.job_id == job.id, Payment.status == PaymentStatus.APPROVED
    ).first()
    if existing_approved:
        return {"success": True, "message": "To'lov allaqachon amalga oshirilgan.", "amount": 0}

    payment = db.query(Payment).filter(
        Payment.job_id == job.id, Payment.status == PaymentStatus.PENDING, Payment.provider == PaymentProvider.PAYME
    ).first()
    if not payment:
        payment = Payment(
            user_id=current_user.id, job_id=job.id, amount=amount,
            provider=PaymentProvider.PAYME, status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
    elif payment.amount != amount:
        payment.amount = amount
        db.commit()

    payment_url = _build_checkout_url(request, payment, f"/video/{job.id}")
    return {"success": True, "payment_url": payment_url, "payment_id": str(payment.id), "amount": amount}


class InitiateSubscriptionRequest(BaseModel):
    plan: str


@router.post("/initiate-subscription")
def initiate_subscription_payment(
    req: InitiateSubscriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.plans import PLANS
    if req.plan not in PLANS or req.plan == "free":
        raise HTTPException(status_code=400, detail="Noto'g'ri tarif tanlandi.")
    plan = PLANS[req.plan]

    payment = Payment(
        user_id=current_user.id, plan=req.plan, amount=plan.price,
        provider=PaymentProvider.PAYME, status=PaymentStatus.PENDING,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    payment_url = _build_checkout_url(request, payment, "/dashboard")
    return {"success": True, "payment_url": payment_url, "payment_id": str(payment.id), "amount": plan.price}


@router.post("/initiate-library")
def initiate_library_payment(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.api.routes import LIBRARY_ACCESS_PRICE
    if current_user.library_access_purchased_at is not None:
        return {"success": True, "message": "Kirish huquqi allaqachon mavjud.", "amount": 0}

    payment = db.query(Payment).filter(
        Payment.user_id == current_user.id,
        Payment.is_library_access.is_(True),
        Payment.status == PaymentStatus.PENDING,
        Payment.provider == PaymentProvider.PAYME,
    ).first()
    if not payment:
        payment = Payment(
            user_id=current_user.id, is_library_access=True, amount=LIBRARY_ACCESS_PRICE,
            provider=PaymentProvider.PAYME, status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

    payment_url = _build_checkout_url(request, payment, "/library")
    return {"success": True, "payment_url": payment_url, "payment_id": str(payment.id), "amount": LIBRARY_ACCESS_PRICE}


# ─────────────────────────────────────────────────────────────────────────
# 2. Merchant API (Payme -> bizning backend, JSON-RPC 2.0)
# ─────────────────────────────────────────────────────────────────────────

def _find_by_account(db: Session, params: dict):
    account = params.get("account")
    if not isinstance(account, dict):
        return None
    payment_id = account.get(ACCOUNT_FIELD)
    if not payment_id or not isinstance(payment_id, str):
        return None
    try:
        return db.query(Payment).filter(Payment.id == payment_id).first()
    except Exception:
        return None


def _find_by_payme_id(db: Session, params: dict):
    txn_id = params.get("id")
    if not txn_id:
        return None
    return db.query(Payment).filter(Payment.payme_transaction_id == txn_id).first()


def _account_error(req_id):
    return payme_error(
        PaymeErrors.INVALID_ACCOUNT,
        "To'lov topilmadi yoki muddati o'tgan.", "Платёж не найден или устарел.", "Payment not found or expired.",
        data=ACCOUNT_FIELD, request_id=req_id,
    )


def _account_busy_error(req_id):
    """CreateTransaction hujjati: "Следует бронировать заказ покупателя...
    до оплаты или отмены по таймауту" -- hisob allaqachon BOSHQA (hali
    yakunlanmagan) tranzaksiya bilan band bo'lsa, bu ham "account" xatosi
    hisoblanadi (-31050 -- -31099), umumiy -31008 emas (rasmiy sandbox
    sertifikatsiya testi shuni talab qiladi, 2026-08-19 tasdiqlangan)."""
    return payme_error(
        PaymeErrors.INVALID_ACCOUNT,
        "Bu hisob band -- boshqa tranzaksiya bilan qulflangan.", "Счёт занят другой транзакцией.", "Account is busy with another transaction.",
        data=ACCOUNT_FIELD, request_id=req_id,
    )


def _handle_check_perform_transaction(db: Session, params: dict, req_id):
    payment = _find_by_account(db, params)
    if not payment or payment.status not in (PaymentStatus.PENDING,):
        return _account_error(req_id)

    amount_tiyin = params.get("amount")
    if amount_tiyin != _amount_tiyin(payment.amount):
        return payme_error(PaymeErrors.INVALID_AMOUNT, "Noto'g'ri summa.", "Неверная сумма.", "Invalid amount.", request_id=req_id)

    return payme_result({"allow": True}, req_id)


def _handle_create_transaction(db: Session, params: dict, req_id):
    txn_id = params.get("id")
    txn_time = params.get("time")
    amount_tiyin = params.get("amount")

    # Idempotentlik: shu Payme id bilan tranzaksiya allaqachon yaratilgan bo'lsa,
    # qayta bir xil natijani qaytaramiz (Payme spetsifikatsiyasi shuni talab qiladi).
    existing = _find_by_payme_id(db, params)
    if existing:
        if existing.payme_state == 1:
            return payme_result({
                "create_time": existing.payme_create_time,
                "transaction": str(existing.id),
                "state": 1,
            }, req_id)
        if existing.payme_state == 2:
            return payme_result({
                "create_time": existing.payme_create_time,
                "transaction": str(existing.id),
                "state": 2,
            }, req_id)
        return payme_error(PaymeErrors.CANNOT_PERFORM_OPERATION, "Amalni bajarib bo'lmadi.", "Невозможно выполнить операцию.", "Cannot perform operation.", request_id=req_id)

    payment = _find_by_account(db, params)
    if not payment or payment.status != PaymentStatus.PENDING:
        return _account_error(req_id)

    if amount_tiyin != _amount_tiyin(payment.amount):
        return payme_error(PaymeErrors.INVALID_AMOUNT, "Noto'g'ri summa.", "Неверная сумма.", "Invalid amount.", request_id=req_id)

    # Shu Payment allaqachon boshqa Payme tranzaksiyasi bilan band bo'lsa (masalan
    # avvalgi urinish hali muddati o'tmagan) -- yangisini rad etamiz.
    if payment.payme_transaction_id and payment.payme_transaction_id != txn_id:
        return _account_busy_error(req_id)

    payment.payme_transaction_id = txn_id
    payment.payme_state = 1
    payment.payme_create_time = txn_time or now_ms()
    db.commit()

    return payme_result({
        "create_time": payment.payme_create_time,
        "transaction": str(payment.id),
        "state": 1,
    }, req_id)


def _handle_perform_transaction(db: Session, params: dict, req_id):
    payment = _find_by_payme_id(db, params)
    if not payment:
        return payme_error(PaymeErrors.TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi.", "Транзакция не найдена.", "Transaction not found.", request_id=req_id)

    if payment.payme_state == 2:
        # Idempotent -- allaqachon tasdiqlangan, xuddi shu natijani qaytaramiz.
        return payme_result({
            "transaction": str(payment.id),
            "perform_time": payment.payme_perform_time,
            "state": 2,
        }, req_id)

    if payment.payme_state != 1:
        return payme_error(PaymeErrors.CANNOT_PERFORM_OPERATION, "Amalni bajarib bo'lmadi.", "Невозможно выполнить операцию.", "Cannot perform operation.", request_id=req_id)

    # 12 soatlik taymout (CreateTransaction sahifasi: 43 200 000 ms).
    if payment.payme_create_time and (now_ms() - payment.payme_create_time) > 43_200_000:
        payment.payme_state = -1
        payment.payme_cancel_time = now_ms()
        payment.payme_cancel_reason = 4
        payment.status = PaymentStatus.CANCELLED
        db.commit()
        return payme_error(PaymeErrors.CANNOT_PERFORM_OPERATION, "Vaqt tugadi.", "Истекло время ожидания.", "Timed out.", request_id=req_id)

    payment.status = PaymentStatus.APPROVED
    payment.payme_state = 2
    payment.payme_perform_time = now_ms()

    from backend.services.payment_fulfillment import apply_successful_payment
    apply_successful_payment(db, payment)

    db.commit()

    return payme_result({
        "transaction": str(payment.id),
        "perform_time": payment.payme_perform_time,
        "state": 2,
    }, req_id)


def _handle_cancel_transaction(db: Session, params: dict, req_id):
    payment = _find_by_payme_id(db, params)
    if not payment:
        return payme_error(PaymeErrors.TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi.", "Транзакция не найдена.", "Transaction not found.", request_id=req_id)

    if payment.payme_state in (-1, -2):
        # Idempotent -- allaqachon bekor qilingan.
        return payme_result({
            "transaction": str(payment.id),
            "cancel_time": payment.payme_cancel_time,
            "state": payment.payme_state,
        }, req_id)

    reason = params.get("reason")
    was_performed = payment.payme_state == 2

    # Payme spetsifikatsiyasi (CancelTransaction sahifasi): agar buyurtma
    # to'liq bajarilgan bo'lsa ("Товар или услуга предоставлена покупателю
    # в полном объеме"), bekor qilish RAD ETILISHI kerak (-31007) --
    # avvalgi kod buni tekshirmasdan har doim bekor qilishga ruxsat berardi.
    if was_performed and payment.job_id:
        job = db.query(DubbingJob).filter(DubbingJob.id == payment.job_id).first()
        if job and job.status == JobStatus.COMPLETED:
            return payme_error(
                PaymeErrors.ORDER_ALREADY_FULFILLED,
                "Buyurtma bajarilgan, bekor qilib bo'lmaydi.", "Заказ выполнен. Невозможно отменить транзакцию.", "Order already fulfilled.",
                request_id=req_id,
            )

    payment.payme_state = -2 if was_performed else -1
    payment.payme_cancel_time = now_ms()
    payment.payme_cancel_reason = reason
    payment.status = PaymentStatus.CANCELLED

    if not was_performed:
        # Faqat hali tasdiqlanmagan (pending) job/obuna/kutubxona to'lovi
        # bekor qilinsa, tegishli job'ni FAILED qilamiz -- Click'dagi
        # click_complete()ning manfiy-xato bo'limi bilan bir xil.
        if payment.job_id:
            job = db.query(DubbingJob).filter(DubbingJob.id == payment.job_id).first()
            if job and job.status == JobStatus.AWAITING_PAYMENT:
                job.status = JobStatus.FAILED
                job.error_message = "To'lov bekor qilindi."

    db.commit()

    return payme_result({
        "transaction": str(payment.id),
        "cancel_time": payment.payme_cancel_time,
        "state": payment.payme_state,
    }, req_id)


def _handle_check_transaction(db: Session, params: dict, req_id):
    payment = _find_by_payme_id(db, params)
    if not payment:
        return payme_error(PaymeErrors.TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi.", "Транзакция не найдена.", "Transaction not found.", request_id=req_id)

    return payme_result({
        "create_time": payment.payme_create_time or 0,
        "perform_time": payment.payme_perform_time or 0,
        "cancel_time": payment.payme_cancel_time or 0,
        "transaction": str(payment.id),
        "state": payment.payme_state,
        "reason": payment.payme_cancel_reason,
    }, req_id)


def _handle_get_statement(db: Session, params: dict, req_id):
    from_ms = params.get("from")
    to_ms = params.get("to")
    q = db.query(Payment).filter(
        Payment.provider == PaymentProvider.PAYME,
        Payment.payme_create_time.isnot(None),
    )
    if from_ms is not None:
        q = q.filter(Payment.payme_create_time >= from_ms)
    if to_ms is not None:
        q = q.filter(Payment.payme_create_time <= to_ms)
    payments = q.order_by(Payment.payme_create_time.asc()).all()

    transactions = []
    for p in payments:
        transactions.append({
            "id": p.payme_transaction_id,
            "time": p.payme_create_time,
            "amount": _amount_tiyin(p.amount),
            "account": {ACCOUNT_FIELD: str(p.id)},
            "create_time": p.payme_create_time or 0,
            "perform_time": p.payme_perform_time or 0,
            "cancel_time": p.payme_cancel_time or 0,
            "transaction": str(p.id),
            "state": p.payme_state,
            "reason": p.payme_cancel_reason,
        })

    return payme_result({"transactions": transactions}, req_id)


_METHOD_HANDLERS = {
    "CheckPerformTransaction": _handle_check_perform_transaction,
    "CreateTransaction": _handle_create_transaction,
    "PerformTransaction": _handle_perform_transaction,
    "CancelTransaction": _handle_cancel_transaction,
    "CheckTransaction": _handle_check_transaction,
    "GetStatement": _handle_get_statement,
}


@router.post("")
async def payme_merchant_api(request: Request, db: Session = Depends(get_db)):
    """Payme Merchant API'ning yagona kirish nuqtasi -- barcha holatlarda
    HTTP 200 va JSON-RPC formatidagi {result} yoki {error} qaytaradi (Payme
    HTTP xato kodlarini emas, javob tanasidagi "error" maydonini kutadi)."""
    settings = get_settings()

    try:
        body = await request.json()
    except Exception:
        return payme_error(PaymeErrors.INVALID_JSON_RPC, "JSON xato.", "Ошибка парсинга JSON.", "JSON parse error.")

    req_id = body.get("id") if isinstance(body, dict) else None
    method = body.get("method") if isinstance(body, dict) else None
    params = body.get("params") if isinstance(body, dict) else None

    if not method or not isinstance(params, dict):
        return payme_error(PaymeErrors.INVALID_REQUEST, "So'rov formati noto'g'ri.", "Неверный формат запроса.", "Invalid request format.", request_id=req_id)

    if not verify_payme_auth(request.headers.get("authorization"), settings.PAYME_KEY, settings.PAYME_TEST_KEY):
        return payme_error(PaymeErrors.INSUFFICIENT_PRIVILEGE, "Ruxsat yo'q.", "Недостаточно привилегий для выполнения метода.", "Insufficient privilege.", request_id=req_id)

    handler = _METHOD_HANDLERS.get(method)
    if not handler:
        return payme_error(PaymeErrors.METHOD_NOT_FOUND, "Metod topilmadi.", "Метод не найден.", "Method not found.", data=method, request_id=req_id)

    try:
        return handler(db, params, req_id)
    except Exception as exc:
        db.rollback()
        return payme_error(PaymeErrors.SYSTEM_ERROR, "Tizim xatosi.", "Системная ошибка.", "System error.", data=str(exc), request_id=req_id)
