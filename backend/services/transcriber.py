import json
import os
import re
import subprocess
import tempfile
import time
import random
import threading
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI, RateLimitError
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=5) if settings.OPENAI_API_KEY else None
_CHUNK_DURATION_SECONDS = 8 * 60
_CHUNK_BITRATE = "64k"

# OpenAI'ning krediti tugaganda (insufficient_quota/credit_balance_exhausted)
# qayta urinish befoyda — darhol Gemini'ga (Vertex AI orqali) o'tish uchun
# aniqlanadi. Boshqa vaqtinchalik 429'lar odatdagidek qayta uriniladi.
_NO_RETRY_ERROR_MARKERS = ("insufficient_quota", "credit_balance_exhausted")

_gemini_local = threading.local()


# Ротация ключей при исчерпании бесплатной квоты (429 RESOURCE_EXHAUSTED).
# Каждый ключ имеет дневной лимит ~20 запросов/модель — при достижении
# лимита переключаемся на следующий (GEMINI_API_KEY_2/_3). Индекс — в
# thread-local, чтобы параллельные чанки не дрались за один индекс.
_gemini_key_idx = threading.local()


def _next_gemini_key() -> str:
    """Текущий ключ Gemini (индекс 0/1/2). При вызове после 429 вызывается
    инкремент через _rotate_gemini_key()."""
    keys = [
        settings.GEMINI_API_KEY,
        settings.GEMINI_API_KEY_2,
        settings.GEMINI_API_KEY_3,
    ]
    valid = [k for k in keys if k]
    if not valid:
        return ""
    idx = getattr(_gemini_key_idx, "idx", 0) % len(valid)
    return valid[idx]


def _rotate_gemini_key() -> None:
    """Переключить на следующий ключ (при 429) и сбросить кеш клиента."""
    keys = [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_2, settings.GEMINI_API_KEY_3]
    valid = [k for k in keys if k]
    if not valid:
        return
    cur = getattr(_gemini_key_idx, "idx", 0)
    _gemini_key_idx.idx = (cur + 1) % len(valid)
    # Старый клиент привязан к исчерпанному ключу — удаляем, следующий вызов создаст новый.
    if hasattr(_gemini_local, "client"):
        del _gemini_local.client
    logger.warning(f"Gemini 429: переключение на ключ #{((cur + 1) % len(valid)) + 1} из {len(valid)}")


def _get_gemini_transcribe_client():
    if not hasattr(_gemini_local, "client"):
        from google import genai

        if settings.GEMINI_USE_VERTEX:
            if settings.GOOGLE_APPLICATION_CREDENTIALS and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
            _gemini_local.client = genai.Client(
                vertexai=True,
                project=settings.GCP_PROJECT_ID,
                location=settings.GCP_LOCATION,
            )
        else:
            _gemini_local.client = genai.Client(api_key=_next_gemini_key())
    return _gemini_local.client

# Whisper faqat cholg'u ohangini "♪♪" yoki "[Music]"/"(applause)" kabi
# belgi bilan qaytarishi mumkin — bular haqiqiy nutq emas.
_NON_SPEECH_RE = re.compile(r"[♩-♯]|\[[^\]]*\]|\([^)]*\)")


def has_speech(segments: list[dict]) -> bool:
    """Segmentlar orasida kamida bitta haqiqiy nutq (so'z) bor-yo'qligini tekshiradi."""
    for seg in segments:
        if _NON_SPEECH_RE.sub("", seg.get("text", "")).strip():
            return True
    return False


def _get_client() -> OpenAI:
    if not client:
        raise RuntimeError("OPENAI_API_KEY not set")
    return client


