"""Audio QA — sintez qilingan TTS audio'ni signal darajasida tekshiradi.

STT round-trip yondashuvi (Whisper orqali qayta transkripsiya qilib matn
mosligini solishtirish) real productionda ishonchli chiqmadi: OpenAI
Whisper API'ning "language" parametri "uz"ni rad etadi (400: "Language 'uz'
is not supported"), avtomatik til aniqlash esa qisqa (bir necha soniyalik)
dublyaj segmentlarida tez-tez boshqa tilga (turkcha/forscha/arabcha yozuvga)
chalkashib ketadi — ikkalasi ham 2026-08-12 productionda haqiqiy job orqali
tasdiqlangan. Natijada STT asosidagi QA hech qachon o'tmasdi, faqat har bir
segment uchun qo'shimcha Whisper chaqiruvi (xarajat) va foydasiz qayta
sintezga olib kelardi.

Shuning uchun QA transkripsiyaga muhtoj bo'lmasdan, to'g'ridan-to'g'ri audio
signalidan TTS'ning eng keng tarqalgan real nosozliklarini aniqlaydi: bo'sh/
sukut audio (sintez muvaffaqiyatsiz bo'lgan) va kutilganidan sezilarli
qisqaroq audio (kesilgan/to'xtab qolgan nutq).
"""
import json
import logging
import subprocess

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from backend.config import get_settings

logger = logging.getLogger(__name__)

_SILENCE_THRESH_DB = -40
_MIN_SILENCE_LEN_MS = 200
_MAX_SILENT_RATIO = 0.6  # audio'ning 60%+ jim bo'lsa -> "no_speech"
_MIN_DURATION_RATIO = 0.5  # audio kutilgan davomiylikning 50%idan kam bo'lsa -> "truncated"

# Yakuniy aralashma tekshiruvi (check_final_mix_quality) uchun.
_CLIP_PEAK_DBFS = -0.1  # shundan baland bo'lsa clipping xavfi
# Dub oynalari shundan PASTROQ bo'lsa "eshitilmayapti" deb belgilanadi.
# MUHIM: bu ORIGINAL fondan qancha baland ekanini emas — mutlaq darajani
# tekshiradi. Nisbiy taqqoslash (dub oynasi vs bo'sh oraliq) real testda
# yolg'on-musbat berdi: original trailer musiqasi tabiiy ravishda dialog
# vaqtida past, pauzalarda baland bo'lib turadi — bu ducking ishlaganidan
# emas, kontent dinamikasidan. To'g'ridan-to'g'ri ducking zanjiri (sidechain-
# compress) alohida tekshirilganda 8-15dB pasayish tasdiqlangan (2026-08-12).
_MIN_DUB_ABSOLUTE_DBFS = -35.0
_BACKGROUND_SILENCE_FLOOR_DBFS = -55.0  # fon shundan past bo'lsa "butunlay o'chirilgan" shubhasi


