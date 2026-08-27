"""
Speech Optimizer — translated Uzbek matnni Azure/Edge TTS uchun tayyorlaydi.

Ikki qatlam:
1. Qoidaviy (har doim, bepul): raqamlarni so'zga, qisqartmalarni og'zaki shaklga
   (PRONUNCIATION_DICT + PronunciationMemory) va URL'larni "havola"ga o'giradi.
2. LLM qatlami (faqat FREE_MODE o'chiq va OPENAI_API_KEY mavjud bo'lsa): uzun
   gaplarni bo'ladi, kitobiy iboralarni og'zaki nutqqa moslaydi, tinish
   belgilarini tabiiy pauzalarga qarab qo'yadi. Qatlam-1 natijasidagi
   raqam/qisqartma o'zgartirishlariga tegmaydi.

Natija faqat TTS kirishi uchun ishlatiladi — subtitr matni (uzbek_srt_content)
o'zgarishsiz, asl tarjimadan olinadi.
"""
import json
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

from backend.config import get_settings
from backend.models.database import SessionLocal, PronunciationMemory
from backend.services.speech_normalizer import normalize_apostrophes, _make_normalizer

logger = logging.getLogger(__name__)
settings = get_settings()
_client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=5) if settings.OPENAI_API_KEY else None


# ─────────────────────────────────────────────────────────────
# 1a. Talaffuz lug'ati (qisqartma/atama → og'zaki shakl)
# ─────────────────────────────────────────────────────────────
PRONUNCIATION_DICT: dict[str, str] = {
    "ChatGPT": "Chat Ji Pi Ti",
    "OpenAI": "Open Ey Ay",
    "PostgreSQL": "Postgres",
    "MongoDB": "Mongo Di Bi",
    "Next.js": "Nekst J S",
    "Node.js": "Nod J S",
    "GitHub": "GitHab",
    "HTTPS": "H T T P Es",
    "OAuth": "O Auth",
    "CI/CD": "Si Ay Si Di",
    "React": "Riakt",
    "Docker": "Dokker",
    "HTTP": "H T T P",
    "JSON": "Jeyson",
    "CRUD": "Krad",
    "HTML": "Eych Ti Em El",
    "REST": "Rest",
    "JWT": "Jey Vi Ti",
    "API": "Ey Pi Ay",
    "CSS": "Si Es Es",
    "SQL": "Es Kyu El",
    "XML": "Eks Em El",
    "Redis": "Redis",
    "Vue": "Vyu",
    "Git": "Git",
    "GPT": "Ji Pi Ti",
    "AI": "Ey Ay",
    "LLM": "El El Em",
    "CEO": "Si I Ou",
    "CTO": "Si Ti Ou",
    "URL": "Yu Ar El",
    "PDF": "Pi Di Ef",
    "USB": "Yu Es Bi",
    "VPN": "Vi Pi En",
}

# Uzunroq kalitlar avval tekshirilsin (masalan "GitHub" "Git"dan oldin).
_DICT_KEYS_BY_LENGTH = sorted(PRONUNCIATION_DICT.keys(), key=len, reverse=True)


def _load_memory_overrides() -> dict[str, str]:
    """PronunciationMemory jadvalidan o'rganilgan tuzatishlarni o'qiydi.

    Hozircha jadval bo'sh bo'ladi (yozish yo'li — round-trip QA — keyingi
    bosqichda qo'shiladi), lekin lookup boshidanoq mavjud bo'lishi kerak,
    shunda QA qatlami qo'shilganda optimizer interfeysi o'zgarmaydi.
    """
    db = SessionLocal()
    try:
        rows = db.query(PronunciationMemory).all()
        return {row.term: row.spoken_form for row in rows}
    except Exception as e:
        logger.warning(f"PronunciationMemory o'qishda xatolik (jadval hali yaratilmagan bo'lishi mumkin): {e}")
        return {}
    finally:
        db.close()


