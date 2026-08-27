"""Uzum Bank Merchant webhook uchun yordamchi funksiyalar.

RASMIY SPETSIFIKATSIYA (2026-08-20, https://developer.uzumbank.uz/merchant/):
5 ta webhook -- /check, /create, /confirm, /reverse, /status. Barchasi
Authorization: Basic base64(login:parol) orqali tekshiriladi (login/parolni
BIZ tanlaymiz, Uzum'ga beramiz).

Umumiy qoida: xato bo'lsa HTTP 400 + {"errorCode": "<son-string>"} (boshqa
maydonlar SHART EMAS). errorCode qiymatlari -- pastdagi UzumErrors klassi,
rasmiy hujjatning "Kody oshibok" jadvalidan so'zma-so'z olingan.

So'rov shakllari (hammasi serviceId (int64) + timestamp (int64, ms) bilan
boshlanadi):
  /check:   {..., "params": {...}}                              -- account params ichida
  /create:  {..., "transId": "<uuid>", "params": {...}, "amount": <tiyin>}
  /confirm: {..., "transId": "<uuid>", "paymentSource": "<enum>",
             "tariff": str|null, "processingReferenceNumber": str|null,
             "phone": "<string>", "cardType": int|null}          -- params YO'Q
  /reverse: {..., "transId": "<uuid>"}                           -- params YO'Q
  /status:  {..., "transId": "<uuid>"}                           -- params YO'Q

Javob shakllari (muvaffaqiyat, HTTP 200):
  /check:   {serviceId, timestamp, status:"OK", data:{...}}
  /create:  {serviceId, transId, status:"CREATED", transTime, data:{...}, amount}
  /confirm: {serviceId, transId, status:"CONFIRMED", confirmTime, data:{...}, amount}
  /reverse: {serviceId, transId, status:"REVERSED", reverseTime, data:{...}, amount}
  /status:  {serviceId, transId, status:"<joriy holat>", transTime,
             confirmTime|null, reverseTime|null, data:{...}, amount}

MUHIM -- Uzum IDEMPOTENT QAYTA CHAQIRUVNI XATO deb hisoblaydi (Payme'dan
farqli!): xuddi shu transId bilan /create qayta chaqirilsa -> xato 10010
(muvaffaqiyatni qaytadan qaytarish emas). Xuddi shu tarzda /confirm allaqachon
tasdiqlangan tranzaksiyaga -> xato 10016, /reverse allaqachon bekor
qilinganga -> xato 10018.

/check'ning "data"sida BIZ o'zimiz FAQAT "amount"ni (string, SO'MDA, tiyinda
emas) qo'shamiz -- bu Uzum texnik xodimi (Абдухамид Атакулов) tomonidan
to'g'ridan-to'g'ri tasdiqlangan, umumiy hujjatdagi bo'sh {} namunasidan
ustunroq (bizning aniq xizmatimiz uchun maxsus ko'rsatma)."""
import base64
import time
import zlib


def verify_basic_auth(auth_header: str | None, username: str, password: str) -> bool:
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[len("Basic "):]).decode("utf-8")
        got_user, _, got_pass = decoded.partition(":")
    except Exception:
        return False
    if not username or not password:
        return False
    return got_user == username and got_pass == password


def account_id_from_payment_id(payment_id) -> int:
    """Uzum'ning "account" maydoni oddiy raqam ko'rinishida keladi -- bizning
    Payment.id UUID, shuning uchun Click'dagi (click_routes.py) crc32
    naqshini qaytadan ishlatamiz."""
    raw = payment_id.bytes if hasattr(payment_id, "bytes") else str(payment_id).encode()
    return zlib.crc32(raw)


def now_ms() -> int:
    return int(time.time() * 1000)


class UzumErrors:
    """Rasmiy "Kody oshibok" jadvalidan (developer.uzumbank.uz/merchant),
    2026-08-20 o'qib olindi -- so'zma-so'z, taxmin emas."""
    ACCESS_DENIED = "10001"                    # barcha metodlar -- auth xato
    JSON_PARSE_ERROR = "10002"                 # barcha metodlar
    INVALID_METHOD = "10003"                   # barcha metodlar -- POST emas
    MISSING_REQUIRED_PARAMS = "10005"          # barcha metodlar
    INVALID_SERVICE_ID = "10006"               # /check, /create
    ATTRIBUTE_NOT_FOUND = "10007"              # /check, /create -- masalan account topilmadi
    ALREADY_PAID = "10008"                     # /check, /create
    PAYMENT_CANCELLED = "10009"                # /check, /create
    TRANSACTION_ALREADY_CREATED = "10010"      # /create -- xuddi shu transId qayta yuborilsa
    INVALID_AMOUNT = "10011"                   # /create
    AMOUNT_TOO_LOW = "10012"                   # /create
    AMOUNT_TOO_HIGH = "10013"                  # /create
    TRANSACTION_NOT_FOUND = "10014"            # /confirm, /reverse, /status
    TRANSACTION_CANCELLED = "10015"            # /confirm -- bekor qilingan, tasdiqlab bo'lmaydi
    TRANSACTION_ALREADY_CONFIRMED = "10016"    # /confirm -- qayta tasdiqlash urinishi
    CANNOT_CANCEL = "10017"                    # /reverse
    TRANSACTION_ALREADY_CANCELLED = "10018"    # /reverse -- qayta bekor qilish urinishi
    INTERNAL_ERROR = "99999"                   # barcha metodlar


def error_envelope(error_code: str) -> dict:
    """Rasmiy hujjat: HTTP 400 + FAQAT "errorCode" (string) shart."""
    return {"errorCode": error_code}


def check_success(service_id, data: dict | None = None) -> dict:
    return {
        "serviceId": service_id,
        "timestamp": now_ms(),
        "status": "OK",
        "data": data or {},
    }


def create_success(service_id, trans_id: str, amount, trans_time_ms: int, data: dict | None = None) -> dict:
    """trans_time_ms -- DB'da saqlangan payment.uzum_create_time'dan hisoblanadi
    (endi now_ms() emas), aks holda /status keyinroq BOSHQA (bir necha
    millisekund farqli) qiymat qaytarardi -- 2026-08-21, foydalanuvchi
    Postman orqali /status va /create javoblarini solishtirib topgan bag."""
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "CREATED",
        "transTime": trans_time_ms,
        "data": data or {},
        "amount": amount,
    }


def confirm_success(service_id, trans_id: str, amount, confirm_time_ms: int, data: dict | None = None) -> dict:
    """confirm_time_ms -- DB'dagi payment.uzum_confirm_time'dan (create_success
    bilan bir xil sabab)."""
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "CONFIRMED",
        "confirmTime": confirm_time_ms,
        "data": data or {},
        "amount": amount,
    }


def reverse_success(service_id, trans_id: str, amount, reverse_time_ms: int, data: dict | None = None) -> dict:
    """reverse_time_ms -- DB'dagi payment.uzum_cancel_time'dan (create_success
    bilan bir xil sabab)."""
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": "REVERSED",
        "reverseTime": reverse_time_ms,
        "data": data or {},
        "amount": amount,
    }


def status_success(
    service_id, trans_id: str, amount, status: str,
    trans_time_ms, confirm_time_ms, reverse_time_ms, data: dict | None = None,
) -> dict:
    return {
        "serviceId": service_id,
        "transId": trans_id,
        "status": status,
        "transTime": trans_time_ms,
        "confirmTime": confirm_time_ms,
        "reverseTime": reverse_time_ms,
        "data": data or {},
        "amount": amount,
    }
