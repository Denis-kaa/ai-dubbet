"""Uzum Bank Merchant webhook integratsiyasi.

RASMIY SPETSIFIKATSIYA (2026-08-20, https://developer.uzumbank.uz/merchant/)
asosida qurilgan -- to'liq so'rov/javob shakllari va xatolik kodlari
backend/services/uzum_service.py'dagi izohda. Ikki yo'nalish:

1. Bizning backend Uzum orqali to'lash uchun "account" raqamini beradi
   (/initiate): checkout havolasi emas -- Uzum'da bizga ma'lum checkout-URL
   mexanizmi yo'q, foydalanuvchi Uzum ilovasi orqali o'zi to'laydi.

2. Uzum bizning backendga 5 ta webhook yuboradi (/check, /create, /confirm,
   /reverse, /status). MUHIM: Uzum idempotent qayta chaqiruvni XATO deb
   hisoblaydi (Payme'dan farqli) -- xuddi shu transId bilan /create qayta
   chaqirilsa 10010, /confirm qayta chaqirilsa 10016, /reverse qayta
   chaqirilsa 10018 qaytariladi, muvaffaqiyat emas.

Har bir chaqiruv to'liq log qilinadi (`docker compose logs backend | grep
UZUM`) -- kelajakda spetsifikatsiya noaniq qolgan joylar (masalan aniq
qaysi holatda 10012 vs 10013) uchun foydali."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db, DubbingJob, JobStatus, User
from backend.models.payment import Payment, PaymentStatus, PaymentProvider
from backend.services.auth import get_current_user
from backend.services.uzum_service import (
    verify_basic_auth,
    account_id_from_payment_id,
    now_ms,
    error_envelope,
    check_success,
    create_success,
    confirm_success,
    reverse_success,
    status_success,
    UzumErrors,
)
from backend.config import get_settings

router = APIRouter(prefix="/api/payments/uzum", tags=["uzum"])


def _amount_tiyin(so_um_amount: float) -> int:
    return int(round(so_um_amount * 100))


def _err(error_code: str) -> JSONResponse:
    """Rasmiy hujjat: HTTP 400 + FAQAT "errorCode" shart."""
    return JSONResponse(status_code=400, content=error_envelope(error_code))


# ─────────────────────────────────────────────────────────────────────────
# 1. Initiatsiya (bizning backend -> Uzum orqali to'lash uchun account raqami)
# ─────────────────────────────────────────────────────────────────────────

class InitiateJobPaymentRequest(BaseModel):
    job_id: str


@router.post("/initiate")
def initiate_job_payment(
    req: InitiateJobPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """click_routes.py:initiate_payment bilan bir xil narxlash mantig'i --
    checkout havolasi o'rniga faqat Uzum "account" raqamini qaytaradi
    (hujjatda checkout-URL mexanizmi ko'rsatilmagan)."""
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
        Payment.job_id == job.id, Payment.status == PaymentStatus.PENDING, Payment.provider == PaymentProvider.UZUM
    ).first()
    if not payment:
        payment = Payment(
            user_id=current_user.id, job_id=job.id, amount=amount,
            provider=PaymentProvider.UZUM, status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
    elif payment.amount != amount:
        payment.amount = amount
        db.commit()

    if not payment.uzum_account_id:
        payment.uzum_account_id = account_id_from_payment_id(payment.id)
        db.commit()

    return {"success": True, "account": payment.uzum_account_id, "payment_id": str(payment.id), "amount": amount}


@router.post("/initiate-library")
def initiate_library_payment(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """payme_routes.py:initiate_library_payment bilan bir xil naqsh --
    checkout havolasi o'rniga faqat Uzum "account" raqamini qaytaradi
    (yuqoridagi initiate_job_payment bilan bir xil sabab). Bu metod ilgari
    umuman yo'q edi -- Uzum faqat video (job) to'lovlari uchun qurilgan,
    kutubxona kirish huquqi uchun na backend endpoint, na frontend tugma
    bor edi (2026-08-24, foydalanuvchi kutubxona sahifasida Uzum tugmasi
    ko'rinmayotganini payqadi)."""
    from backend.api.routes import LIBRARY_ACCESS_PRICE
    if current_user.library_access_purchased_at is not None:
        return {"success": True, "message": "Kirish huquqi allaqachon mavjud.", "amount": 0}

    payment = db.query(Payment).filter(
        Payment.user_id == current_user.id,
        Payment.is_library_access.is_(True),
        Payment.status == PaymentStatus.PENDING,
        Payment.provider == PaymentProvider.UZUM,
    ).first()
    if not payment:
        payment = Payment(
            user_id=current_user.id, is_library_access=True, amount=LIBRARY_ACCESS_PRICE,
            provider=PaymentProvider.UZUM, status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

    if not payment.uzum_account_id:
        payment.uzum_account_id = account_id_from_payment_id(payment.id)
        db.commit()

    return {"success": True, "account": payment.uzum_account_id, "payment_id": str(payment.id), "amount": LIBRARY_ACCESS_PRICE}


# ─────────────────────────────────────────────────────────────────────────
# 2. Webhook (Uzum -> bizning backend)
# ─────────────────────────────────────────────────────────────────────────

def _find_by_account(db: Session, params: dict) -> Payment | None:
    if not isinstance(params, dict):
        return None
    account = params.get("account")
    if account is None:
        return None
    try:
        account_int = int(account)
    except (TypeError, ValueError):
        return None
    return db.query(Payment).filter(Payment.uzum_account_id == account_int).first()


def _find_by_uzum_txn(db: Session, trans_id) -> Payment | None:
    if trans_id is None:
        return None
    return db.query(Payment).filter(Payment.uzum_transaction_id == str(trans_id)).first()


def _log(method: str, data) -> None:
    print(f">>> [UZUM {method} WEBHOOK RECEIVED]: {data}", flush=True)


def _check_auth_and_service(request: Request, body: dict, check_service: bool) -> str | None:
    """Auth va (kerak bo'lsa) serviceId'ni tekshiradi. Xato bo'lsa mos
    errorCode qaytaradi, hammasi joyida bo'lsa None."""
    settings = get_settings()
    if not verify_basic_auth(request.headers.get("authorization"), settings.UZUM_WEBHOOK_USERNAME, settings.UZUM_WEBHOOK_PASSWORD):
        return UzumErrors.ACCESS_DENIED
    if check_service:
        service_id = body.get("serviceId")
        if service_id is None or int(service_id) != int(settings.UZUM_SERVICE_ID):
            return UzumErrors.INVALID_SERVICE_ID
    return None


async def _parse_body(request: Request) -> dict | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _dt_to_ms(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return int(dt.replace(tzinfo=None).timestamp() * 1000) if dt.tzinfo else int(dt.timestamp() * 1000)


@router.post("/check")
async def uzum_check(request: Request, db: Session = Depends(get_db)):
    body = await _parse_body(request)
    if body is None:
        return _err(UzumErrors.JSON_PARSE_ERROR)
    _log("CHECK", body)

    err = _check_auth_and_service(request, body, check_service=True)
    if err:
        return _err(err)

    service_id = body.get("serviceId")
    params = body.get("params")
    if not isinstance(params, dict):
        return _err(UzumErrors.MISSING_REQUIRED_PARAMS)

    payment = _find_by_account(db, params)
    if not payment:
        return _err(UzumErrors.ATTRIBUTE_NOT_FOUND)
    if payment.status == PaymentStatus.APPROVED:
        return _err(UzumErrors.ALREADY_PAID)
    if payment.status == PaymentStatus.CANCELLED:
        return _err(UzumErrors.PAYMENT_CANCELLED)

    # Uzum texnik xodimi (Абдухамид Атакулов, 2026-08-20) tasdiqladi: /check
    # javobida "amount" SO'MDA (tiyinda emas) bo'lishi kerak. 2026-08-24:
    # xuddi shu xodim maydon shaklini TUZATDI -- ilgari tekis satr edi
    # ("amount": "5000"), aslida {"value": "..."} ichma-ich obyekt bo'lishi
    # kerak ekan. So'm/tekis-satr qoidasi hali ham amalda, faqat qadoqlash
    # o'zgardi.
    return JSONResponse(status_code=200, content=check_success(service_id, {"amount": {"value": str(int(payment.amount))}}))


@router.post("/create")
async def uzum_create(request: Request, db: Session = Depends(get_db)):
    body = await _parse_body(request)
    if body is None:
        return _err(UzumErrors.JSON_PARSE_ERROR)
    _log("CREATE", body)

    err = _check_auth_and_service(request, body, check_service=True)
    if err:
        return _err(err)

    service_id = body.get("serviceId")
    trans_id = body.get("transId")
    params = body.get("params")
    amount_in = body.get("amount")  # tiyinda (rasmiy hujjat: "Сумма платежа в тийинах")

    if not trans_id or not isinstance(params, dict) or amount_in is None:
        return _err(UzumErrors.MISSING_REQUIRED_PARAMS)

    # Uzum spetsifikatsiyasi: xuddi shu transId bilan qayta /create chaqirilsa
    # XATO 10010 qaytariladi -- muvaffaqiyatni qaytadan qaytarish EMAS
    # (Payme'dan farqli idempotentlik modeli).
    existing = _find_by_uzum_txn(db, trans_id)
    if existing:
        return _err(UzumErrors.TRANSACTION_ALREADY_CREATED)

    payment = _find_by_account(db, params)
    if not payment:
        return _err(UzumErrors.ATTRIBUTE_NOT_FOUND)
    if payment.status == PaymentStatus.APPROVED:
        return _err(UzumErrors.ALREADY_PAID)
    if payment.status == PaymentStatus.CANCELLED:
        return _err(UzumErrors.PAYMENT_CANCELLED)
    if payment.uzum_transaction_id:
        # Boshqa transId bilan allaqachon band -- rasmiy jadvalda aniq kod
        # yo'q, eng yaqini ham ALREADY_PAID (jarayon boshlangan holat).
        return _err(UzumErrors.ALREADY_PAID)

    if int(amount_in) != _amount_tiyin(payment.amount):
        return _err(UzumErrors.INVALID_AMOUNT)

    payment.uzum_transaction_id = str(trans_id)
    payment.uzum_create_time = datetime.utcnow()
    db.commit()

    return JSONResponse(status_code=200, content=create_success(service_id, str(trans_id), int(amount_in), _dt_to_ms(payment.uzum_create_time)))


@router.post("/confirm")
async def uzum_confirm(request: Request, db: Session = Depends(get_db)):
    body = await _parse_body(request)
    if body is None:
        return _err(UzumErrors.JSON_PARSE_ERROR)
    _log("CONFIRM", body)

    err = _check_auth_and_service(request, body, check_service=False)
    if err:
        return _err(err)

    service_id = body.get("serviceId")
    trans_id = body.get("transId")
    # paymentSource/tariff/processingReferenceNumber/phone/cardType -- rasmiy
    # so'rov tarkibida, lekin bizning tasdiqlash mantig'imiz uchun shart
    # emas (faqat transId orqali tranzaksiya topiladi va yakunlanadi).
    if not trans_id:
        return _err(UzumErrors.MISSING_REQUIRED_PARAMS)

    payment = _find_by_uzum_txn(db, trans_id)
    if not payment:
        return _err(UzumErrors.TRANSACTION_NOT_FOUND)

    if payment.status == PaymentStatus.CANCELLED:
        return _err(UzumErrors.TRANSACTION_CANCELLED)
    if payment.status == PaymentStatus.APPROVED:
        # Rasmiy hujjat: qayta tasdiqlash urinishi -- XATO 10016.
        return _err(UzumErrors.TRANSACTION_ALREADY_CONFIRMED)

    # 30 daqiqalik muddat (rasmiy hujjat): agar /create'dan beri shuncha vaqt
    # o'tgan bo'lsa, tranzaksiya muvaffaqiyatsiz hisoblanadi.
    if payment.uzum_create_time and datetime.utcnow() - payment.uzum_create_time > timedelta(minutes=30):
        payment.status = PaymentStatus.CANCELLED
        payment.uzum_cancel_time = datetime.utcnow()
        if payment.job_id:
            job = db.query(DubbingJob).filter(DubbingJob.id == payment.job_id).first()
            if job and job.status == JobStatus.AWAITING_PAYMENT:
                job.status = JobStatus.FAILED
                job.error_message = "To'lov muddati tugadi."
        db.commit()
        return _err(UzumErrors.TRANSACTION_CANCELLED)

    payment.status = PaymentStatus.APPROVED
    payment.uzum_confirm_time = datetime.utcnow()

    from backend.services.payment_fulfillment import apply_successful_payment
    apply_successful_payment(db, payment)

    db.commit()

    amount_out = _amount_tiyin(payment.amount)
    return JSONResponse(status_code=200, content=confirm_success(service_id, str(trans_id), amount_out, _dt_to_ms(payment.uzum_confirm_time)))


@router.post("/reverse")
async def uzum_reverse(request: Request, db: Session = Depends(get_db)):
    body = await _parse_body(request)
    if body is None:
        return _err(UzumErrors.JSON_PARSE_ERROR)
    _log("REVERSE", body)

    err = _check_auth_and_service(request, body, check_service=False)
    if err:
        return _err(err)

    service_id = body.get("serviceId")
    trans_id = body.get("transId")
    if not trans_id:
        return _err(UzumErrors.MISSING_REQUIRED_PARAMS)

    payment = _find_by_uzum_txn(db, trans_id)
    if not payment:
        return _err(UzumErrors.TRANSACTION_NOT_FOUND)

    if payment.status == PaymentStatus.CANCELLED:
        # Rasmiy hujjat: qayta bekor qilish urinishi -- XATO 10018.
        return _err(UzumErrors.TRANSACTION_ALREADY_CANCELLED)

    if payment.status == PaymentStatus.APPROVED:
        # Xizmat allaqachon ko'rsatilgan (apply_successful_payment
        # chaqirilgan) -- bizda avtomatik pul qaytarish/bekor qilish
        # mexanizmi yo'q, shuning uchun bekor qilishni rad etamiz
        # (Click/Payme'dagi needs_refund bayrog'i bilan bir xil ehtiyotkorlik).
        return _err(UzumErrors.CANNOT_CANCEL)

    payment.status = PaymentStatus.CANCELLED
    payment.uzum_cancel_time = datetime.utcnow()

    if payment.job_id:
        job = db.query(DubbingJob).filter(DubbingJob.id == payment.job_id).first()
        if job and job.status == JobStatus.AWAITING_PAYMENT:
            job.status = JobStatus.FAILED
            job.error_message = "To'lov bekor qilindi."

    db.commit()

    amount_out = _amount_tiyin(payment.amount)
    return JSONResponse(status_code=200, content=reverse_success(service_id, str(trans_id), amount_out, _dt_to_ms(payment.uzum_cancel_time)))


@router.post("/status")
async def uzum_status(request: Request, db: Session = Depends(get_db)):
    body = await _parse_body(request)
    if body is None:
        return _err(UzumErrors.JSON_PARSE_ERROR)
    _log("STATUS", body)

    err = _check_auth_and_service(request, body, check_service=False)
    if err:
        return _err(err)

    service_id = body.get("serviceId")
    trans_id = body.get("transId")
    if not trans_id:
        return _err(UzumErrors.MISSING_REQUIRED_PARAMS)

    payment = _find_by_uzum_txn(db, trans_id)
    if not payment:
        return _err(UzumErrors.TRANSACTION_NOT_FOUND)

    status_keyword = (
        "CONFIRMED" if payment.status == PaymentStatus.APPROVED else
        "REVERSED" if payment.status == PaymentStatus.CANCELLED else
        "CREATED"
    )
    amount_out = _amount_tiyin(payment.amount)
    return JSONResponse(status_code=200, content=status_success(
        service_id, str(trans_id), amount_out, status_keyword,
        _dt_to_ms(payment.uzum_create_time),
        _dt_to_ms(payment.uzum_confirm_time),
        _dt_to_ms(payment.uzum_cancel_time),
    ))