def check_audio_quality(audio_path: str, expected_text: str) -> dict:
    """
    Sintez qilingan audioni signal darajasida tekshiradi.

    Returns:
        {
            "score": float,            # 0.0-1.0, yuqori = yaxshiroq
            "flags": list[str],        # "no_speech" | "truncated"
            "duration_seconds": float,
            "silent_ratio": float,     # audio ichidagi jim qismning ulushi
        }
    """
    if not (expected_text or "").strip():
        return {"score": 1.0, "flags": [], "duration_seconds": 0.0, "silent_ratio": 0.0}

    try:
        audio = AudioSegment.from_wav(audio_path)
    except Exception as exc:
        logger.warning(f"Audio QA: audio faylni o'qishda xatolik: {exc}")
        return {"score": 0.0, "flags": ["no_speech"], "duration_seconds": 0.0, "silent_ratio": 1.0}

    duration_seconds = len(audio) / 1000.0
    if duration_seconds <= 0:
        return {"score": 0.0, "flags": ["no_speech"], "duration_seconds": 0.0, "silent_ratio": 1.0}

    nonsilent_ranges = detect_nonsilent(
        audio, min_silence_len=_MIN_SILENCE_LEN_MS, silence_thresh=_SILENCE_THRESH_DB
    )
    nonsilent_ms = sum(end - start for start, end in nonsilent_ranges)
    silent_ratio = round(1.0 - (nonsilent_ms / len(audio)), 3)

    flags = []
    if silent_ratio > _MAX_SILENT_RATIO:
        flags.append("no_speech")

    from backend.services.translator import estimate_duration_seconds
    expected_duration = estimate_duration_seconds(expected_text)
    duration_ratio = duration_seconds / expected_duration if expected_duration > 0 else 1.0
    if duration_ratio < _MIN_DURATION_RATIO:
        flags.append("truncated")

    if "no_speech" in flags:
        score = 0.0
    elif "truncated" in flags:
        score = max(0.0, round(duration_ratio / _MIN_DURATION_RATIO * 0.5, 3))
    else:
        score = round(min(1.0, 1.0 - max(0.0, silent_ratio - 0.1)), 3)

    return {
        "score": score,
        "flags": flags,
        "duration_seconds": round(duration_seconds, 3),
        "silent_ratio": silent_ratio,
    }


