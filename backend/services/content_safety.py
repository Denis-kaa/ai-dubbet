"""Dublajdan oldingi majburiy kontent xavfsizligi tekshiruvi (Safety Gate).

Ikki bosqichda ishlaydi:
1. Metadata bosqichi — job yaratilishidan OLDIN (routes.py: create_job),
   sarlavha/tavsif/kanal nomi asosida, arzon va tez. Bloklansa, job
   umuman yaratilmaydi.
2. Transkript bosqichi — transkripsiyadan keyin, dublaj (tarjima/TTS)
   boshlanishidan OLDIN (tasks.py: process_video), videoning haqiqiy
   nutqi asosida chuqurroq tekshiruv. Sarlavha zararsiz ko'ringan, lekin
   videoning o'zi siyosatga zid bo'lgan holatlarni shu yerda ushlaydi.

Standart zararli kontent (jinsiy, zo'ravonlik, o'z joniga qasd va h.k.)
OpenAI moderation endpoint orqali tekshiriladi. GapirAI'ning o'ziga xos
biznes siyosati (diniy kontent, terrorizm targ'iboti, noqonuniy faoliyat)
esa alohida GPT klassifikatori orqali — moderation endpoint bu
kategoriyalarni tanimaydi, chunki ular umumiy "zararli kontent" emas,
balki GapirAI'ning o'z biznes qarori.

Xizmat vaqtinchalik ishlamay qolsa (API xatosi, tarmoq muammosi) — FAIL
OPEN: video bloklanmaydi. Sabab: moderatsiya qo'shimcha xavfsizlik
qatlami, asosiy xizmat emas — vaqtinchalik OpenAI nosozligi butun
saytni to'xtatib qo'ymasligi kerak.
"""
from dataclasses import dataclass
import json
import logging

from openai import OpenAI

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=3)
    return _client


# category kodi -> admin panelda ko'rsatiladigan o'zbekcha nom
CATEGORY_LABELS: dict[str, str] = {
    "sexual_explicit": "Pornografik / 18+ kontent",
    "sexual_minors": "Voyaga yetmaganlar ishtirokidagi jinsiy kontent",
    "sexual_violence": "Zo'rlash yoki jinsiy zo'ravonlik",
    "terrorism_extremism": "Terroristik / ekstremistik targ'ibot",
    "graphic_violence": "Haddan tashqari grafik zo'ravonlik",
    "hate_violent_extremism": "Nafrat yoki zo'ravonlikni qo'zg'atish",
    "self_harm": "O'ziga zarar yetkazishni targ'ib qilish",
    "illegal_activity": "Noqonuniy faoliyatni targ'ib qilish/o'rgatish",
    "religious_content": "Diniy kontent",
    "policy_violation": "Kontent siyosatini buzish (aniqlanmagan toifa)",
}


@dataclass
class SafetyResult:
    allowed: bool
    category: str | None = None
    reason: str | None = None


def _moderation_check(text: str) -> SafetyResult:
    """OpenAI moderation endpoint — standart zararli kategoriyalar uchun
    (jinsiy, zo'ravonlik, o'z joniga qasd, nafrat).

    FAQAT bolalarga nisbatan jinsiy ekspluatatsiya (sexual_minors) qat'iy
    BLOKLANADI -- bu chegara biznes qaroriga bog'liq emas. Qolgan barcha
    kategoriyalar 2026-08-16'dan boshlab endi bloklamaydi, faqat
    OGOHLANTIRISH sifatida qayd etiladi (admin panelda ko'rish uchun) --
    sabab: soxta signal muammosi (masalan oddiy drama dialogi "harassment"
    deb belgilanishi) va foydalanuvchining aniq qarori."""
    client = _get_client()
    resp = client.moderations.create(model="omni-moderation-latest", input=text)
    result = resp.results[0]
    if not result.flagged:
        return SafetyResult(allowed=True)

    cats = result.categories
    if getattr(cats, "sexual_minors", False):
        return SafetyResult(False, "sexual_minors", "Voyaga yetmaganlar ishtirokidagi jinsiy kontent aniqlandi.")

    # Qolgan kategoriyalar -- endi faqat ogohlantirish, video bloklanmaydi.
    if getattr(cats, "sexual", False):
        return SafetyResult(True, "sexual_explicit", "Jinsiy (18+) kontent aniqlandi.")
    if getattr(cats, "violence_graphic", False):
        return SafetyResult(True, "graphic_violence", "Haddan tashqari grafik zo'ravonlik aniqlandi.")
    if getattr(cats, "hate_threatening", False) or getattr(cats, "harassment_threatening", False):
        return SafetyResult(True, "hate_violent_extremism", "Nafrat yoki zo'ravonlikni qo'zg'atuvchi kontent aniqlandi.")
    if getattr(cats, "self_harm", False):
        return SafetyResult(True, "self_harm", "O'ziga zarar yetkazishni targ'ib qiluvchi kontent aniqlandi.")
    return SafetyResult(allowed=True)