def _chunk_audio(audio_path: str, chunk_dir: Path) -> list[Path]:
    output_pattern = chunk_dir / "chunk_%03d.mp3"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-i",
            audio_path,
            "-f",
            "segment",
            "-segment_time",
            str(_CHUNK_DURATION_SECONDS),
            "-reset_timestamps",
            "1",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            _CHUNK_BITRATE,
            str(output_pattern),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Audio bo'laklarga ajratishda xatolik: {proc.stderr[-500:]}")

    chunks = sorted(chunk_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("OpenAI transkripsiyasi uchun audio bo'laklari yaratilmadi.")
    return chunks


def _segment_to_dict(segment: object) -> dict:
    if hasattr(segment, "model_dump"):
        return segment.model_dump()
    if isinstance(segment, dict):
        return segment
    return {
        "start": getattr(segment, "start", None),
        "end": getattr(segment, "end", None),
        "text": getattr(segment, "text", ""),
    }


def _response_to_dict(response: object) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if isinstance(response, dict):
        return response
    return {
        "text": getattr(response, "text", ""),
        "language": getattr(response, "language", ""),
        "segments": getattr(response, "segments", []),
    }


def call_openai_with_retry(api_func, *args, **kwargs):
    max_attempts = 7
    for attempt in range(max_attempts):
        try:
            return api_func(*args, **kwargs)
        except RateLimitError as e:
            if any(marker in str(e) for marker in _NO_RETRY_ERROR_MARKERS):
                raise e
            if attempt == max_attempts - 1:
                raise e

            retry_after = 5.0
            try:
                if hasattr(e, "response") and e.response is not None:
                    headers = e.response.headers
                    if "retry-after-ms" in headers:
                        retry_after = float(headers["retry-after-ms"]) / 1000.0
                    elif "retry-after" in headers:
                        retry_after = float(headers["retry-after"])
            except Exception:
                pass
            
            backoff = (2 ** attempt) + random.uniform(0.1, 1.0)
            sleep_time = max(retry_after, backoff)
            logger.warning(f"OpenAI RateLimit (429) hit. Qayta urinish {sleep_time:.2f} soniyadan so'ng (Urinish {attempt + 1}/{max_attempts}). Xato: {e}")
            time.sleep(sleep_time)


def _bucket_words_into_segments(words: list[dict], segments: list[dict]) -> None:
    """OpenAI so'z darajasidagi timestamp'lar javobning yuqori darajasida
    (segmentlar ichida emas) qaytariladi — har bir so'zni o'z vaqt oralig'iga
    to'g'ri keladigan segmentga joylashtiradi (in-place, segments["words"])."""
    if not words or not segments:
        return
    for seg in segments:
        seg["words"] = []
    idx = 0
    for word in words:
        w_start = word.get("start")
        if w_start is None:
            continue
        while idx + 1 < len(segments) and w_start >= segments[idx + 1]["start"]:
            idx += 1
        # So'z segment oralig'idan chetga chiqib ketishi mumkin (masalan
        # chunk chegarasida) — eng yaqin segmentga baribir biriktiriladi,
        # tashlab yuborilmaydi.
        segments[idx]["words"].append({
            "word": word.get("word", ""),
            "start": round(float(w_start), 3),
            "end": round(float(word.get("end", w_start)), 3),
        })


def _transcribe_chunk(chunk_path: Path, offset_seconds: float, language: str | None = "en") -> tuple[list[dict], str, str]:
    # OpenAI'ning "language" parametri faqat cheklangan ISO-639-1 ro'yxatini
    # qabul qiladi — "uz" o'sha ro'yxatda YO'Q va 400 xato bilan rad etiladi
    # (2026-08-12 productionda tasdiqlangan). Shuning uchun qo'llab-
    # quvvatlanmagan/berilmagan til uchun bu parametr butunlay
    # yubormaydi — Whisper avtomatik aniqlaydi (Uzbek uchun ham ishlaydi,
    # faqat aniq "hint" sifatida berib bo'lmaydi).
    kwargs = {
        "file": None,
        "model": settings.OPENAI_TRANSCRIPTION_MODEL,
        "response_format": "verbose_json",
        "timestamp_granularities": ["segment", "word"],
    }
    if language:
        kwargs["language"] = language

    with chunk_path.open("rb") as audio_file:
        kwargs["file"] = audio_file
        response = call_openai_with_retry(
            _get_client().audio.transcriptions.create,
            **kwargs,
        )

    response_data = _response_to_dict(response)
    segments = []
    for segment in response_data.get("segments", []):
        segment_data = _segment_to_dict(segment)
        text = (segment_data.get("text") or "").strip()
        start = segment_data.get("start")
        end = segment_data.get("end")
        if not text or start is None or end is None:
            continue
        segments.append(
            {
                "start": round(float(start) + offset_seconds, 3),
                "end": round(float(end) + offset_seconds, 3),
                "text": text,
            }
        )

    # "word" granularity so'ralganda javob top-level "words" ro'yxatini ham
    # qaytaradi (segmentlar ichida emas) — offset qo'shib, tegishli
    # segmentlarga taqsimlanadi.
    raw_words = response_data.get("words") or []
    if raw_words and segments:
        offset_words = []
        for w in raw_words:
            w_dict = w if isinstance(w, dict) else _segment_to_dict(w)
            offset_words.append({
                "word": w_dict.get("word", ""),
                "start": w_dict.get("start", 0) + offset_seconds,
                "end": w_dict.get("end", 0) + offset_seconds,
            })
        _bucket_words_into_segments(offset_words, segments)

    return (
        segments,
        (response_data.get("text") or "").strip(),
        response_data.get("language") or "en",
    )


_TRANSCRIBE_LANGUAGE_NAMES = {"en": "English", "uz": "Uzbek"}


def _build_transcribe_prompt(language: str | None) -> str:
    lang_name = _TRANSCRIBE_LANGUAGE_NAMES.get(language, language) if language else "whatever language is spoken"
    return (
        f"Transcribe this audio clip verbatim in {lang_name}, exactly as spoken. "
        "Split the transcription into short natural subtitle-style segments "
        "(roughly one sentence or clause each). For each segment, give its "
        "start and end time in seconds, measured from the very start of THIS "
        "audio clip (0.0 = beginning of the clip). Silent/music-only clips "
        "should return an empty segments list.\n\n"
        'Respond with ONLY this JSON shape, no other text:\n'
        '{"segments": [{"start": 0.0, "end": 2.4, "text": "..."}, ...]}'
    )


def _transcribe_chunk_gemini(chunk_path: Path, offset_seconds: float, language: str | None = "en") -> tuple[list[dict], str, str]:
    """OpenAI muqobili sifatida — Vertex AI orqali Gemini bilan transkripsiya.
    Whisper'ning audio-alignment aniqligiga teng emas, lekin OpenAI krediti
    tugagan holatlarda navbatni to'xtatib qo'ymaslik uchun yetarli."""
    from google.genai import types

    audio_bytes = chunk_path.read_bytes()
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
    )
    contents = [
        types.Part.from_bytes(data=audio_bytes, mime_type="audio/mpeg"),
        _build_transcribe_prompt(language),
    ]

    # Barcha Gemini kalitlari soni — agar hammasi 429 bo'lsa, darhol tashlaymiz
    keys = [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_2, settings.GEMINI_API_KEY_3]
    total_keys = len([k for k in keys if k])
    max_attempts = min(5, total_keys + 1)  # kalitlar sonidan ko'p retry qilmaymiz
    keys_exhausted = 0

    for attempt in range(max_attempts):
        try:
            response = _get_gemini_transcribe_client().models.generate_content(
                model=settings.GEMINI_VERTEX_TEXT_MODEL,
                contents=contents,
                config=config,
            )
            result = json.loads(response.text)
            raw_segments = result.get("segments", []) if isinstance(result, dict) else result

            segments = []
            text_parts = []
            for seg in raw_segments or []:
                text = (seg.get("text") or "").strip()
                start = seg.get("start")
                end = seg.get("end")
                if not text or start is None or end is None:
                    continue
                text_parts.append(text)
                segments.append({
                    "start": round(float(start) + offset_seconds, 3),
                    "end": round(float(end) + offset_seconds, 3),
                    "text": text,
                })
            return segments, " ".join(text_parts), language
        except Exception as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            is_bad_json = isinstance(e, json.JSONDecodeError)
            if attempt == max_attempts - 1 or not (is_rate_limit or is_bad_json):
                raise
            if is_rate_limit:
                keys_exhausted += 1
                # Agar barcha kalitlar ishlatilgan — darhol tashlaymiz (200s kutmaslik)
                if keys_exhausted >= total_keys:
                    logger.warning(f"Gemini: barcha {total_keys} kalitlar ishlatildi (429) — faster-whisper ga o'tilmoqda")
                    raise
                _rotate_gemini_key()
            backoff = (2 ** attempt) + random.uniform(0.1, 1.0) if is_rate_limit else random.uniform(0.3, 1.2)
            logger.warning(f"Gemini transkripsiya xato — qayta urinish {backoff:.2f}s ({attempt + 1}/{max_attempts}): {e}")
            time.sleep(backoff)
    return [], "", language


