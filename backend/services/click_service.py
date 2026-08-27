import hashlib
import math
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

class ClickErrors:
    SUCCESS = 0
    SIGN_CHECK_FAILED = -1
    INVALID_AMOUNT = -2
    ACTION_NOT_FOUND = -3
    ALREADY_PAID = -4
    USER_NOT_FOUND = -5
    TRANSACTION_NOT_FOUND = -6
    FAILED_TO_UPDATE = -7
    ERROR_IN_REQUEST = -8
    TRANSACTION_CANCELLED = -9

CLICK_BASE_URL = 'https://my.click.uz/services/pay'


def normalize_uzs_amount(amount: Decimal | float | int | str) -> int:
    normalized = Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(normalized)

def generate_digest(timestamp: int, secret_key: str) -> str:
    data = f"{timestamp}{secret_key}"
    return hashlib.sha1(data.encode('utf-8')).hexdigest()

def generate_payment_url(
    merchant_id: str,
    service_id: str,
    transaction_param: str,
    amount: Decimal | float | int | str,
    return_url: str,
    merchant_user_id: str = "",
) -> str:
    params = {
        'service_id': service_id,
        'merchant_id': merchant_id,
        'amount': str(normalize_uzs_amount(amount)),
        'transaction_param': transaction_param,
        'return_url': return_url,
    }
    if merchant_user_id:
        params['merchant_user_id'] = merchant_user_id
    return f"{CLICK_BASE_URL}?{urlencode(params)}"

def validate_signature(params: dict, secret_key: str) -> bool:
    click_trans_id = params.get('click_trans_id')
    service_id = params.get('service_id')
    merchant_trans_id = params.get('merchant_trans_id')
    amount = params.get('amount')
    action = params.get('action')
    sign_time = params.get('sign_time')
    sign_string = params.get('sign_string')
    merchant_prepare_id = params.get('merchant_prepare_id')

    if not all([click_trans_id, service_id, merchant_trans_id, amount, str(action), sign_time, sign_string]):
        return False

    if str(action) == "1":
        # Complete request: click_trans_id + service_id + secret_key + merchant_trans_id + merchant_prepare_id + amount + action + sign_time
        prep_str = str(merchant_prepare_id) if merchant_prepare_id is not None else ""
        payload_str = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{prep_str}{amount}{action}{sign_time}"
    else:
        # Prepare request: click_trans_id + service_id + secret_key + merchant_trans_id + amount + action + sign_time
        payload_str = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}"

    expected = hashlib.md5(payload_str.encode('utf-8')).hexdigest()
    return expected.lower() == str(sign_string).lower()

def calculate_price(duration_minutes: float, *, is_first_video: bool = False) -> int:
    """
    Pricing logic:
    - Videos < 45 minutes: free.
    - Videos >= 45 minutes: 500 UZS per minute.
      Example: 45 min → 22,500 UZS, 90 min → 45,000 UZS.
    """
    if duration_minutes < 45.0:
        return 0
    if is_first_video:
        return 0

    # 500 UZS per minute
    amount = math.ceil(duration_minutes) * 500
    return normalize_uzs_amount(amount)


