"""Paynet (UZPAYNET) to'lov integratsiyasi -- ikki xil yo'nalish:

1. Bizning backend to'lovni BOSHLAYDI (/initiate*): foydalanuvchi to'lovni
   boshlaydi, biz Payment(provider=PAYNET, status=PENDING) yozib, unga mos
   "order_id"ni (Payment.id) qaytaramiz. Payme/Click'dan farqli -- hujjatda
   Paynet tomonidan taqdim etiladigan checkout havolasi ko'rsatilmagan
   (bu -- klient poastavshik agentiga/ilovasiga o'zi murojaat qilib, shu
   order_id'ni kiritib to'laydigan "billing agregator" modeli). Frontend
   foydalanuvchiga shu order_id'ni ko'rsatishi kerak (2026-08-20, hali
   frontend qismi yozilmagan -- UX kelishilishi kerak).

2. Paynet bizning backendga so'rov yuboradi (/webhook): bitta JSON-RPC 2.0
   kirish nuqtasi, "method" maydoni orqali tarmoqlanadi (Payme'ning Merchant
   API'siga o'xshash naqsh). Farqi: Basic Auth login/parolni BIZ tanlaymiz
   (Paynet bizga bermaydi), va noto'g'ri/yo'q autentifikatsiya holatida
   JSON-RPC xato tanasi emas, chin HTTP 401 qaytarilishi SHART
   (spetsifikatsiya: "Спецификация универсального WEB-сервиса поставщика
   услуг", UZPAYNET, v1.0, 2.2-bo'lim).

   "fields.order_id" -- bizning Payment.id (Payme'dagi account.payment_id
   bilan bir xil naqsh). Foydalanuvchi tomonidan tasdiqlangan (2026-08-24) --
   ilgari bu taxmin edi (Paynet'ning "test uchun hisob" namunasidagi maydon
   nomidan kelib chiqqan, rasmiy hujjatda umumiy misol "client_id"
   ishlatgan edi), endi qat'iy fakt sifatida ishlatilishi mumkin.
"""
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db, DubbingJob, JobStatus, User
from backend.models.payment import Payment, PaymentStatus, PaymentProvider
from backend.services.auth import get_current_user
from backend.services.paynet_service import (
    PaynetErrors,
    rpc_result,
    rpc_error,
    verify_basic_auth,
    provider_trn_id,
    now_gmt5_str,
    dt_to_gmt5_str,
)
from backend.config import get_settings

router = APIRouter(prefix="/api/payments/paynet", tags=["paynet"])

ORDER_FIELD = "order_id"  # Payme'dagi ACCOUNT_FIELD bilan bir xil naqsh -- Payment.id


def _check_service_id(params: dict, req_id):
    """Barcha metodlar uchun bitta joyda -- ilgari faqat PerformTransaction
    o'zi tekshirardi, qolgan metodlar serviceId'ni umuman tekshirmasdi.
    Paynet texnik jamoasi tasdiqladi (2026-08-24): noto'g'ri serviceId
    HAR BIR metodda 305 (Xizmat topilmadi) bilan rad etilishi kerak."""
    service_id = params.get("serviceId")
    if service_id is None:
        return rpc_error(PaynetErrors.REQUIRED_PARAMS_MISSING, "serviceId talab qilinadi.", req_id)
    settings = get_settings()
    try:
        if int(service_id) != int(settings.PAYNET_SERVICE_ID):
            return rpc_error(PaynetErrors.SERVICE_NOT_FOUND, "Xizmat topilmadi.", req_id)
    except (TypeError, ValueError):
        return rpc_error(PaynetErrors.SERVICE_NOT_FOUND, "Xizmat topilmadi.", req_id)
    return None


def _amount_tiyin(so_um_amount: float) -> int:
    return int(round(so_um_amount * 100))