def _apply_pronunciation_dict(text: str, overrides: dict[str, str]) -> str:
    # PronunciationMemory statik lug'atni ustidan yozadi.
    merged = {**PRONUNCIATION_DICT, **overrides}
    keys_by_length = sorted(merged.keys(), key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in keys_by_length) + r")\b"
    ) if merged else None
    if not pattern:
        return text
    return pattern.sub(lambda m: merged[m.group(1)], text)


# ─────────────────────────────────────────────────────────────
# 1b. Raqamlarni o'zbekcha so'zga o'girish
# ─────────────────────────────────────────────────────────────
_UNITS = ["", "bir", "ikki", "uch", "toʻrt", "besh", "olti", "yetti", "sakkiz", "toʻqqiz"]
_TENS = ["", "oʻn", "yigirma", "oʻttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "toʻqson"]
_SCALES = ["", " ming", " million", " milliard", " trillion"]


def _three_digits_to_words(n: int) -> str:
    """0–999 oralig'idagi sonni so'zga o'giradi ('bir' hech qachon 'yuz'/'ming' oldidan qo'shilmaydi)."""
    if n == 0:
        return ""
    hundreds, rem = divmod(n, 100)
    tens, units = divmod(rem, 10)
    parts = []
    if hundreds:
        parts.append("yuz" if hundreds == 1 else f"{_UNITS[hundreds]} yuz")
    if tens:
        parts.append(_TENS[tens])
    if units:
        parts.append(_UNITS[units])
    return " ".join(parts)


def number_to_uzbek_words(n: int) -> str:
    """Butun sonni (manfiy bo'lishi mumkin) o'zbekcha so'zlarga o'giradi."""
    if n == 0:
        return "nol"
    sign = "minus " if n < 0 else ""
    n = abs(n)

    groups = []
    while n > 0:
        n, rem = divmod(n, 1000)
        groups.append(rem)

    if len(groups) > len(_SCALES):
        # Juda katta son — so'zga o'girishga urinmaymiz, raqam holicha qoldiramiz.
        return f"{sign}{n}"

    parts = []
    for i in reversed(range(len(groups))):
        group = groups[i]
        if group == 0:
            continue
        words = _three_digits_to_words(group)
        if i == 1 and group == 1:
            # "bir ming" emas, "ming"
            parts.append("ming")
        else:
            parts.append(f"{words}{_SCALES[i]}")

    return sign + " ".join(parts)


# Sana/yil/valyuta normalizatsiyasi — number_to_uzbek_words'ni tashqaridan
# oladi (speech_normalizer.py bilan aylanma import bo'lmasligi uchun).
_normalize_dates_and_currency = _make_normalizer(number_to_uzbek_words)


_PERCENT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s?%")
_HALF_DECIMAL_RE = re.compile(r"(-?\d+)[.,]5\b")
_DECIMAL_RE = re.compile(r"(-?\d+)[.,](\d+)")
_INTEGER_RE = re.compile(r"-?\d+")

# "6.3 million" -> 6 300 000 -> "olti million uch yuz ming" (nuqta o'qish emas)
_SCALE_VALUES = {"ming": 1_000, "million": 1_000_000, "milliard": 1_000_000_000, "trillion": 1_000_000_000_000}
_DECIMAL_SCALE_RE = re.compile(
    r"(-?\d+)[.,](\d+)\s?(ming|million|milliard|trillion)\b", re.IGNORECASE
)


def _convert_number_match(int_str: str) -> str:
    try:
        return number_to_uzbek_words(int(int_str))
    except ValueError:
        return int_str


def convert_numbers_in_text(text: str) -> str:
    """Foiz, kasr va butun sonlarni o'zbekcha so'zga o'giradi.

    Tartib muhim: foiz va kasrlar ("3.5", "100%") butun son regexidan oldin
    ishlanishi kerak, aks holda "3" va "5" alohida-alohida o'girilib ketadi.
    """
    def _decimal_scale_sub(m: re.Match) -> str:
        whole_str, frac_str, scale_word = m.group(1), m.group(2), m.group(3).lower()
        scale = _SCALE_VALUES[scale_word]
        whole = int(whole_str)
        frac_value = round(int(frac_str) * scale / (10 ** len(frac_str)))
        sign = -1 if whole < 0 else 1
        total = sign * (abs(whole) * scale + frac_value)
        return number_to_uzbek_words(total)

    # "6.3 million" kabi o'nlik+shkala birikmasi — foiz/oddiy kasr
    # qoidalaridan OLDIN ishlanishi kerak, aks holda "6.3" alohida
    # "olti nuqta uch" deb o'qilib, "million" so'zi orqada qolib ketadi.
    text = _DECIMAL_SCALE_RE.sub(_decimal_scale_sub, text)

    def _percent_sub(m: re.Match) -> str:
        num = m.group(1).replace(",", ".")
        if "." in num:
            whole, frac = num.split(".")
            if frac == "5":
                return f"{number_to_uzbek_words(int(whole))} yarim foiz"
            return f"{_convert_number_match(whole)} nuqta {' '.join(_UNITS[int(d)] or 'nol' for d in frac)} foiz"
        return f"{number_to_uzbek_words(int(num))} foiz"

    text = _PERCENT_RE.sub(_percent_sub, text)

    def _half_sub(m: re.Match) -> str:
        return f"{number_to_uzbek_words(int(m.group(1)))} yarim"

    text = _HALF_DECIMAL_RE.sub(_half_sub, text)

    def _decimal_sub(m: re.Match) -> str:
        whole, frac = m.group(1), m.group(2)
        frac_words = " ".join(_UNITS[int(d)] or "nol" for d in frac)
        return f"{number_to_uzbek_words(int(whole))} nuqta {frac_words}"

    text = _DECIMAL_RE.sub(_decimal_sub, text)

    text = _INTEGER_RE.sub(lambda m: _convert_number_match(m.group(0)), text)
    return text


# ─────────────────────────────────────────────────────────────
# 1c. URL'larni "havola"ga almashtirish
# ─────────────────────────────────────────────────────────────
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)