def transcribe_audio(audio_path: str, language: str | None = "en") -> dict:
    """
    Audio faylni matnga aylantirish (STT).

    language: audio'da qaysi til gapirilishi kutilmoqda ("en" — original
    video, dublyaj pipeline'ining standart holati; "uz" — dublyaj qilingan
    audio'ni QA orqali qayta tekshirishda, backend/services/audio_qa.py).
    Bu OpenAI/Gemini'ga qaysi tilni tinglashini aytadi — noto'g'ri til
    berilsa, masalan o'zbekcha audio "en" bilan so'ralsa, Whisper uni
    inglizchaga zo'rlab talqin qilib, butunlay boshqa (yaroqsiz) matn
    qaytaradi (2026-08-12 productionda tasdiqlangan xato).
    Returns:
        dict: {
            "text": str,           # To'liq matn
            "segments": list,      # Vaqt belgilangan segmentlar
            "srt": str,            # SRT format subtitles
            "language": str,       # Aniqlangan til
        }
    """
    if settings.FREE_MODE:
        try:
            from faster_whisper import WhisperModel
            _model_name = settings.WHISPER_MODEL
            logger.info(f"FREE_MODE: Running local faster-whisper transcription ({_model_name} model on CPU)...")

            model = WhisperModel(_model_name, device="cpu", compute_type="int8")
            segments, info = model.transcribe(audio_path, beam_size=5, language=language)
            
            segments_list = []
            full_text_parts = []
            for i, segment in enumerate(segments, start=1):
                text = segment.text.strip()
                if not text:
                    continue
                full_text_parts.append(text)
                segments_list.append({
                    "id": i,
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "text": text
                })
                
            srt_lines = []
            for seg in segments_list:
                srt_lines.append(str(seg["id"]))
                srt_lines.append(f"{_format_time(seg['start'])} --> {_format_time(seg['end'])}")
                srt_lines.append(seg["text"])
                srt_lines.append("")
                
            return {
                "text": " ".join(full_text_parts),
                "segments": segments_list,
                "srt": "\n".join(srt_lines),
                "language": info.language,
            }
        except Exception as e:
            logger.error(f"Local faster-whisper transcription failed: {e}. Falling back to OpenAI...")

    segments_list = []
    full_text_parts = []
    detected_language = language

    def _transcribe_chunk_with_fallback(cpath: Path, offset: float) -> tuple[list[dict], str, str]:
        # Fallback chain: OpenAI → Gemini → faster-whisper (local)
        try:
            return _transcribe_chunk(cpath, offset_seconds=offset, language=language)
        except Exception as e:
            logger.warning(f"OpenAI transkripsiya muvaffaqiyatsiz ({e}) — Gemini'ga o'tilmoqda.")
        try:
            if settings.GEMINI_API_KEY or settings.GEMINI_USE_VERTEX:
                return _transcribe_chunk_gemini(cpath, offset_seconds=offset, language=language)
        except Exception as e:
            logger.warning(f"Gemini transkripsiya ham muvaffaqiyatsiz ({e}) — faster-whisper ga o'tilmoqda.")
        # Final fallback: local faster-whisper (bepul, API kerak emas)
        try:
            from faster_whisper import WhisperModel
            _model_name = settings.WHISPER_MODEL
            logger.info(f"faster-whisper: local transkripsiya ishlatilmoqda ({_model_name})...")
            model = WhisperModel(_model_name, device="cpu", compute_type="int8")
            segments_iter, info = model.transcribe(str(cpath), beam_size=5, language=language)
            segments = []
            text_parts = []
            for seg in segments_iter:
                text = seg.text.strip()
                if not text:
                    continue
                text_parts.append(text)
                segments.append({
                    "start": round(float(seg.start) + offset, 3),
                    "end": round(float(seg.end) + offset, 3),
                    "text": text,
                })
            return segments, " ".join(text_parts), info.language or language or "en"
        except Exception as e2:
            logger.error(f"faster-whisper ham muvaffaqiyatsiz ({e2}) — barcha transkripsiya provayderlari tugadi.")
            raise RuntimeError(f"Barcha transkripsiya provayderlari ishlamadi: OpenAI, Gemini, faster-whisper")

    with tempfile.TemporaryDirectory(prefix="openai-stt-") as temp_dir:
        chunk_paths = _chunk_audio(audio_path, Path(temp_dir))

        if len(chunk_paths) == 1:
            chunk_results = [
                (0, _transcribe_chunk_with_fallback(chunk_paths[0], 0))
            ]
        else:
            def _process_chunk(args):
                idx, cpath = args
                return idx, _transcribe_chunk_with_fallback(cpath, idx * _CHUNK_DURATION_SECONDS)

            with ThreadPoolExecutor(max_workers=min(len(chunk_paths), 4)) as executor:
                chunk_results = list(executor.map(_process_chunk, enumerate(chunk_paths)))

        chunk_results.sort(key=lambda x: x[0])
        for _, (chunk_segments, chunk_text, chunk_language) in chunk_results:
            if chunk_text:
                full_text_parts.append(chunk_text)
            if chunk_segments:
                segments_list.extend(chunk_segments)
            if chunk_language:
                detected_language = chunk_language

    srt_lines = []
    for i, seg in enumerate(segments_list, start=1):
        seg["id"] = i

        # SRT format
        srt_lines.append(str(i))
        srt_lines.append(f"{_format_time(seg['start'])} --> {_format_time(seg['end'])}")
        srt_lines.append(seg["text"])
        srt_lines.append("")

    return {
        "text": " ".join(full_text_parts),
        "segments": segments_list,
        "srt": "\n".join(srt_lines),
        "language": detected_language,
    }


def _format_time(seconds: float) -> str:
    """Sekundni SRT vaqt formatiga aylantirish: 00:01:23,456"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
