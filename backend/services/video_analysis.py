"""
VideoAnalysisService — timestamped transkriptdan xulosa, asosiy fikrlar,
chapterlar, konspekt, test va savol-javob generatsiya qiladi.

Bitta servis, bitta transkript — har bir metod allaqachon olingan
transcript_segments'dan ishlaydi (backend.services.transcriber orqali),
hech qachon qayta transkripsiya qilmaydi. Barcha chaqiruvlar
OPENAI_LIGHT_MODEL (gpt-4o-mini) bilan, JSON rejimida ishlaydi.

Xavfsizlik qoidasi (bugungi tarjima segmentlari xatosidan saboq): LLM
javobidagi raqamli/strukturaviy maydonlar (timestamp, id, index) hech
qachon ko'r-ko'rona ishonib olinmaydi — har doim tekshiriladi va
noto'g'ri bo'lsa xavfsiz holatga tushiriladi, hech qachon butun
tahlilni qulatmaydi.
"""
import json
import logging

from openai import OpenAI

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
_client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=5) if settings.OPENAI_API_KEY else None

# Tahlil tili sifatida tanlanishi mumkin bo'lgan tillar + "Original" rejimida
# Whisper aniqlashi mumkin bo'lgan ko'proq tarqalgan video tillari uchun nomlar.
# Ro'yxatda yo'q kod uchun _language_rule xavfsiz holatda kodning o'zini ishlatadi.
LANGUAGE_NAMES = {
    "uz": "o'zbek",
    "en": "ingliz (English)",
    "ru": "rus (Русский)",
    "tr": "turk (Türkçe)",
    "kk": "qozoq (Қазақша)",
    "es": "ispan (Español)",
    "fr": "fransuz (Français)",
    "de": "nemis (Deutsch)",
    "ko": "koreys (한국어)",
    "ja": "yapon (日本語)",
    "zh": "xitoy (中文)",
    "ar": "arab (العربية)",
    "pt": "portugal (Português)",
    "it": "italyan (Italiano)",
    "hi": "hind (हिन्दी)",
}

# OpenAI Whisper API "language" maydonini to'liq ingliz nomi sifatida qaytaradi
# (masalan "english", "russian"), ISO kod emas. "Original" rejimi va tahlil
# tili tanlash ISO kodlarga (uz/en/ru/...) asoslangani uchun, transkripsiyadan
# keyin buni normalize_video_language() orqali kodga aylantiramiz.
_WHISPER_NAME_TO_CODE = {
    "uzbek": "uz", "english": "en", "russian": "ru", "turkish": "tr",
    "kazakh": "kk", "spanish": "es", "french": "fr", "german": "de",
    "korean": "ko", "japanese": "ja", "chinese": "zh", "arabic": "ar",
    "portuguese": "pt", "italian": "it", "hindi": "hi",
}