def _replace_urls(text: str) -> str:
    return _URL_RE.sub("havola", text)


def _rule_based_optimize(text: str, overrides: dict[str, str]) -> str:
    if not text or not text.strip():
        return text
    text = normalize_apostrophes(text)
    text = _replace_urls(text)
    text = _apply_pronunciation_dict(text, overrides)
    text = _normalize_dates_and_currency(text)
    text = convert_numbers_in_text(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ─────────────────────────────────────────────────────────────
# 2. LLM qatlami — tabiiy og'zaki nutqqa moslash (faqat pullik rejimda)
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Siz nutq matnini Microsoft Azure Speech (TTS) uchun tayyorlovchi mutaxassissiz.
Vazifangiz TARJIMA QILISH EMAS — matn allaqachon o'zbek tiliga tarjima qilingan.

QOIDALAR:
1. Ma'noni hech qachon o'zgartirmang: ma'lumot qo'shmang, olib tashlamang, misol o'ylab topmang.
2. Yozma/kitobiy uslubni og'zaki, tabiiy nutqqa aylantiring (professional lekin jonli).
3. 15-20 so'zdan uzun gaplarni bir necha qisqa gapga bo'ling.
4. Vergul va nuqtalarni notiq tabiiy pauza qiladigan joylarga qo'ying.
5. QUYIDAGILARGA HECH QACHON TEGMANG (allaqachon optimallashtirilgan):
   - Katta harflar bilan yozilgan talaffuz shakllari (masalan "Jey Vi Ti", "Ey Pi Ay")
   - So'z bilan yozilgan sonlar (masalan "ikki ming yigirma olti")
   - "havola" so'zi (URL o'rnida)
   - Ism, kompaniya, mahsulot va freymvork nomlari (masalan React, Docker, Kubernetes)
   - Vaqt belgilari (00:15, 01:32:18)
   - Kod bloklari

