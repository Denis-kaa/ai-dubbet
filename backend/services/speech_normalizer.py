"""
Uzbek Speech Normalizer — TTS'ga yuborishdan oldin matnni standartlashtiradi.

speech_optimizer.py'dagi qoidaviy raqam-so'zga o'girish yetarli emas edi:
"1947-yil" kabi sanalar kardinal ("bir ming to'qqiz yuz qirq yetti") emas,
ORDINAL ("ming to'qqiz yuz qirq yettinchi yil") shaklda o'qilishi kerak.
Bundan tashqari, tarjima manbasi (GPT/Whisper) turli apostrof belgilarini
(', ', ', `) aralash ishlatadi — bu TTS talaffuzini beqaror qiladi.

Pipeline tartibi (speech_optimizer._rule_based_optimize ichida chaqiriladi):
  apostrof normalizatsiya -> valyuta -> sana -> yil -> minglik ajratkichi
  -> (keyin speech_optimizer'ning mavjud kardinal-son konvertori)
"""
import re

# ─────────────────────────────────────────────────────────────
# 1. Apostrof normalizatsiyasi
# ─────────────────────────────────────────────────────────────
# O'zbek lotin yozuvida ikkita alohida belgi bor:
#   ʻ (U+02BB) — faqat "o"/"g" dan keyin, oʻ/gʻ digrafini hosil qiladi
#   ʼ (U+02BC) — "tutuq belgisi", boshqa harflardan keyin (ma'no, san'at, e'lon)
# Manba matnda bular ko'pincha oddiy ' yoki ' bilan aralashtirilgan bo'ladi —
# buni farqlab, to'g'ri belgiga o'giramiz.
_APOSTROPHE_VARIANTS = "'\u2019\u2018\u0060\u00b4"
_APOSTROPHE_CLASS = "[" + re.escape(_APOSTROPHE_VARIANTS) + "]"

_OG_APOSTROPHE_RE = re.compile(rf"([oOgG]){_APOSTROPHE_CLASS}")
_OTHER_APOSTROPHE_RE = re.compile(_APOSTROPHE_CLASS)


def normalize_apostrophes(text: str) -> str:
    """Barcha apostrof variantlarini kanonik oʻ/gʻ (U+02BB) yoki tutuq
    belgisi ʼ (U+02BC) ga o'giradi."""
    if not text:
        return text
    text = _OG_APOSTROPHE_RE.sub("\\1\u02bb", text)
    text = _OTHER_APOSTROPHE_RE.sub("\u02bc", text)
    return text


# ─────────────────────────────────────────────────────────────
# 2. Kardinal -> ordinal son (raqam so'zlariga import qilinadi)
# ─────────────────────────────────────────────────────────────
_UZ_VOWELS = set("aeiouAEIOU")


def _ordinalize_last_word(cardinal_words: str) -> str:
    """Kardinal son so'zining oxirgi bo'lagiga ordinal qo'shimcha qo'shadi.

    Qoida: oxirgi harf unli bo'lsa -> "nchi", undosh bo'lsa -> "inchi".
    (yigirma->yigirmanchi, olti->oltinchi, lekin o'n->o'ninchi, besh->beshinchi)
    """
    words = cardinal_words.rsplit(" ", 1)
    last = words[-1]
    if not last:
        return cardinal_words
    suffix = "nchi" if last[-1] in _UZ_VOWELS else "inchi"
    words[-1] = last + suffix
    return " ".join(words)


# ─────────────────────────────────────────────────────────────
# 3. Sana / yil naqshlari
# ─────────────────────────────────────────────────────────────
_UZ_MONTHS = {
    1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel", 5: "may", 6: "iyun",
    7: "iyul", 8: "avgust", 9: "sentyabr", 10: "oktyabr", 11: "noyabr", 12: "dekabr",
}

_YEAR_RE = re.compile(r"\b(\d{3,4})[-\s](yil\w*|y\.)")
_NUMERIC_DATE_DMY_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")  # DD.MM.YYYY
_NUMERIC_DATE_YMD_RE = re.compile(r"\b(\d{4})[./](\d{1,2})[./](\d{1,2})\b")  # YYYY/MM/DD
_MONTH_NAMES_PATTERN = "|".join(_UZ_MONTHS.values())
_DAY_BEFORE_MONTH_RE = re.compile(rf"\b(\d{{1,2}})[-\s](?={_MONTH_NAMES_PATTERN}\b)")

# Valyuta / minglik ajratkichlari
_DOLLAR_RE = re.compile(r"\$\s?(\d[\d,\.\s]*\d|\d)")
_THOUSANDS_COMMA_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")
_THOUSANDS_SPACE_RE = re.compile(r"\b\d{1,3}(?:\s\d{3})+\b")


def _make_normalizer(number_to_words):
    """number_to_uzbek_words funksiyasini tashqaridan oladi (speech_optimizer
    bilan aylanma import bo'lmasligi uchun)."""

    def _ordinal_words(n: int) -> str:
        return _ordinalize_last_word(number_to_words(n))

    def _year_sub(m: re.Match) -> str:
        num = int(m.group(1))
        suffix_word = m.group(2)
        if suffix_word == "y.":
            suffix_word = "yil"
        return f"{_ordinal_words(num)} {suffix_word}"

    def _numeric_date_dmy_sub(m: re.Match) -> str:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return m.group(0)
        return f"{_ordinal_words(day)} {_UZ_MONTHS[month]}, {_ordinal_words(year)} yil"

    def _numeric_date_ymd_sub(m: re.Match) -> str:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return m.group(0)
        return f"{_ordinal_words(day)} {_UZ_MONTHS[month]}, {_ordinal_words(year)} yil"

    def _day_before_month_sub(m: re.Match) -> str:
        return _ordinal_words(int(m.group(1))) + " "

    def _dollar_sub(m: re.Match) -> str:
        raw = m.group(1).replace(",", "").replace(" ", "")
        try:
            n = int(float(raw))
        except ValueError:
            return m.group(0)
        return f"{number_to_words(n)} dollar"

    def normalize(text: str) -> str:
        if not text or not text.strip():
            return text
        # Sana/valyuta naqshlari umumiy butun-son konvertoridan OLDIN ishlanishi
        # kerak — aks holda "2026" alohida-alohida raqam sifatida o'girilib
        # ketadi.
        text = _DOLLAR_RE.sub(_dollar_sub, text)
        text = _NUMERIC_DATE_DMY_RE.sub(_numeric_date_dmy_sub, text)
        text = _NUMERIC_DATE_YMD_RE.sub(_numeric_date_ymd_sub, text)
        text = _DAY_BEFORE_MONTH_RE.sub(_day_before_month_sub, text)
        text = _YEAR_RE.sub(_year_sub, text)
        # Qolgan ko'p xonali sonlardagi minglik ajratkichlarini olib tashlash
        # (masalan "1,500,000 so'm" -> "1500000 so'm"), keyingi bosqichda
        # kardinal so'zga o'giriladi.
        text = _THOUSANDS_COMMA_RE.sub(lambda m: m.group(0).replace(",", ""), text)
        text = _THOUSANDS_SPACE_RE.sub(lambda m: m.group(0).replace(" ", ""), text)
        return text

    return normalize