# ─────────────────────────────────────────────────────────────────────────
# 1. Initiatsiya (bizning backend -> Paynet orqali to'lash uchun order_id)
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
    lekin checkout havolasi o'rniga faqat order_id qaytaradi (Paynet'da
    hozircha bizga ma'lum checkout-URL mexanizmi yo'q)."""
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
        Payment.job_id == job.id, Payment.status == PaymentStatus.PENDING, Payment.provider == PaymentProvider.PAYNET
    ).first()
    if not payment:
        payment = Payment(
            user_id=current_user.id, job_id=job.id, amount=amount,
            provider=PaymentProvider.PAYNET, status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
    elif payment.amount != amount:
        payment.amount = amount
        db.commit()

    return {"success": True, "order_id": str(payment.id), "payment_id": str(payment.id), "amount": amount}


# ─────────────────────────────────────────────────────────────────────────
# 2. Merchant API (Paynet -> bizning backend, JSON-RPC 2.0)
# ─────────────────────────────────────────────────────────────────────────

def _find_by_order_id(db: Session, params: dict) -> Payment | None:
    fields = params.get("fields")
    if not isinstance(fields, dict):
        return None
    order_id = fields.get(ORDER_FIELD)
    if not order_id or not isinstance(order_id, str):
        return None
    try:
        return db.query(Payment).filter(Payment.id == order_id).first()
    except Exception:
        return None


def _find_by_paynet_txn(db: Session, params: dict) -> Payment | None:
    txn_id = params.get("transactionId")
    if txn_id is None:
        return None
    return db.query(Payment).filter(Payment.paynet_transaction_id == txn_id).first()


def _handle_get_information(db: Session, params: dict, req_id):
    err = _check_service_id(params, req_id)
    if err:
        return err

    payment = _find_by_order_id(db, params)
    if not payment or payment.status != PaymentStatus.PENDING:
        return rpc_error(PaynetErrors.CLIENT_NOT_FOUND, "To'lov topilmadi yoki muddati o'tgan.", req_id)

    label = "Kutubxona kirish huquqi" if payment.is_library_access else (
        f"Tarif: {payment.plan}" if payment.plan else "Video dublyaj"
    )
    return rpc_result({
        # Paynet texnik jamoasi tasdiqladi (2026-08-24): "status" STRING
        # bo'lishi kerak (spec jadvalida "Number" deyilgan, lekin bu
        # noto'g'ri -- ularning o'z misolida ham "0" qo'shtirnoqda).
        "status": "0",
        "timestamp": now_gmt5_str(),
        "fields": {
            # Paynet texnik jamoasi tasdiqladi (2026-08-24): bu yerda summa
            # SO'MDA qaytarilishi kerak -- tiyinda emas (PerformTransaction
            # so'rovidagi "amount" tiyinda bo'lishi bilan farqli, xuddi
            # Uzum'ning /check javobidagi bir xil qoida kabi).
            "amount": int(payment.amount),
            "name": label,
        },
    }, req_id)


def _handle_perform_transaction(db: Session, params: dict, req_id):
    amount_tiyin = params.get("amount")
    txn_id = params.get("transactionId")

    if amount_tiyin is None or txn_id is None:
        return rpc_error(PaynetErrors.REQUIRED_PARAMS_MISSING, "Majburiy parametr(lar) yo'q.", req_id)

    err = _check_service_id(params, req_id)
    if err:
        return err

    # Paynet texnik jamoasi tasdiqladi (2026-08-24): bir xil transactionId
    # bilan takroriy so'rov HAR DOIM 201 (Tranzaksiya allaqachon mavjud) --
    # holat allaqachon APPROVED bo'lsa ham muvaffaqiyatni qaytadan
    # qaytarilmaydi (ilgari shunday edi, Payme uslubida idempotent-success --
    # bu noto'g'ri ekan). Uzum'ning /create'dagi bir xil qat'iy qoidasiga mos.
    existing = _find_by_paynet_txn(db, params)
    if existing:
        return rpc_error(PaynetErrors.TRANSACTION_ALREADY_EXISTS, "Tranzaksiya allaqachon mavjud.", req_id)

    payment = _find_by_order_id(db, params)
    if not payment or payment.status != PaymentStatus.PENDING:
        return rpc_error(PaynetErrors.TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi.", req_id)

    if amount_tiyin != _amount_tiyin(payment.amount):
        return rpc_error(PaynetErrors.WRONG_AMOUNT, "Noto'g'ri summa.", req_id)

    payment.paynet_transaction_id = txn_id
    payment.status = PaymentStatus.APPROVED
    payment.paynet_perform_time = datetime.utcnow()

    from backend.services.payment_fulfillment import apply_successful_payment
    apply_successful_payment(db, payment)

    db.commit()

    return rpc_result({
        "providerTrnId": provider_trn_id(payment.id),
        "timestamp": dt_to_gmt5_str(payment.paynet_perform_time),
        # "balance" -- Paynet shartnoma ilovasi (Таблица 4) buni MAJBURIY
        # deb belgilagan ("Баланс плательщика после проведения транзакции").
        # Bizda hamyon/balans tushunchasi yo'q (bir martalik to'lov xizmati)
        # -- foydalanuvchi bilan kelishilgan: doim 0 qaytariladi (2026-08-24).
        "fields": {ORDER_FIELD: str(payment.id), "balance": 0},
    }, req_id)


def _handle_check_transaction(db: Session, params: dict, req_id):
    err = _check_service_id(params, req_id)
    if err:
        return err

    payment = _find_by_paynet_txn(db, params)
    if not payment:
        return rpc_result({
            "providerTrnId": 0,
            "timestamp": now_gmt5_str(),
            "transactionState": 3,
        }, req_id)

    state = 2 if payment.status == PaymentStatus.CANCELLED else (1 if payment.status == PaymentStatus.APPROVED else 3)
    ts = payment.paynet_cancel_time or payment.paynet_perform_time or payment.updated_at
    return rpc_result({
        "providerTrnId": provider_trn_id(payment.id),
        "timestamp": dt_to_gmt5_str(ts),
        "transactionState": state,
    }, req_id)


def _handle_cancel_transaction(db: Session, params: dict, req_id):
    err = _check_service_id(params, req_id)
    if err:
        return err

    payment = _find_by_paynet_txn(db, params)
    if not payment:
        return rpc_error(PaynetErrors.TRANSACTION_NOT_FOUND, "Tranzaksiya topilmadi.", req_id)

    if payment.status == PaymentStatus.CANCELLED:
        # Idempotent -- allaqachon bekor qilingan.
        return rpc_result({
            "providerTrnId": provider_trn_id(payment.id),
            "timestamp": dt_to_gmt5_str(payment.paynet_cancel_time or payment.updated_at),
            "transactionState": 2,
        }, req_id)

    was_approved = payment.status == PaymentStatus.APPROVED
    payment.status = PaymentStatus.CANCELLED
    payment.paynet_cancel_time = datetime.utcnow()

    if not was_approved and payment.job_id:
        job = db.query(DubbingJob).filter(DubbingJob.id == payment.job_id).first()
        if job and job.status == JobStatus.AWAITING_PAYMENT:
            job.status = JobStatus.FAILED
            job.error_message = "To'lov bekor qilindi."

    db.commit()

    return rpc_result({
        "providerTrnId": provider_trn_id(payment.id),
        "timestamp": dt_to_gmt5_str(payment.paynet_cancel_time),
        "transactionState": 2,
    }, req_id)


def _handle_get_statement(db: Session, params: dict, req_id):
    from backend.services.paynet_service import parse_gmt5_str

    err = _check_service_id(params, req_id)
    if err:
        return err

    date_from = params.get("dateFrom")
    date_to = params.get("dateTo")
    if not date_from or not date_to:
        return rpc_error(PaynetErrors.REQUIRED_PARAMS_MISSING, "dateFrom/dateTo talab qilinadi.", req_id)

    try:
        dt_from = parse_gmt5_str(date_from).astimezone().replace(tzinfo=None)
        dt_to = parse_gmt5_str(date_to).astimezone().replace(tzinfo=None)
    except ValueError:
        return rpc_error(PaynetErrors.WRONG_DATETIME_FORMAT, "Noto'g'ri sana formati.", req_id)

    payments = db.query(Payment).filter(
        Payment.provider == PaymentProvider.PAYNET,
        Payment.status == PaymentStatus.APPROVED,
        Payment.paynet_perform_time >= dt_from,
        Payment.paynet_perform_time <= dt_to,
    ).order_by(Payment.paynet_perform_time.asc()).all()

    statements = [
        {
            "amount": _amount_tiyin(p.amount),
            "transactionId": p.paynet_transaction_id,
            "providerTrnId": provider_trn_id(p.id),
            "timestamp": dt_to_gmt5_str(p.paynet_perform_time),
        }
        for p in payments
    ]
    return rpc_result({"statements": statements}, req_id)


_METHOD_HANDLERS = {
    "GetInformation": _handle_get_information,
    "PerformTransaction": _handle_perform_transaction,
    "CheckTransaction": _handle_check_transaction,
    "CancelTransaction": _handle_cancel_transaction,
    "GetStatement": _handle_get_statement,
    # ChangePassword -- ixtiyoriy metod, hozircha amalga oshirilmagan.
}


@router.post("/webhook")
async def paynet_webhook(request: Request, db: Session = Depends(get_db)):
    """Paynet Universal Web-Service'ning yagona kirish nuqtasi. Hujjat talabi
    (2.2-bo'lim): auth yo'q/xato bo'lsa chin HTTP 401 (JSON-RPC xato tanasi
    emas) -- shuning uchun bu tekshiruv JSON tahlildan OLDIN bajariladi."""
    settings = get_settings()
    if not verify_basic_auth(request.headers.get("authorization"), settings.PAYNET_USERNAME, settings.PAYNET_PASSWORD):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body = await request.json()
    except Exception:
        return rpc_error(PaynetErrors.PARSE_ERROR, "JSON xato.")

    if not isinstance(body, dict):
        return rpc_error(PaynetErrors.INVALID_REQUEST, "So'rov formati noto'g'ri.")

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params")

    if not method or not isinstance(params, dict):
        return rpc_error(PaynetErrors.INVALID_REQUEST, "So'rov formati noto'g'ri.", req_id)

    handler = _METHOD_HANDLERS.get(method)
    if not handler:
        return rpc_error(PaynetErrors.METHOD_NOT_FOUND, "Metod topilmadi.", req_id)

    try:
        return handler(db, params, req_id)
    except Exception as exc:
        db.rollback()
        return rpc_error(PaynetErrors.SYSTEM_ERROR, f"Tizim xatosi: {exc}", req_id)