def _measure_loudness_range(video_path: str) -> float | None:
    """FFmpeg loudnorm'ning bir-o'tishli tahlil rejimidan LRA (loudness
    range, EBU R128) qiymatini oladi — yakuniy aralashmani qayta
    normallashtirmaydi, faqat backend/services/merger.py'dagi loudnorm
    natijasini tekshiradi."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-af", "loudnorm=print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=120,
        )
        # loudnorm JSON natijasi stderr'ga yoziladi (ffmpeg -f null chiqishi).
        stderr = result.stderr
        start = stderr.rfind("{")
        end = stderr.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(stderr[start:end + 1])
        return float(data.get("input_lra"))
    except Exception as exc:
        logger.warning(f"Final QA: loudness range o'lchashda xatolik: {exc}")
        return None


def check_final_mix_quality(
    video_path: str,
    actual_timings: list[dict] | None = None,
    audio_mix_mode: str | None = None,
) -> dict:
    """
    Yakuniy aralashtirilgan videoni (merger.py'ning natijasi) signal
    darajasida tekshiradi — STT'siz, xuddi check_audio_quality() kabi.

    Tekshiruvlar:
    - clipping: cho'qqi darajasi 0 dBFS'ga juda yaqinmi.
    - loudness range: EBU R128 LRA me'yoriy oraliqdami (juda tor — dinamika
      yo'q, "ezilgan"; juda keng — balandlik notekis).
    - dub eshitiladimi: actual_timings bo'yicha dub gapirayotgan oynalarning
      mutlaq darajasi juda past emasmi (aks holda dub mikslashda yo'qolib
      qolgan yoki umuman qo'shilmagan degani).
    - fon saqlanganmi: faqat ``AUDIO_MIX_MODE=ducked_mix`` rejimida dub
      orasidagi bo'sh joylar butunlay jim emasmi. ``dubbed_only`` rejimida
      original fon ataylab chiqariladi, shuning uchun bu tekshiruv o'tkazib
      yuboriladi.

    Ma'lum cheklov: bu funksiya faqat YAKUNIY (aralashtirilgan) audioni
    ko'radi, dub va original alohida-alohida emas — shuning uchun "dub juda
    baland fon ostida ko'milib qolgan" holatini ishonchli aniqlay olmaydi
    (buni aniqlash uchun ikkala trekni alohida saqlash kerak bo'lardi, bu
    hozircha ortiqcha murakkablik). Mutlaq past darajadagi (deyarli sukut)
    dub esa ishonchli aniqlanadi — bu eng jiddiy nosozlik holati.

    Returns:
        {
            "score": float,
            "flags": list[str],  # "clipping" | "loudness_out_of_range" |
                                  # "dub_not_audible" | "background_missing"
            "peak_dbfs": float,
            "loudness_lra": float | None,
            "dub_rms_dbfs": float | None,
            "background_rms_dbfs": float | None,
        }
    """
    try:
        audio = AudioSegment.from_file(video_path)
    except Exception as exc:
        logger.warning(f"Final QA: video audiosini o'qishda xatolik: {exc}")
        return {"score": 0.0, "flags": ["read_error"], "peak_dbfs": None,
                "loudness_lra": None, "dub_rms_dbfs": None, "background_rms_dbfs": None}

    flags = []
    peak_dbfs = audio.max_dBFS
    if peak_dbfs > _CLIP_PEAK_DBFS:
        flags.append("clipping")

    loudness_lra = _measure_loudness_range(video_path)
    if loudness_lra is not None and not (1.0 <= loudness_lra <= 20.0):
        flags.append("loudness_out_of_range")

    # Raqamli mutlaq sukunat (masalan original butunlay o'chirilgan) uchun
    # pydub .dBFS -inf qaytaradi — bu qiymatni chetlab o'tish ENG YOMON
    # holatni (fon butunlay yo'q) ko'rmas qilib qo'yardi, shuning uchun
    # -inf chetga chiqarilmaydi, past chegaraga qisqartiriladi (clamp).
    _SILENCE_FLOOR = -90.0

    dub_rms_values: list[float] = []
    bg_rms_values: list[float] = []
    if actual_timings:
        ordered = sorted(actual_timings, key=lambda s: s["start"])
        prev_end_ms = 0
        for seg in ordered:
            start_ms = max(0, int(seg["start"] * 1000))
            end_ms = min(len(audio), int(seg["end"] * 1000))
            if end_ms > start_ms:
                window = audio[start_ms:end_ms]
                if len(window) > 0:
                    level = window.dBFS
                    dub_rms_values.append(_SILENCE_FLOOR if level == float("-inf") else level)
            if start_ms - prev_end_ms > 500:
                gap = audio[prev_end_ms:start_ms]
                if len(gap) > 0:
                    level = gap.dBFS
                    bg_rms_values.append(_SILENCE_FLOOR if level == float("-inf") else level)
            prev_end_ms = max(prev_end_ms, end_ms)

    dub_rms = sum(dub_rms_values) / len(dub_rms_values) if dub_rms_values else None
    bg_rms = sum(bg_rms_values) / len(bg_rms_values) if bg_rms_values else None

    if dub_rms is not None and dub_rms < _MIN_DUB_ABSOLUTE_DBFS:
        flags.append("dub_not_audible")
    # In dubbed_only mode the original track is intentionally absent; treating
    # silent gaps as a failure would create a false warning for every job.
    mode = audio_mix_mode or get_settings().AUDIO_MIX_MODE
    if mode == "ducked_mix":
        if bg_rms is not None and bg_rms < _BACKGROUND_SILENCE_FLOOR_DBFS:
            flags.append("background_missing")
    else:
        bg_rms = None

    score = 1.0
    if "clipping" in flags:
        score -= 0.3
    if "loudness_out_of_range" in flags:
        score -= 0.2
    if "dub_not_audible" in flags:
        score -= 0.3
    if "background_missing" in flags:
        score -= 0.2
    score = max(0.0, round(score, 3))

    return {
        "score": score,
        "flags": flags,
        "peak_dbfs": round(peak_dbfs, 2) if peak_dbfs != float("-inf") else None,
        "loudness_lra": round(loudness_lra, 2) if loudness_lra is not None else None,
        "dub_rms_dbfs": round(dub_rms, 2) if dub_rms is not None else None,
        "background_rms_dbfs": round(bg_rms, 2) if bg_rms is not None else None,
    }