def normalize_video_language(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip().lower()
    return _WHISPER_NAME_TO_CODE.get(raw, raw)


def _language_rule(language: str) -> str:
    if language == "uz":
        return """Javobni TABIIY, so'zlashuv uslubidagi O'ZBEK tilida yozing — so'zma-so'z
tarjima qilmang. Texnik atamalarni (API, backend, frontend, database, server,
framework kabi va dasturlash tillari/kutubxona nomlari) original holida
qoldiring, ularni sun'iy o'zbekchalashtirmang."""
    name = LANGUAGE_NAMES.get(language, language)
    return f"""Javobni TABIIY, so'zlashuv uslubidagi "{name}" tilida yozing — so'zma-so'z,
sun'iy tarjima uslubida emas. Texnik atamalarni (API, backend, frontend,
database, server, framework kabi va dasturlash tillari/kutubxona nomlari)
original holida qoldiring."""

_NO_HALLUCINATION_RULE = """Faqat transkriptda HAQIQATAN aytilgan narsalarga asoslaning. Hech qachon
transkriptda yo'q ma'lumotni o'ylab topmang yoki taxmin qilmang."""


def _get_client() -> OpenAI:
    if not _client:
        raise RuntimeError("OPENAI_API_KEY not set")
    return _client


def _format_timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _format_transcript(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        ts = _format_timestamp(seg.get("start", 0))
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _call_json(system_prompt: str, user_message: str, max_attempts: int = 3) -> dict:
    """OpenAI'ga JSON-rejim so'rov, JSON parse xatosida qayta uriniladi
    (Gemini tarjimasida ko'p marta ko'rilgan "yaxshi javob, buzuq JSON"
    holatiga qarshi — bu yerda OpenAI JSON mode bilan kamdan-kam, lekin
    baribir himoya sifatida saqlanadi)."""
    last_err = None
    for attempt in range(max_attempts):
        try:
            response = _get_client().chat.completions.create(
                model=settings.OPENAI_LIGHT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.4,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as e:
            last_err = e
            logger.warning(f"VideoAnalysis JSON parse xatosi, qayta urinish {attempt + 1}/{max_attempts}: {e}")
    raise RuntimeError(f"JSON javobini o'qib bo'lmadi: {last_err}")


class VideoAnalysisService:
    def generate_summary(self, segments: list[dict], language: str = "uz") -> dict:
        """Returns {"short": str, "medium": str, "detailed": str}."""
        system = f"""Siz video transkriptlarini xulosalovchi mutaxassissiz.
{_NO_HALLUCINATION_RULE}
{_language_rule(language)}

Uchta xulosa formatida javob bering:
- "short": 2-5 jumlali juda qisqa xulosa
- "medium": bir necha paragrafda asosiy mazmun
- "detailed": videodagi barcha muhim fikrlarni tartibli tushuntiruvchi batafsil xulosa

JSON formatida qaytaring: {{"short": "...", "medium": "...", "detailed": "..."}}"""
        result = _call_json(system, _format_transcript(segments))
        return {
            "short": str(result.get("short", "")).strip(),
            "medium": str(result.get("medium", "")).strip(),
            "detailed": str(result.get("detailed", "")).strip(),
        }

    def generate_key_points(self, segments: list[dict], language: str = "uz") -> list[dict]:
        """Returns [{"title","description","timestamp"}]."""
        system = f"""Siz video transkriptidan asosiy fikrlarni ajratib oluvchi mutaxassissiz.
{_NO_HALLUCINATION_RULE}
{_language_rule(language)}

Videodagi eng muhim 5-10 ta fikrni aniqlang. Har biri uchun qisqa sarlavha,
tushuntirish va transkriptdagi eng yaqin soniya (timestamp, raqam) bering.

JSON formatida qaytaring:
{{"key_points": [{{"title": "...", "description": "...", "timestamp": 125}}, ...]}}"""
        result = _call_json(system, _format_transcript(segments))
        max_ts = max((_safe_float(s.get("end")) for s in segments), default=0.0)
        points = []
        for item in result.get("key_points", []) if isinstance(result, dict) else []:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            ts = _safe_float(item.get("timestamp"))
            points.append({
                "title": str(item["title"]).strip(),
                "description": str(item.get("description", "")).strip(),
                "timestamp": min(max(ts, 0.0), max_ts) if max_ts else 0.0,
            })
        return points

    def generate_chapters(self, segments: list[dict], video_duration: float, language: str = "uz") -> list[dict]:
        """Returns [{"title","start","end"}]."""
        system = f"""Siz video mazmunini mantiqiy chapterlarga ajratuvchi mutaxassissiz.
{_NO_HALLUCINATION_RULE}
{_language_rule(language)}

Video davomiyligi: {video_duration:.0f} soniya. Videoni 3-12 ta chapterga ajrating,
har biri qisqa sarlavha va boshlanish/tugash vaqti (soniyada) bilan. Chapterlar
0'dan video oxirigacha ketma-ket, bo'shliqsiz bo'lishi kerak.

JSON formatida qaytaring:
{{"chapters": [{{"title": "...", "start": 0, "end": 120}}, ...]}}"""
        result = _call_json(system, _format_transcript(segments))
        chapters = []
        for item in result.get("chapters", []) if isinstance(result, dict) else []:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            start = min(max(_safe_float(item.get("start")), 0.0), video_duration or 1e9)
            end = min(max(_safe_float(item.get("end"), start), start), video_duration or 1e9)
            chapters.append({"title": str(item["title"]).strip(), "start": start, "end": end})
        chapters.sort(key=lambda c: c["start"])
        return chapters

    def generate_notes(self, segments: list[dict], language: str = "uz") -> str:
        """Returns a structured markdown-style study conspectus (plain text)."""
        system = f"""Siz ta'lim videolaridan konspekt tuzuvchi mutaxassissiz.
{_NO_HALLUCINATION_RULE}
{_language_rule(language)}

Quyidagi tuzilishda konspekt yozing: mavzu sarlavhasi, so'ng raqamlangan
bo'limlar (asosiy tushunchalar, muhim fikrlar, misollar, xulosa). Markdown
formatida (## sarlavha, - ro'yxat) yozing.

JSON formatida qaytaring: {{"notes": "markdown matn"}}"""
        result = _call_json(system, _format_transcript(segments))
        return str(result.get("notes", "")).strip()

    def generate_quiz(self, segments: list[dict], language: str = "uz", num_questions: int = 10) -> list[dict]:
        """Returns [{"question","options","correct_answer","explanation","timestamp"}]."""
        system = f"""Siz video mazmuniga asoslangan test tuzuvchi mutaxassissiz.
{_NO_HALLUCINATION_RULE}
{_language_rule(language)}

{num_questions} ta ko'p tanlovli savol tuzing (har birida 4 ta variant). Savollar
faqat transkriptdagi ma'lumotlarga asoslangan bo'lsin, o'ylab topilgan
faktlar bo'lmasin.

JSON formatida qaytaring:
{{"questions": [{{"question": "...", "options": ["...", "...", "...", "..."],
"correct_answer": 0, "explanation": "...", "timestamp": 125}}, ...]}}
("correct_answer" — to'g'ri javobning options ro'yxatidagi indeksi, 0 dan boshlab.)"""
        result = _call_json(system, _format_transcript(segments))
        max_ts = max((_safe_float(s.get("end")) for s in segments), default=0.0)
        questions = []
        for item in result.get("questions", []) if isinstance(result, dict) else []:
            if not isinstance(item, dict) or not item.get("question"):
                continue
            options = item.get("options")
            if not isinstance(options, list) or len(options) < 2:
                continue
            options = [str(o) for o in options][:4]
            correct = item.get("correct_answer")
            correct = int(correct) if isinstance(correct, (int, float)) and 0 <= int(correct) < len(options) else 0
            ts = _safe_float(item.get("timestamp"))
            questions.append({
                "question": str(item["question"]).strip(),
                "options": options,
                "correct_answer": correct,
                "explanation": str(item.get("explanation", "")).strip(),
                "timestamp": min(max(ts, 0.0), max_ts) if max_ts else 0.0,
            })
        return questions

    def answer_question(
        self,
        segments: list[dict],
        question: str,
        qa_history: list[dict] | None = None,
    ) -> dict:
        """Returns {"answer": str, "timestamps": [float, ...]}.

        Javob tili "language" (tahlil tili) bilan emas, savolning o'zi qaysi
        tilda yozilgan bo'lsa o'sha til bilan belgilanadi — foydalanuvchi bir
        suhbat ichida tilni erkin almashtira olishi uchun (masalan o'zbekcha
        so'rab, keyin "Explain it in English" deb yozishi mumkin).
        """
        history_text = ""
        if qa_history:
            recent = qa_history[-3:]
            history_lines = [f"S: {qa['question']}\nJ: {qa['answer']}" for qa in recent if qa.get("question")]
            if history_lines:
                history_text = "\n\nOldingi savol-javoblar (kontekst uchun):\n" + "\n\n".join(history_lines)

        system = f"""Siz video haqida savollarga javob beruvchi yordamchisiz.
{_NO_HALLUCINATION_RULE}

MUHIM (til): Javobni foydalanuvchi SAVOLNI yozgan tilda bering — savol qaysi
tilda yozilgan bo'lsa, javob ham o'sha tilda bo'lsin (masalan savol inglizcha
bo'lsa, javob ham inglizcha; savol o'zbekcha bo'lsa, javob ham o'zbekcha).
Bu tahlilning umumiy tilidan mustaqil — foydalanuvchi savolni istalgan tilda
yozishi mumkin.

MUHIM: agar savolga javob transkriptda aniq topilmasa, foydalanuvchi savol
yozgan tilda, mazmunan "Bu ma'lumot videoda aniq tushuntirilmagan" deb javob
bering. Hech qachon transkriptda yo'q narsani "videoda aytilgan" deb ko'rsatmang.

Javobingiz bilan birga, javobga asos bo'lgan transkript qismlarining
soniyalardagi vaqtlarini (timestamps) ham bering.

JSON formatida qaytaring: {{"answer": "...", "timestamps": [125, 340]}}"""
        user_message = f"Transkript:\n{_format_transcript(segments)}{history_text}\n\nSavol: {question}"
        result = _call_json(system, user_message)
        max_ts = max((_safe_float(s.get("end")) for s in segments), default=0.0)
        timestamps = []
        for ts in result.get("timestamps", []) if isinstance(result, dict) else []:
            val = _safe_float(ts, -1)
            if 0 <= val <= (max_ts or 1e9):
                timestamps.append(val)
        return {
            "answer": str(result.get("answer", "")).strip() or "Bu ma'lumot videoda aniq tushuntirilmagan.",
            "timestamps": timestamps,
        }

    def generate_bilingual_segments(self, segments: list[dict], target_language: str) -> list[dict]:
        """Returns [{"start","end","original","translated"}] — Transkript tabidagi
        "Bilingual" ko'rinishi uchun: har bir gap original tilda va tanlangan
        tahlil tilida yonma-yon.

        Xom Whisper segmentlari juda qisqa/bo'lakli bo'lishi mumkin (dublyaj
        pipeline'idagi bilan bir xil muammo), shuning uchun avval to'liq
        gaplarga guruhlanadi (group_segments_into_sentences — synthesizer.py'dan
        qayta foydalanish, nusxa ko'chirilmagan).
        """
        from backend.services.synthesizer import group_segments_into_sentences

        grouped = group_segments_into_sentences(segments)
        if not grouped:
            return []

        numbered = "\n".join(f"{i + 1}. {g['text']}" for i, g in enumerate(grouped))
        system = f"""Siz video subtitrlarini tarjima qiluvchi mutaxassissiz.
{_language_rule(target_language)}

Quyida raqamlangan gaplar ro'yxati berilgan. Har birini alohida, kontekstga mos
tarjima qiling. Texnik atamalarni original holida qoldiring. Tarjimalar sonini
va tartibini o'zgartirmang — har bir raqamga bitta tarjima mos kelishi kerak.

JSON formatida qaytaring: {{"translations": ["1-tarjima", "2-tarjima", ...]}}"""
        result = _call_json(system, numbered)
        translations = result.get("translations") if isinstance(result, dict) else None
        translations = translations if isinstance(translations, list) else []

        bilingual = []
        for i, g in enumerate(grouped):
            translated = str(translations[i]).strip() if i < len(translations) and translations[i] else g["text"]
            bilingual.append({
                "start": _safe_float(g.get("start")),
                "end": _safe_float(g.get("end")),
                "original": g["text"],
                "translated": translated,
            })
        return bilingual
