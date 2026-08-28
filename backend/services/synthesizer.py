import os
import re
import subprocess
import tempfile
import time
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pydub import AudioSegment
from backend.config import get_settings
from backend.services.tts.factory import get_provider, get_fallback_provider
from backend.services.tts.base import PermanentTTSError
from backend.services.tts_cost import log_tts_usage

logger = logging.getLogger(__name__)
settings = get_settings()

_FRAME_RATE = 24000

# ─────────────────────────────────────────────────────────────
# Segmentlarni TABIIY gapga qayta guruhlash
# ─────────────────────────────────────────────────────────────
# Whisper segmentlari nutqdagi PAUZALARGA qarab kesilgan, grammatik gap
# chegarasiga emas — bitta tugal fikr ko'pincha 2-3 bo'lakka bo'linib
# qoladi. Bu esa faqat TTS'da emas, ANDOZA (tarjima, nutq optimallash)
# bosqichlarida ham muammo: LLM har bir bo'lakni ALOHIDA qayta yozadi va
# ko'pincha oxiriga soxta nuqta qo'shib, uni "tugal gap"dek ko'rsatadi
# (masalan "Bugun." / "Qanday qilib u.") — bu keyingi bosqichlarni ham
# aldab qo'yadi. Shuning uchun bu funksiya TARJIMADAN OLDIN, xom
# transkripsiya ustida ishlatiladi (tasks.py) — TTS bosqichida yana
# xavfsizlik to'ri sifatida qayta chaqiriladi (nutq optimallash o'zi
# ham uzun gaplarni qayta bo'lib qo'yishi mumkin).
_GROUP_MAX_GAP_S = 0.6
_GROUP_MAX_WORDS = 30
_GROUP_MAX_SPAN_S = 12.0
_SENTENCE_END_RE = re.compile(r"[.!?…]\s*$")


def group_segments_into_sentences(segments: list[dict]) -> list[dict]:
    groups: list[dict] = []
    current: dict | None = None

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue

        if current is None:
            current = {**seg, "text": text}
            continue

        gap = seg["start"] - current["end"]
        combined_text = f"{current['text']} {text}"
        prev_ends_sentence = bool(_SENTENCE_END_RE.search(current["text"]))

        can_merge = (
            not prev_ends_sentence
            and gap <= _GROUP_MAX_GAP_S
            and len(combined_text.split()) <= _GROUP_MAX_WORDS
            and (seg["end"] - current["start"]) <= _GROUP_MAX_SPAN_S
        )

        if can_merge:
            current["text"] = combined_text
            current["end"] = seg["end"]
        else:
            groups.append(current)
            current = {**seg, "text": text}

    if current:
        groups.append(current)

    return groups