_POLICY_SYSTEM_PROMPT = (
    "Siz video kontent moderatori. Berilgan matn (sarlavha/tavsif/transkript) "
    "quyidagi kategoriyalardan biriga tegishlimi tekshiring:\n"
    "- religious_content: diniy kontent (targ'ibot, va'z, diniy ta'lim, diniy tarix hikoyasi)\n"
    "- terrorism_extremism: terroristik/ekstremistik targ'ibot, rekrutlash yoki ulug'lash\n"
    "- illegal_activity: aniq noqonuniy faoliyatni o'rgatish yoki targ'ib qilish\n\n"
    "Oddiy tarix, ilm-fan, texnologiya, biznes, sport, ta'lim, yangiliklar kontenti "
    "BLOKLANMAYDI — hatto diniy urush yoki jinoyat haqida BEZARARLI tarixiy/hujjatli "
    "tarzda gapirsa ham, agar bu targ'ibot yoki instruksiya bo'lmasa.\n\n"
    'Faqat shu JSON formatda javob bering: '
    '{"blocked": bool, "category": string yoki null, "reason": string yoki null}'
)


def _policy_classify(text: str) -> SafetyResult:
    """GapirAI'ning o'ziga xos biznes kategoriyalari uchun GPT klassifikatori."""
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.OPENAI_LIGHT_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _POLICY_SYSTEM_PROMPT},
            {"role": "user", "content": text[:6000]},
        ],
    )
    result = json.loads(response.choices[0].message.content)
    if result.get("blocked"):
        # Diniy/terrorizm/noqonuniy faoliyat -- endi faqat ogohlantirish,
        # bloklanmaydi (2026-08-16, foydalanuvchi qarori).
        return SafetyResult(True, result.get("category") or "policy_violation", result.get("reason") or "")
    return SafetyResult(allowed=True)


def check_safety(text: str) -> SafetyResult:
    """Matnni (metadata yoki transkript) ikkala tekshiruvdan ham o'tkazadi.
    Bo'sh matn yoki xizmat o'chirilgan bo'lsa — avtomatik ruxsat.

    Faqat sexual_minors (CSAM) hali ham allowed=False qaytaradi -- bu
    yagona qat'iy blok. Qolgan barcha topilgan kategoriyalar allowed=True
    bilan birga category/reason'ni ham qaytaradi (ogohlantirish, chaqiruvchi
    -- job_creation.py/tasks.py -- buni ContentViolation'ga blocked=False
    bilan yozib qo'yadi, lekin jarayonni to'xtatmaydi)."""
    if not settings.CONTENT_SAFETY_ENABLED or not text.strip():
        return SafetyResult(allowed=True)
    try:
        moderation_result = _moderation_check(text)
        if not moderation_result.allowed:
            return moderation_result  # faqat CSAM shu yerda to'xtaydi
        policy_result = _policy_classify(text)
        # Ikkalasi ham endi faqat ogohlantirish qaytaradi -- birinchi
        # topilgan ogohlantirish qaytariladi (moderatsiya ustuvor).
        if moderation_result.category:
            return moderation_result
        return policy_result
    except Exception as e:
        logger.error(f"Kontent xavfsizligi tekshiruvida xato (fail-open, bloklanmadi): {e}")
        return SafetyResult(allowed=True)
