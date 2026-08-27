"""Paynet (UZPAYNET) Universal Web-Service uchun yordamchi funksiyalar --
autentifikatsiya, xato kodlari va JSON-RPC 2.0 javob konvertlari.
Spetsifikatsiya: "Спецификация универсального WEB-сервиса поставщика
услуг" (UZPAYNET, версия 1.0, 2026-08-20 o'qib chiqilgan, foydalanuvchi
yuborgan PDF). Payme'dan farqli -- login/parolni BIZ tanlaymiz va Paynet'ga
beramiz (ular bizga bermaydi), va noto'g'ri/yo'q auth holatida JSON-RPC
xato tanasi emas, chin HTTP 401 qaytarilishi SHART (spetsifikatsiya talabi)."""
import base64
import zlib
from datetime import datetime, timezone, timedelta


class PaynetErrors:
    """Hujjatning 2.5-bo'limi "Общие ошибки" jadvalidan."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    SYSTEM_ERROR = -32603

    SUCCESS = 0
    INSUFFICIENT_FUNDS_FOR_CANCEL = 77
    SERVICE_TEMPORARILY_UNAVAILABLE = 100
    QUOTA_EXCEEDED = 101
    SYSTEM_ERROR_BUSINESS = 102
    UNKNOWN_ERROR = 103
    WALLET_NOT_IDENTIFIED = 113
    TRANSACTION_ALREADY_EXISTS = 201
    TRANSACTION_ALREADY_CANCELLED = 202
    TRANSACTION_NOT_FOUND = 203
    CLIENT_NOT_FOUND = 302
    SERVICE_NOT_FOUND = 305
    REQUIRED_PARAMS_MISSING = 411
    WRONG_LOGIN_PASSWORD = 412
    WRONG_AMOUNT = 413
    WRONG_DATETIME_FORMAT = 414
    ACCESS_DENIED = 601


_GMT5 = timezone(timedelta(hours=5))


def now_gmt5_str() -> str:
    return datetime.now(_GMT5).strftime("%Y-%m-%d %H:%M:%S")


def dt_to_gmt5_str(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_GMT5).strftime("%Y-%m-%d %H:%M:%S")


def parse_gmt5_str(value: str) -> datetime:
    """Hujjat ikkita formatni aralashtirib ishlatadi (masalan CancelTransaction
    misolida "16.06.2021 12:44:57", boshqa joylarda "2021-06-16 12:41:54") --
    ikkalasini ham qabul qilamiz."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=_GMT5)
        except ValueError:
            continue
    raise ValueError(f"Noto'g'ri sana formati: {value}")


def provider_trn_id(payment_id) -> int:
    """Bizning tomondan generatsiya qilinadigan raqamli tranzaksiya ID --
    Click'dagi merchant_prepare_id/merchant_confirm_id bilan bir xil naqsh
    (payment.id UUID'idan CRC32)."""
    return zlib.crc32(payment_id.bytes if hasattr(payment_id, "bytes") else str(payment_id).encode())


def rpc_result(result: dict, request_id=None) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def rpc_error(code: int, message: str, request_id=None) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


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