def _synthesize_text(
    text: str,
    output_path: str,
    voice_name: str | None = None,
    video_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """
    Matnni audioga aylantiradi.

    Qatlam 1 — TTS_PROVIDER (default: ElevenLabs).
    Qatlam 2 — TTS_FALLBACK_PROVIDER (default: Edge, bepul) — faqat VAQTINCHALIK
    xatolikda (timeout/429/5xx). Provider PermanentTTSError ko'tarsa (noto'g'ri
    API kalit, yaroqsiz matn) fallbackka urinilmaydi — sabab hal qilinmaguncha
    fallback ham xuddi shu sababdan ishlamaydi.

    Qaytaradi: ovozni haqiqatda sintez qilgan provider nomi — dublyajda faqat
    bitta ovoz eshitilishini ta'minlash uchun synthesize_segments() bu qiymatni
    kuzatib boradi.
    """
    # Kesh faqat SHU YERDA o'qiladi (get_cached) — yozish (store_cached) esa
    # synthesize_segments()'da, QA o'tgandan KEYIN amalga oshiriladi. Agar
    # bu yerda darhol yozilsa, QA muvaffaqiyatsiz bo'lib ICHKI qayta urinish
    # xuddi shu matn/ovoz/provider bilan qayta chaqirilganda, keshdan AYNAN
    # O'SHA yaroqsiz audio qaytib kelardi — qayta urinish ma'nosiz bo'lardi.
    from backend.services.tts_cache import get_cached

    if settings.FREE_MODE:
        logger.info("FREE_MODE: Edge TTS (bepul) ishlatilmoqda...")
        fallback = get_fallback_provider()
        if fallback.synthesize(text, output_path, voice_name=voice_name):
            log_tts_usage(fallback, text, output_path, video_id=video_id, user_id=user_id)
            return fallback.name
        raise RuntimeError("FREE_MODE: Edge TTS muvaffaqiyatsiz.")

    # --- Asosiy provider ---
    primary = get_provider()

    # Kesh: bir xil matn+ovoz+provider oldin sintez qilingan bo'lsa, qayta
    # pul to'lamasdan S3'dan qaytariladi (backend/services/tts_cache.py).
    if get_cached(text, voice_name, primary.name, output_path):
        log_tts_usage(primary, text, output_path, video_id=video_id, user_id=user_id, cache_hit=True)
        return primary.name

    logger.info(f"TTS provider: {primary.name} | chars={len(text)}")

    try:
        if primary.synthesize(text, output_path, voice_name=voice_name):
            log_tts_usage(primary, text, output_path, video_id=video_id, user_id=user_id)
            return primary.name
    except PermanentTTSError as exc:
        logger.error(f"{primary.name} TTS doimiy xatolik — fallbackka urinilmaydi: {exc}")
        raise RuntimeError(f"{primary.name} TTS doimiy xatolik: {exc}") from exc

    logger.warning(f"{primary.name} TTS muvaffaqiyatsiz — fallback {settings.TTS_FALLBACK_PROVIDER} ga o'tilmoqda.")

    # --- Fallback: vaqtinchalik xatoliklar uchun ---
    if settings.ELEVENLABS_FALLBACK_TO_EDGE:
        fallback = get_fallback_provider()
        if get_cached(text, voice_name, fallback.name, output_path):
            log_tts_usage(fallback, text, output_path, video_id=video_id, user_id=user_id, cache_hit=True)
            return fallback.name
        try:
            if fallback.synthesize(text, output_path, voice_name=voice_name):
                log_tts_usage(fallback, text, output_path, video_id=video_id, user_id=user_id)
                return fallback.name
        except PermanentTTSError as exc:
            logger.error(f"{fallback.name} fallback ham doimiy xatolik: {exc}")

    raise RuntimeError(f"Barcha TTS providerlari muvaffaqiyatsiz: '{text[:50]}...'")


def _speedup_audio(audio: AudioSegment, factor: float) -> AudioSegment:
    """FFmpeg atempo filter bilan audio tezlashtirish (pitch va namuna chastotasi o'zgarmaydi, toza ovoz saqlanadi)."""
    factor = max(0.5, min(2.0, round(factor, 3)))
    in_fd, in_path = tempfile.mkstemp(suffix=".wav")
    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(in_fd); os.close(out_fd)
    try:
        audio.export(in_path, format="wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", in_path, "-filter:a", f"atempo={factor},volume=0.95", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", out_path],
            check=True, capture_output=True,
        )
        return AudioSegment.from_wav(out_path)
    finally:
        if os.path.exists(in_path):
            try: os.unlink(in_path)
            except Exception: pass
        if os.path.exists(out_path):
            try: os.unlink(out_path)
            except Exception: pass


def synthesize_segments(
    segments: list[dict],
    output_dir: str,
    voice_name: str | None = None,
    video_id: str | None = None,
    user_id: str | None = None,
    existing_qa: dict | None = None,
) -> tuple[str, list[dict], dict]:
    """
    Har bir segmentni to'liq matn bilan ovozga aylantirish.

    Sinxronizatsiya va sifat strategiyasi:
    - HECH QACHON gap / matn oxiridan kesib tashlanmaydi!
    - Har bir audio segment headroom normalizatsiyadan o'tkaziladi (shirillash to'liq yo'qotiladi).
    - Kerak bo'lsa biroz mo''tadil tezlashtiriladi (max 1.45x) yoki (qisqa
      bo'lsa) sekinlashtiriladi.
    - Hali ham yetmasa, keyingi segment boshlanishi keyinroqqa suriladi (gap to'liq tugaydi).

    existing_qa: oldingi Celery urinishidan segment_qa checkpoint'i
    (backend/models/database.py: DubbingJob.segment_qa) — {seg_id: {"score",
    "flags", "attempts"}}. Allaqachon o'tgan segmentlar qayta QA qilinmaydi
    (audio esa TTS keshi orqali baribir qayta pul to'lamasdan olinadi).

    Returns: (audio_fayl_yo'li, haqiqiy_vaqtlar, qa_natijalari) — ikkinchisi
    original Whisper vaqtlaridan siljigan bo'lishi mumkin (yuqoridagi qoida
    tufayli), shuning uchun chaqiruvchi subtitr matnini SHU vaqtlar bilan
    qayta qurishi kerak — aks holda subtitr ovozdan orqada/oldinda qolib
    ketadi. Uchinchisi — job.segment_qa'ga saqlanadigan yangilangan QA holati.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Tarjima/optimallashtirish bosqichlaridagi LLM ba'zan 'id' maydonini
    # tashlab qoldirishi kuzatilgan (KeyError('id') bilan butun jobni
    # qulatgan) — shu yerda oxirgi himoya sifatida tekshiriladi.
    for i, seg in enumerate(segments):
        if "id" not in seg:
            seg["id"] = i

    segments = group_segments_into_sentences(segments)

    # 1. Har bir segmentni parallel ravishda sintez qilish
    def _clean_audio(audio: AudioSegment) -> AudioSegment:
        # Bosh va oxiridagi bo'sh sukunatni tozalash (audio o'z-o'zidan 200-400ms qisqaradi va aniqroq bo'ladi)
        silence_len = 30
        while len(audio) > 150 and audio[:silence_len].dBFS < -42:
            audio = audio[silence_len:]
        while len(audio) > 150 and audio[-silence_len:].dBFS < -42:
            audio = audio[:-silence_len]
        return audio.normalize(headroom=2.0)

    # Ba'zi provayderlar (masalan Gemini) bir nechta segmentni BITTA so'rovda
    # sintez qila oladi — bu daqiqalik/kunlik so'rov-soni limitiga tegishni
    # kamaytiradi. Oldindan tayyorlab qo'yamiz; muvaffaqiyatsiz bo'lgan
    # segmentlar pastdagi oddiy bir-bir yo'lga avtomatik qaytadi.
    pre_synthesized: dict[int, str] = {}
    if not settings.FREE_MODE:
        primary_provider = get_provider()
        try:
            pre_synthesized = primary_provider.synthesize_batch(segments, str(output_path), voice_name=voice_name)
        except Exception as exc:
            logger.warning(f"Batch sintez muvaffaqiyatsiz, oddiy usulga o'tildi: {exc}")
        if pre_synthesized:
            logger.info(f"Batch orqali oldindan tayyorlandi: {len(pre_synthesized)}/{len(segments)} segment")

    # Azure TTS rate-limit: 0.3s interval between requests (prevents 429)
    import threading as _threading
    _azure_rate_lock = _threading.Lock()
    _azure_last_request = [0.0]  # mutable for closure

    def _rate_limit_azure():
        """Minimal delay between Azure TTS requests to avoid 429 TooManyRequests."""
        with _azure_rate_lock:
            now = time.monotonic()
            elapsed = now - _azure_last_request[0]
            if elapsed < 0.3:
                time.sleep(0.3 - elapsed)
            _azure_last_request[0] = time.monotonic()

    def _process_single_segment(idx_seg):
        idx, seg = idx_seg
        text = seg.get("text", "").strip()
        if not text:
            return None
        seg_file = output_path / f"seg_{seg['id']:04d}.wav"
        if seg["id"] in pre_synthesized:
            engine = get_provider().name
        else:
            _rate_limit_azure()  # Rate-limit before Azure TTS call
            engine = _synthesize_text(text, str(seg_file), voice_name=voice_name, video_id=video_id, user_id=user_id)
        if seg_file.exists():
            audio = _clean_audio(AudioSegment.from_wav(str(seg_file)))
            return (idx, {
                "audio": audio,
                "start_ms": int(seg["start"] * 1000),
                "end_ms": int(seg["end"] * 1000),
                "engine": engine,
                "text": text,
                "seg_id": seg["id"],
            })
        return None

    # ElevenLabs bir vaqtda ko'p so'rovni qabul qilmaydi (concurrency limit) —
    # juda ko'p parallel oqim ba'zi segmentlarni Edge TTS'ga (boshqa ovozga)
    # "fallback" qilib qo'yishi mumkin edi, natijada bitta dublyajda ikki xil
    # odam ovozi eshitilardi. 2 oqim — Azure 429 (TooManyRequests) oldini olish.
    with ThreadPoolExecutor(max_workers=2) as executor:
        raw_results = list(executor.map(_process_single_segment, enumerate(segments)))

    # Saralangan segmentlarni yig'ish
    valid_results = [r for r in raw_results if r is not None]
    valid_results.sort(key=lambda x: x[0])
    seg_data = [item for _, item in valid_results]

    if not seg_data:
        raise ValueError("Birlashtirish uchun segment topilmadi.")

    # Ovoz izchilligi: agar ba'zi segmentlar (vaqtinchalik xatolik tufayli)
    # boshqa TTS provayderiga tushib qolgan bo'lsa, ular ko'pchilik
    # ishlatgan provayder bilan ketma-ket (shoshilmasdan) qayta sintez
    # qilinadi — aks holda dublyajda bir necha xil ovoz aralashib qolardi.
    if not settings.FREE_MODE:
        engine_counts: dict[str, int] = {}
        for item in seg_data:
            engine_counts[item["engine"]] = engine_counts.get(item["engine"], 0) + 1
        majority_engine = max(engine_counts, key=engine_counts.get)
        primary = get_provider()
        if majority_engine == primary.name:
            for item in seg_data:
                if item["engine"] == majority_engine:
                    continue
                retry_file = output_path / f"seg_retry_{item['seg_id']:04d}.wav"
                try:
                    time.sleep(1.5)
                    if primary.synthesize(item["text"], str(retry_file), voice_name=voice_name):
                        item["audio"] = _clean_audio(AudioSegment.from_wav(str(retry_file)))
                        item["engine"] = majority_engine
                        logger.info(f"Segment {item['seg_id']} ovoz izchilligi uchun {majority_engine} bilan qayta sintez qilindi.")
                finally:
                    if retry_file.exists():
                        try:
                            retry_file.unlink()
                        except Exception:
                            pass

    # 1.5. Avtomatik QA — har bir segment audiosini signal darajasida
    # tekshiradi (backend/services/audio_qa.py: sukut/kesilgan audio
    # aniqlash, STT'ga tayanmaydi — sababi izoh uchun o'sha faylga qarang).
    # Muvaffaqiyatsiz segmentlar BIR MARTA joyida qayta sintez qilinadi
    # (butun TTS bosqichi emas). Allaqachon o'tgan segmentlar (existing_qa,
    # oldingi Celery urinishidan checkpoint) qayta tekshirilmaydi. Faqat
    # QA'dan o'tgan audio keshga yoziladi (backend/services/tts_cache.py) —
    # aks holda yaroqsiz audio keshlanib, keyingi urinishda AYNAN o'sha
    # yaroqsiz audio qaytib kelardi.
    qa_results: dict = {str(k): v for k, v in (existing_qa or {}).items()}
    if settings.ENABLE_SEGMENT_QA:
        from backend.services.audio_qa import check_audio_quality
        from backend.services.tts_cache import store_cached

        def _qa_and_maybe_retry(item):
            seg_id = item["seg_id"]
            prior = qa_results.get(str(seg_id), {})
            if prior.get("score", 0) >= settings.SEGMENT_QA_THRESHOLD:
                return item, prior

            attempts = prior.get("attempts", 0)
            qa_file = output_path / f"seg_qa_{seg_id:04d}.wav"
            qa = {"score": 0.0, "flags": ["no_speech"], "duration_seconds": 0.0, "silent_ratio": 1.0}
            try:
                item["audio"].export(str(qa_file), format="wav")
                qa = check_audio_quality(str(qa_file), item["text"])

                if qa["score"] < settings.SEGMENT_QA_THRESHOLD and attempts < 2:
                    logger.warning(f"Segment {seg_id} QA'dan o'tmadi (score={qa['score']}, flags={qa['flags']}) — qayta sintez qilinmoqda.")
                    retry_file = output_path / f"seg_qaretry_{seg_id:04d}.wav"
                    try:
                        engine = _synthesize_text(item["text"], str(retry_file), voice_name=voice_name, video_id=video_id, user_id=user_id)
                        if retry_file.exists():
                            item["audio"] = _clean_audio(AudioSegment.from_wav(str(retry_file)))
                            item["engine"] = engine
                            item["audio"].export(str(qa_file), format="wav")
                            qa = check_audio_quality(str(qa_file), item["text"])
                    finally:
                        if retry_file.exists():
                            try:
                                retry_file.unlink()
                            except Exception:
                                pass
                    attempts += 1

                qa["attempts"] = attempts
                if qa["score"] >= settings.SEGMENT_QA_THRESHOLD:
                    try:
                        store_cached(item["text"], voice_name, item["engine"], str(qa_file))
                    except Exception:
                        pass
            finally:
                if qa_file.exists():
                    try:
                        qa_file.unlink()
                    except Exception:
                        pass
            return item, qa

        with ThreadPoolExecutor(max_workers=2) as executor:
            qa_pairs = list(executor.map(_qa_and_maybe_retry, seg_data))
        seg_data = [pair[0] for pair in qa_pairs]
        for item, qa in qa_pairs:
            qa_results[str(item["seg_id"])] = qa

    # 2. Vaqtga moslashtirish — AUDIO HECH QACHON O'RTADAN KESILMAYDI.
    # Avval mo''tadil tezlashtiramiz (max 1.45x); shundan keyin ham audio
    # o'ziga ajratilgan vaqt oralig'idan uzun bo'lsa, KEYINGI segment
    # boshlanishi shunga mos kechiktiriladi — gap hech qachon so'zning
    # yarmida kesilib qolmaydi (oldingi versiyada fade-out bilan qirqib
    # tashlangan, bu "gap oxirigacha aytilmayapti" muammosining asosiy
    # sababi edi). Sezilarli QISQA segmentlar esa (o'lik sukunatni
    # kamaytirish uchun) biroz sekinlashtiriladi — juda katta cho'zish
    # notabiiy eshitilishi mumkinligi uchun faqat mo''tadil qisqalikda.
    prev_end_ms = 0
    for i in range(len(seg_data)):
        cur = seg_data[i]
        original_start_ms = cur["start_ms"]
        start_ms = max(original_start_ms, prev_end_ms)

        if i < len(seg_data) - 1:
            slot_ms = seg_data[i + 1]["start_ms"] - start_ms
        else:
            slot_ms = max(cur["end_ms"] - start_ms, 1000)

        audio_ms = len(cur["audio"])

        if slot_ms > 150 and audio_ms > slot_ms:
            factor = audio_ms / slot_ms
            speed_factor = min(factor, 1.45)
            if speed_factor > 1.03:
                try:
                    cur["audio"] = _speedup_audio(cur["audio"], speed_factor)
                except Exception:
                    pass
        # Qisqa segmentlarni sun'iy sekinlashtirish OLIB TASHLANDI (2026-08-12,
        # real tinglov orqali aniqlangan): foydalanuvchi ovoz tezligi
        # BIR XILDA, original ovozdek tabiiy bo'lishini so'radi — segmentga
        # qarab ba'zan tezlashtirilib, ba'zan sekinlashtirilib turishning
        # o'zi "notekis" hissi berardi. Endi TTS FAQAT o'z tabiiy tezligida
        # gapiradi (yoki juda uzun bo'lsa yuqoridagi xavfsizlik to'ri bilan
        # tezlashtiriladi) — qisqa segmentdan keyingi ortiqcha vaqt shunchaki
        # tabiiy pauza sifatida qoladi, sun'iy cho'zilmaydi.

        cur["start_ms"] = start_ms
        prev_end_ms = start_ms + len(cur["audio"])

    # Subtitr ANIQ shu audio bilan mos kelishi uchun — yuqoridagi moslashtirish
    # segmentlarni original vaqtidan siljitgan bo'lishi mumkin (gap kesilib
    # qolmasligi uchun), shuning uchun chaqiruvchiga HAQIQIY (audio bilan mos)
    # vaqtlar qaytariladi — subtitr shulardan qayta tuziladi, aks holda
    # subtitr eski, endi noto'g'ri original vaqtda qolib ketardi.
    actual_timings = [
        {
            "id": item["seg_id"],
            "start": round(item["start_ms"] / 1000, 3),
            "end": round((item["start_ms"] + len(item["audio"])) / 1000, 3),
            "text": item["text"],
        }
        for item in seg_data
    ]

    # 3. Umumiy audio uzunligini hisoblash
    last = seg_data[-1]
    natural_end_ms = last["start_ms"] + len(last["audio"])
    original_end_ms = last["end_ms"]
    total_ms = max(natural_end_ms, original_end_ms) + 200

    # 4. Segmentlarni bitta audioda joylashtirish — FFmpeg vositasida, xotirada
    #    emas (AUDIT_STABILITY.md §3 P0-2 / §4 Shag 3b).
    #
    #    Eski usul: AudioSegment.silent(duration=total_ms) + overlay() —
    #    ular har bir segment uchun BUTUN parcha XOTIRAda saqlanardi: 3 saotlik
    #    video uchun ~518MB faqat silent-track + har bir overlay yana butun
    #    buffer nusxasi. 4 workerda parallel — OOM-kill -> worker qayta
    #    ishga tushib, recover_stuck* -> siklik qayta ishga tushirish.
    #
    #    Yangi usul: har bir segment diskda wav sifatida (seg_*.wav) — ffmpeg
    #    stream deflyatsiyada: har biri adelay orqali o'z start_ms ga suyiladi
    #    (adelay=delay|delay, stereo), keyin amix normalize=0 bilan aralashtiriladi
    #    va alimiter=0.95 clippingni oldini oladi. Xotira — O(1) by segment,
    #    disk — O(N). Fallback (ffmpeg xato qilsa) — eski pydub usuli.
    merged_path = str(output_path / "dubbed_audio.wav")

    def _fallback_pydub_combine(seg_data, total_ms, merged_path):
        """Xotira usulida birlashtirish — faqat ffmpeg skleyka muvaffaqiyatsiz
        bo'lsa fallback (qisqa video / xato)."""
        combined = AudioSegment.silent(duration=total_ms, frame_rate=_FRAME_RATE)
        for item in seg_data:
            combined = combined.overlay(item["audio"], position=item["start_ms"])
        combined = combined.normalize(headroom=1.5)
        combined.set_frame_rate(_FRAME_RATE).export(merged_path, format="wav")
        return seg_data

    seg_files = sorted(output_path.glob("seg_*.wav"))
    if seg_files:
        seg_id_to_start = {item["seg_id"]: item["start_ms"] for item in seg_data}
        inputs: list[str] = []
        filter_parts: list[str] = []
        amix_inputs: list[str] = []
        idx = 0
        for seg_file in seg_files:
            m = re.search(r"seg_(\d+)\.wav$", seg_file.name)
            if not m:
                continue
            seg_id = int(m.group(1))
            delay_ms = seg_id_to_start.get(seg_id, 0)
            inputs += ["-i", str(seg_file)]
            filter_parts.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms}[d{idx}]")
            amix_inputs.append(f"[d{idx}]")
            idx += 1
        if idx > 0:
            amix = "".join(amix_inputs) + f"amix=inputs={idx}:normalize=0,alimiter=limit=0.95[a]"
            filter_complex = ";".join(filter_parts) + ";" + amix
            cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex,
                   "-map", "[a]", "-ar", str(_FRAME_RATE), "-ac", "1",
                   "-c:a", "pcm_s16le", merged_path]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if proc.returncode != 0:
                logger.warning(f"FFmpeg skleika failed ({proc.stderr[-300:]}). Fallback pydub.")
                _fallback_pydub_combine(seg_data, total_ms, merged_path)
        else:
            _fallback_pydub_combine(seg_data, total_ms, merged_path)
    else:
        _fallback_pydub_combine(seg_data, total_ms, merged_path)

    # Alohida segment fayllari (seg_XXXX.wav) birlashtirilgan audioga
    # kirgandan so'ng boshqa hech qachon kerak bo'lmaydi — ular diskda
    # qolib ketsa, har bir job o'nlab-yuzlab kichik WAV fayl tashlab
    # ketadi (haqiqiy sinovda: job hajmining ~50% shu chiqindi edi).
    for seg_file in output_path.glob("seg_*.wav"):
        try:
            seg_file.unlink()
        except Exception:
            pass

    return merged_path, actual_timings, qa_results


