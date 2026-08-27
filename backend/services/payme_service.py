"""Payme (Paycom) Merchant API uchun yordamchi funksiyalar -- autentifikatsiya,
xato kodlari va checkout URL generatsiyasi. To'liq spetsifikatsiya:
https://developer.help.paycom.uz/protokol-merchant-api (2026-08-19 da o'qib
chiqilgan)."""
import base64
import time


class PaymeErrors:
    """https://developer.help.paycom.uz/protokol-merchant-api/obschie-oshibki
    va har bir metodning o'z sahifasidagi kodlar."""
    INVALID_JSON_RPC = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INSUFFICIENT_PRIVILEGE = -32504
    SYSTEM_ERROR = -32400

    INVALID_AMOUNT = -31001
    TRANSACTION_NOT_FOUND = -31003
    CANNOT_PERFORM_OPERATION = -31008
    ORDER_ALREADY_FULFILLED = -31007
    INVALID_ACCOUNT = -31050  # -31050 dan -31099 gacha oralig'i "account" xatolari uchun ajratilgan


def payme_error(code: int, message_uz: str, message_ru: str = "", message_en: str = "", data: str | None = None, request_id=None) -> dict:
    """RPC-javob formatidagi xato ob'ekti (Formatoveta sahifasiga mos)."""
    body = {
        "error": {
            "code": code,
            "message": {
                "uz": message_uz,
                "ru": message_ru or message_uz,
                "en": message_en or message_uz,
            },
        },
        "id": request_id,
    }
    if data is not None:
        body["error"]["data"] = data
    return body


def payme_result(result: dict, request_id=None) -> dict:
    return {"result": result, "id": request_id}


def verify_payme_auth(auth_header: str | None, key: str, test_key: str) -> bool:
    """Authorization: Basic base64(Paycom:<key yoki test_key>). Login qismi
    ("Paycom") tekshirilmaydi -- faqat parol (key) to'g'riligi muhim, Payme
    o'zi doim shu login bilan yuboradi."""
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[len("Basic "):]).decode("utf-8")
        _, _, password = decoded.partition(":")
    except Exception:
        return False
    if not password:
        return False
    return password == key or password == test_key


def now_ms() -> int:
    return int(time.time() * 1000)


def generate_payme_checkout_url(
    merchant_id: str,
    account_field: str,
    account_value: str,
    amount_tiyin: int,
    return_url: str,
    lang: str = "uz",
    sandbox: bool = False,
) -> str:
    """https://developer.help.paycom.uz/initsializatsiya-platezhey/otpravka-cheka-po-metodu-get
    Format: https://<host>/base64(m=...;ac.field=value;a=...;c=...;l=...)

    sandbox=True -> checkout.test.paycom.uz (kassa faqat TEST_KEY bilan
    ro'yxatdan o'tgan bo'lsa, production checkout.paycom.uz "Поставщик не
    найден или заблокирован" deb rad etadi -- 2026-08-19, haqiqiy checkoutda
    tasdiqlangan xato). Diqqat: bare "test.paycom.uz" (checkout. prefiksisiz)
    sandbox TEST BOSHQARUV PANELI ("Песочница Paycom" -- Merchant API'ni
    qo'lda sinash uchun), haqiqiy checkout sahifasi emas -- shuning uchun
    checkout ham "checkout." subdomeni bilan bo'lishi shart."""
    params = (
        f"m={merchant_id};"
        f"ac.{account_field}={account_value};"
        f"a={amount_tiyin};"
        f"c={return_url};"
        f"l={lang}"
    )
    encoded = base64.b64encode(params.encode("utf-8")).decode("ascii")
    host = "checkout.test.paycom.uz" if sandbox else "checkout.paycom.uz"
    return f"https://{host}/{encoded}"