JSON formatida qaytaring. Faqat "text" maydonini qayta yozing, "id"/"start"/"end"ni o'zgartirmang."""


def _get_client() -> OpenAI:
    if not _client:
        raise RuntimeError("OPENAI_API_KEY not set")
    return _client


def _llm_optimize_chunk(segments: list[dict]) -> list[dict]:
    user_message = json.dumps(segments, ensure_ascii=True, indent=2)
    instruction = (
        "Quyidagi segmentlarni Azure TTS uchun og'zaki nutqqa moslang.\n"
        "JAVOB FORMATI — faqat shu ko'rinishda:\n"
        '{"segments": [{"id": ..., "start": ..., "end": ..., "text": "OPTIMALLASHTIRILGAN MATN"}, ...]}\n\n'
        f"{user_message}"
    )
    try:
        response = _get_client().chat.completions.create(
            model=settings.OPENAI_LIGHT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": instruction},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        optimized = result.get("segments") if isinstance(result, dict) else result
        if isinstance(optimized, list) and optimized and "text" in optimized[0]:
            # LLM 'id'/'start'/'end' ni tashlab qoldirishi yoki
            # o'zgartirishi mumkin — TTS bosqichida KeyError('id') bilan
            # butun jobni qulatmasligi uchun ular hech qachon modeldan
            # ishonib olinmaydi, faqat 'text' olinadi.
            if len(optimized) != len(segments):
                logger.warning(
                    f"LLM optimize segment soni mos kelmadi (original={len(segments)}, "
                    f"natija={len(optimized)}) — pozitsiya bo'yicha moslashtirilmoqda."
                )
            reconciled = []
            for i, orig in enumerate(segments):
                text = orig.get("text", "")
                if i < len(optimized) and isinstance(optimized[i], dict):
                    candidate = optimized[i].get("text")
                    if candidate:
                        text = candidate
                reconciled.append({**orig, "text": text})
            return reconciled
    except Exception as e:
        logger.warning(f"LLM speech optimization chunk failed, falling back to rule-based output only: {e}")
    return segments


def _llm_optimize(segments: list[dict]) -> list[dict]:
    if not segments:
        return []
    chunk_size = 30
    chunks = [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]
    if len(chunks) == 1:
        return _llm_optimize_chunk(chunks[0])
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(_llm_optimize_chunk, chunks))
    merged: list[dict] = []
    for r in results:
        merged.extend(r)
    return merged


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────
def optimize_segments(segments: list[dict]) -> list[dict]:
    """
    Tarjima qilingan segmentlarni TTS uchun optimallashtiradi.

    Natija faqat synthesizer.synthesize_segments() ga beriladi — subtitr
    matni bunga tegmaydi, chunki qisqartmalarning og'zaki yozilishi
    ("Jey Vi Ti") yozma subtitrda g'alati ko'rinadi.
    """
    if not segments:
        return []

    overrides = _load_memory_overrides()
    rule_based = [
        {**seg, "text": _rule_based_optimize(seg.get("text", ""), overrides)}
        for seg in segments
    ]

    if settings.FREE_MODE or not _client:
        logger.info("FREE_MODE (yoki OPENAI_API_KEY yo'q): faqat qoidaviy speech optimization qo'llanildi.")
        return rule_based

    logger.info("LLM speech optimization ishlamoqda...")
    optimized = _llm_optimize(rule_based)
    # LLM o'z chiqishida boshqa apostrof shaklini ishlatgan bo'lishi mumkin —
    # yakuniy o'tishda yana kanonik shaklga keltiramiz.
    return [{**seg, "text": normalize_apostrophes(seg.get("text", ""))} for seg in optimized]
