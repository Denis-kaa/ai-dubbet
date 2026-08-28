import os
import re
import shutil
import time
from pathlib import Path
from datetime import datetime
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from openai import OpenAI
from backend.workers.celery_app import celery_app
from backend.models.database import SessionLocal, DubbingJob, JobStatus
from backend.services import downloader, transcriber, translator, speech_optimizer, synthesizer, merger
from backend.services.chunked_pipeline import (
    split_video_into_chunks,
    split_segments_into_chunks,
    concat_video_chunks,
    cleanup_chunk_files,
)
from backend.services.errors import PermanentError
from backend.services.content_safety import check_safety
from backend.models.database import ContentViolation
from backend.services.email_service import send_dubbing_complete_email
from backend.services.telegram_notify import send_telegram_message
from backend.config import get_settings
from backend.services.scheduler import get_scheduler
from backend.services.backpressure import get_backpressure
from backend.services.metrics import get_metrics
from backend.services.sliding_window import ChunkWindow

logger = get_task_logger(__name__)
settings = get_settings()

# Module-level singletons (lazy — не создают Redis-соединение при импорте)
_scheduler = get_scheduler()
_backpressure = get_backpressure()
_metrics = get_metrics()

# Redis NX-лок против дублей (AUDIT_STABILITY.md §3 P0-1/§4 Шаг 2b):
# `recover_stuck_*` / ручная повторная отправка / Celery retry могут
# положить в очередь второй экземпляр задачи с тем же job_id. Так как
# `task_acks_late=True`, Celery сам дубли не дедуплицирует. Лок
# `job:running:{id}` (Redis SET NX EX) гарантирует, что в каждый момент
# job выполняется ровно ОДИН раз; если лок уже занят — дубликат логируется
# и молча пропускается.
_JOB_LOCK_TTL_SECONDS = 3600  # совпадает с max (hard) time_limit задачи

def _acquire_job_lock(job_id: str) -> bool:
    try:
        from redis import Redis
        r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return bool(r.set(f"job:running:{job_id}", "1", nx=True, ex=_JOB_LOCK_TTL_SECONDS))
    except Exception as exc:
        logger.warning(f"[JOB {job_id}] Redis lock qo'yib bo'lmadi (fail-open): {exc}")
        return True  # fail-open: Redis ishlamasa ham ish davom etsin


def _release_job_lock(job_id: str) -> None:
    try:
        from redis import Redis
        r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.delete(f"job:running:{job_id}")
    except Exception:
        pass


def _sec_to_vtt_time(seconds: float) -> str:
    """Soniyani WebVTT vaqt formatiga o'girish: HH:MM:SS.mmm"""
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = int(seconds // 60) % 60
    h = int(seconds // 3600)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _segments_to_vtt(segments: list[dict]) -> str:
    """Tarjima qilingan segmentlardan WebVTT subtitr yaratish."""
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = _sec_to_vtt_time(seg["start"])
        end   = _sec_to_vtt_time(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _cleanup_upload_dir(job_id: str) -> None:
    """
    uploads/{job_id}/ (yuklab olingan asl video + transkripsiya uchun
    ajratilgan audio) hech qachon foydalanuvchiga ko'rsatilmaydi — faqat
    pipeline ichida ishlatiladi. Job haqiqatan tugagach (COMPLETED yoki
    qayta urinishlar tugab FAILED bo'lgach) endi kerak emas.

    Diqqat: bu faqat job TUGAGANDA chaqiriladi, retry oralig'ida emas —
    aks holda navbatdagi urinish videoni behuda qayta yuklab olar edi.
    """
    job_dir = Path(settings.UPLOAD_DIR) / job_id
    if job_dir.exists():
        try:
            shutil.rmtree(job_dir)
        except Exception as exc:
            logger.warning(f"uploads/{job_id} tozalab bo'lmadi: {exc}")


def _update_job(db, job: DubbingJob, status: JobStatus, progress: float, message: str):
    job.status = status
    job.progress = progress
    job.status_message = message
    job.updated_at = datetime.utcnow()
    db.commit()


_STAGE_ICONS = {"ok": "✅", "skipped": "⏭️", "error": "❌"}


def _record_stage(stage_timings: dict, job_id: str, stage: str, start: float, status: str, detail: str = "") -> None:
    """Bir bosqich tugagach chaqiriladi — davomiylikni saqlaydi va bitta
    izchil formatli log qatorini chiqaradi (masalan monitoring/log
    qidiruvida grep qilish uchun oson bo'lsin deb)."""
    duration = time.monotonic() - start
    stage_timings[stage] = {"duration": duration, "status": status, "detail": detail}
    icon = _STAGE_ICONS.get(status, "•")
    suffix = f" — {detail}" if detail else ""
    logger.info(f"[{job_id}] STAGE={stage} duration={duration:.1f}s status={status} {icon}{suffix}")


def _log_pipeline_summary(job_id: str, stage_timings: dict, total_start: float, final_status: str) -> None:
    """Job tugagach (COMPLETED/FAILED/retry oldidan) yagona, o'qish oson
    hisobot bloki — qaysi bosqich qancha vaqt olganini bir qarashda ko'rish
    uchun."""
    total = time.monotonic() - total_start
    lines = [f"JOB {job_id} [{final_status}]"]
    for stage, info in stage_timings.items():
        icon = _STAGE_ICONS.get(info["status"], "•")
        lines.append(f"  {stage:<12} {info['duration']:>7.1f}s {icon} {info['status']}")
    lines.append(f"  {'TOTAL':<12} {total:>7.1f}s")
    logger.info("\n".join(lines))


def _detect_gender(transcript_text: str) -> str:
    """Detect speaker gender with OpenAI."""
    try:
        snippet = transcript_text[:1000]
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=settings.OPENAI_LIGHT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You analyze video transcripts and determine the speaker's gender. "
                        "Reply with ONLY one word: 'male' or 'female'. "
                        "If unclear or multiple speakers, reply 'male'."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Transcript: {snippet}",
                },
            ],
            max_tokens=5,
            temperature=0,
        )
        result = resp.choices[0].message.content.strip().lower()
        return "female" if "female" in result else "male"
    except Exception:
        return "male"


_URL_CREDENTIAL_RE = re.compile(r"://[^/@\s]+@")


def _scrub_secrets(text: str) -> str:
    """Log qatoridan `http://user:pass@host` shaklidagi URL ichiga ko'milgan
    credential'larni olib tashlaydi (masalan YOUTUBE_PROXY_URL/
    YOUTUBE_RESIDENTIAL_PROXY_URL) — ba'zi urllib3/requests xato xabarlari
    to'liq (proxy) URL'ni o'z ichiga oladi."""
    return _URL_CREDENTIAL_RE.sub("://<redacted>@", text)


def _classify_download_error(exc: Exception) -> str:
    """DOWNLOAD bosqichidagi xatoni aniq toifaga ajratadi — matn-belgi
    (marker) asosida, chunki yt-dlp/urllib3/requests zanjiridan chiqadigan
    xatolar odatda oddiy RuntimeError/OSError bo'lib, o'z `.code`'iga ega
    emas. Faqat XABAR matniga qaraydi — hech qanday sir/token/proxy
    credential loglanmaydi (Webshare URL'ida login:parol bor, lekin bu
    funksiya va chaqiruvchisi hech qachon proxy URL'ining o'zini emas,
    faqat exception matnini ko'radi)."""
    text = str(exc)
    lower = text.lower()

    if "402" in text and ("payment required" in lower or "proxy" in lower):
        return "PROXY_BILLING_ERROR"
    if "proxy" in lower and ("unable to connect" in lower or "tunnel connection failed" in lower or "proxyerror" in lower):
        return "PROXY_ERROR"
    if "sign in to confirm" in lower or "cookies are no longer valid" in lower or "cookielari eskirgan" in lower:
        return "AUTH_ERROR"
    if "timed out" in lower or "timeout" in lower:
        return "TIMEOUT"
    if any(m in lower for m in ("connection reset", "network is unreachable", "failed to establish a new connection", "name or service not known")):
        return "NETWORK_ERROR"
    if "unsupported url" in lower or "is not a valid url" in lower:
        return "INVALID_URL"
    if any(m in lower for m in ("service unavailable", "internal server error", "bad gateway", "http error 5")):
        return "UPSTREAM_ERROR"
    return "DOWNLOAD_ERROR"


def _error_code_for(exc: Exception, current_stage: str) -> str:
    """Xatolikni qisqa toifaga ajratadi (admin panel/monitoring uchun)."""
    code = getattr(exc, "code", None)
    if code:
        return code
    if isinstance(exc, SoftTimeLimitExceeded):
        return "TIMEOUT"
    if current_stage == "DOWNLOAD":
        return _classify_download_error(exc)
    return f"{current_stage}_FAILED"


def _mark_job_failed(job_id: str, exc: Exception, current_stage: str) -> None:
    """Job'ni FAILED holatiga o'tkazadi — doim BUTUNLAY YANGI DB sessiyasi
    bilan, chaqiruvchining `db` sessiyasidan mustaqil ravishda.

    Sabab: 2026-08-21/22 productionda haqiqiy job (cdc1f75e) topildi — u
    yuklab olishda muvaffaqiyatsiz bo'lgach, xuddi shu `except` bloki FAILED
    deb belgilashga urinayotganda DB ulanishi vaqtinchalik uzilgan edi
    (`OperationalError: server closed the connection unexpectedly`) — bu
    IKKINCHI xato hech qayerda ushlanmagani uchun, job hech qachon FAILED
    bo'lmay, oxirgi muvaffaqiyatli holatida (DOWNLOADING) ABADIY qotib
    qolgan edi. Bu funksiya shu holatni oldini oladi: eski `db` qanday
    holatda bo'lishidan qat'i nazar, 2 marta yangi sessiya bilan urinadi;
    ikkalasi ham muvaffaqiyatsiz bo'lsa, kamida CRITICAL log qoldiradi —
    "hech narsa" o'rniga."""
    fields = {
        "status": JobStatus.FAILED,
        "error_message": str(exc),
        "error_code": _error_code_for(exc, current_stage),
        "updated_at": datetime.utcnow(),
    }
    for attempt in range(2):
        session = SessionLocal()
        try:
            session.query(DubbingJob).filter(DubbingJob.id == job_id).update(fields)
            session.commit()
            return
        except Exception as mark_exc:
            logger.error(f"[JOB {job_id}] FAILED holatiga o'tkazishda xatolik (urinish {attempt + 1}/2): {mark_exc}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
    logger.critical(f"[JOB {job_id}] FAILED holatiga HECH QANDAY usulda o'tkazib bo'lmadi — job eski holatida abadiy qotib qolishi mumkin!")


@celery_app.task(
    bind=True,
    name="backend.workers.tasks.process_video",
    max_retries=5,
    default_retry_delay=60,
    soft_time_limit=3300,  # 55 daqiqa — osilib qolgan bosqichga ogohlantirish
    time_limit=3600,       # 60 daqiqa — worker'ni majburan to'xtatadi (hard limit)
)
def process_video(self: Task, job_id: str) -> dict:
    # NX-лок: agar этот job УЖЕ выполняется другим воркером — дубликат
    # пропускаем (см. _acquire_job_lock docstring).
    if not _acquire_job_lock(job_id):
        logger.warning(f"[JOB {job_id}] allaqachon boshqa worker'da bajarilmoqda — dublikat o'tkazib yuborildi.")
        return {"job_id": job_id, "status": "already_running"}

    db = SessionLocal()
    stage_timings: dict = {}
    pipeline_start = time.monotonic()
    current_stage = "INIT"

    # ─── Scheduler: per-user concurrency check (промт 115 §4) ───
    user_id_str = None  # будет заполнен после загрузки job

    try:
        job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
        if not job:
            raise ValueError(f"Job topilmadi: {job_id}")

        job_dir = Path(settings.UPLOAD_DIR) / job_id
        output_dir = Path(settings.OUTPUT_DIR) / job_id

        # Scheduler: per-user limit check
        user_id_str = str(job.user_id) if job.user_id else "anonymous"
        if not _scheduler.can_accept_job(user_id_str):
            logger.warning(f"[JOB {job_id}] Per-user limit reached for {user_id_str} — scheduling deferred")
        _scheduler.register_active_job(user_id_str, job_id)

        # Metrics: start tracking
        _metrics.start_job(user_id_str, job_id)

        # BOSQICH 1: Yuklash
        # Checkpoint: agar video+audio disk'da hali ham mavjud bo'lsa (masalan
        # oldingi urinish shu yerdan keyin qulagan bo'lsa), qayta yuklab
        # olinmaydi — YouTube'ga behuda so'rov yuborilmaydi.
        current_stage = "DOWNLOAD"
        stage_t0 = time.monotonic()
        audio_path = str(job_dir / "audio.wav")
        if job.original_video_path and Path(job.original_video_path).exists() and Path(audio_path).exists():
            _record_stage(stage_timings, job_id, "DOWNLOAD", stage_t0, "skipped")
            video_path = job.original_video_path
        else:
            _update_job(db, job, JobStatus.DOWNLOADING, 5.0, "YouTube'dan yuklanmoqda...")
            download_result = downloader.download_video(job.youtube_url, job_id)
            job.video_title = download_result["title"]
            job.video_duration = download_result["duration"]
            job.original_video_path = download_result["video_path"]
            db.commit()
            video_path = download_result["video_path"]
            audio_path = download_result["audio_path"]
            _record_stage(stage_timings, job_id, "DOWNLOAD", stage_t0, "ok")

        # BOSQICH 2: Transkripsiya
        # Checkpoint: xom segmentlar (timestamp bilan) DB'da saqlanadi —
        # ular bo'lsa, qimmat/uzoq transkripsiya qayta bajarilmaydi.
        current_stage = "TRANSCRIBE"
        stage_t0 = time.monotonic()
        if job.transcript_segments:
            _record_stage(stage_timings, job_id, "TRANSCRIBE", stage_t0, "skipped")
            segments = job.transcript_segments
            transcript_text = job.transcript_text or ""
        else:
            _update_job(db, job, JobStatus.TRANSCRIBING, 20.0, "Nutq matnga aylantirilmoqda...")
            transcript = transcriber.transcribe_audio(audio_path)
            if not transcript["segments"] or not transcriber.has_speech(transcript["segments"]):
                _record_stage(stage_timings, job_id, "TRANSCRIBE", stage_t0, "error", "nutq topilmadi")
                raise PermanentError("Bu videoda nutq topilmadi.", code="NO_SPEECH_FOUND")
            job.transcript_text = transcript["text"]
            job.srt_content = transcript["srt"]
            job.transcript_segments = transcript["segments"]
            db.commit()
            segments = transcript["segments"]
            transcript_text = transcript["text"]
            _record_stage(stage_timings, job_id, "TRANSCRIBE", stage_t0, "ok")

        # Safety Gate -- 2-bosqich (transkript). Sarlavha zararsiz ko'ringan,
        # lekin videoning haqiqiy nutqi siyosatga zid bo'lgan holatlarni shu
        # yerda ushlaydi -- tarjima/TTS (qimmat bosqichlar) boshlanishidan OLDIN.
        current_stage = "SAFETY_CHECK"
        safety = check_safety(transcript_text)
        if not safety.allowed:
            # Faqat CSAM (sexual_minors) shu yerga yetib keladi -- yagona
            # qat'iy blok. user_id NOT NULL -- anonim job (deyarli
            # bo'lmaydi, login majburiy, lekin himoya sifatida) uchun
            # yozuv qo'shmaymiz, video baribir bloklanadi.
            if job.user_id is not None:
                db.add(ContentViolation(
                    user_id=job.user_id,
                    youtube_url=job.youtube_url,
                    video_title=job.video_title,
                    stage="transcript",
                    category=safety.category or "policy_violation",
                    reason=safety.reason or "",
                    blocked=True,
                ))
                db.commit()
            raise PermanentError(
                "Ushbu video GapirAI.uz kontent siyosatiga mos kelmagani sababli dublaj qilinmaydi.",
                code="CONTENT_BLOCKED",
            )
        if safety.category and job.user_id is not None:
            # Ogohlantirish -- pipeline to'xtamaydi, faqat qayd etiladi.
            db.add(ContentViolation(
                user_id=job.user_id,
                youtube_url=job.youtube_url,
                video_title=job.video_title,
                stage="transcript",
                category=safety.category,
                reason=safety.reason or "",
                blocked=False,
            ))
            job.content_flagged = True
            db.commit()

        # Whisper segmentlari nutq pauzasiga qarab kesilgan, gap chegarasiga
        # emas — tarjima/nutq optimallashdan OLDIN tabiiy gaplarga
        # birlashtiramiz, aks holda LLM har bir bo'lakka soxta nuqta qo'yib,
        # keyingi bosqichlarni "bu tugal gap" deb aldab qo'yadi.
        segments = synthesizer.group_segments_into_sentences(segments)

        # BOSQICH 3: Jins aniqlash (foydalanuvchi tanlamagan bo'lsa avtomatik)
        current_stage = "GENDER"
        stage_t0 = time.monotonic()
        if job.speaker_gender:
            gender = job.speaker_gender
            _record_stage(stage_timings, job_id, "GENDER", stage_t0, "skipped")
        else:
            setting = job.voice_gender_setting or "auto"
            if setting in ("male", "female"):
                gender = setting
            else:
                _update_job(db, job, JobStatus.TRANSLATING, 35.0, "Spikerning jinsi aniqlanmoqda...")
                gender = _detect_gender(transcript_text)
            job.speaker_gender = gender
            db.commit()
            _record_stage(stage_timings, job_id, "GENDER", stage_t0, "ok")

        # BOSQICH 4: Tarjima
        # Checkpoint: tarjima qilingan segmentlar saqlanadi — Google
        # Translate'ga qayta murojaat qilinmaydi.
        current_stage = "TRANSLATE"
        stage_t0 = time.monotonic()
        if job.translated_segments:
            _record_stage(stage_timings, job_id, "TRANSLATE", stage_t0, "skipped")
            translated_segments = job.translated_segments
        else:
            _update_job(db, job, JobStatus.TRANSLATING, 40.0, "O'zbek tiliga tarjima qilinmoqda...")
            translated_segments = translator.translate_segments(segments)

            # Davomiylik tekshiruvi — original segment vaqtidan sezilarli
            # uzunroq chiqqan tarjimalar BIR MARTA qisqartiriladi (haqiqiy
            # TTS chaqirilmasdan, belgi-tezlik evristikasi bilan taxmin
            # qilinadi). TRANSLATE checkpoint'i bilan birga saqlanadi —
            # qayta ishlashda ikkalasi ham birga o'tkazib yuboriladi.
            over_budget = {}
            for seg in translated_segments:
                target = seg.get("end", 0) - seg.get("start", 0)
                if target <= 0:
                    continue
                estimated = translator.estimate_duration_seconds(seg.get("text", ""))
                if estimated > target * settings.DURATION_OVERAGE_TOLERANCE:
                    over_budget[seg["id"]] = target
            if over_budget:
                logger.info(f"Job {job_id}: {len(over_budget)} segment vaqt byudjetidan oshib ketgan — qisqartirilmoqda.")
                to_shorten = [s for s in translated_segments if s["id"] in over_budget]
                shortened = translator.shorten_segments(to_shorten, over_budget)
                shortened_by_id = {s["id"]: s for s in shortened}
                translated_segments = [shortened_by_id.get(s["id"], s) for s in translated_segments]

            job.translated_text = " ".join(s["text"] for s in translated_segments)
            job.uzbek_srt_content = _segments_to_vtt(translated_segments)
            job.translated_segments = translated_segments
            db.commit()
            _record_stage(stage_timings, job_id, "TRANSLATE", stage_t0, "ok")

        # BOSQICH 4.5: Nutq uchun optimallashtirish (raqamlar, qisqartmalar, og'zaki uslub)
        # Faqat TTS kirishi uchun — subtitr matni yuqoridagi tarjimadan o'zgarishsiz qoladi,
        # chunki "JWT" -> "Jey Vi Ti" kabi og'zaki shakllar yozma subtitrda g'alati ko'rinadi.
        # Checkpoint: bu bosqich LLM chaqiruvi bo'lishi mumkin (pullik) — natija saqlanadi.
        current_stage = "SPEECH_OPT"
        stage_t0 = time.monotonic()
        if job.speech_segments:
            _record_stage(stage_timings, job_id, "SPEECH_OPT", stage_t0, "skipped")
            speech_segments = job.speech_segments
        else:
            _update_job(db, job, JobStatus.SYNCING, 50.0, "Matn tabiiy talaffuzga moslashtirilmoqda...")
            speech_segments = speech_optimizer.optimize_segments(translated_segments)
            job.speech_segments = speech_segments
            db.commit()
            _record_stage(stage_timings, job_id, "SPEECH_OPT", stage_t0, "ok")

        # BOSQICH 5: TTS (jinsga mos ovoz)
        # Checkpoint: agar birlashtirilgan dublyaj audiosi allaqachon
        # diskda bo'lsa, ElevenLabs'ga qayta pul to'lab sintez qilinmaydi.
        current_stage = "TTS"
        stage_t0 = time.monotonic()
        if job.dubbed_audio_path and Path(job.dubbed_audio_path).exists():
            _record_stage(stage_timings, job_id, "TTS", stage_t0, "skipped")
            dubbed_audio_path = job.dubbed_audio_path
            # Checkpoint orqali qayta tiklangan job uchun aniq segment
            # vaqtlari qayta hisoblanmaydi (qimmat emas, shunchaki mavjud
            # emas bu bosqichda) — yakuniy QA (pastda) bunsiz ham
            # clipping/balandlik tekshiruvlarini bajaradi, faqat dub/fon
            # balansi tekshiruvi o'tkazib yuboriladi.
            actual_timings = None
        else:
            voice = "uz-UZ-MadinaNeural" if gender == "female" else "uz-UZ-SardorNeural"
            _update_job(db, job, JobStatus.SYNTHESIZING, 60.0,
                        f"O'zbek ovozi yaratilmoqda ({'ayol' if gender == 'female' else 'erkak'})...")
            tts_dir = str(output_dir / "tts_segments")

            # Chunked pipeline: video va segmentlarni chunk'larga bo'lib,
            # TTS + MERGE ni parallel ravishda bajarish (~1.7-2x tezroq).
            if settings.ENABLE_CHUNKED_PIPELINE:
                logger.info(f"[JOB {job_id}] Chunked pipeline YONIQ (chunk={settings.CHUNK_DURATION_SEC}s, parallel={settings.MAX_PARALLEL_CHUNKS})")
                output_dir.mkdir(parents=True, exist_ok=True)

                # Video chunk'larga bo'lish
                video_chunks = split_video_into_chunks(
                    video_path, str(output_dir),
                    chunk_duration_sec=settings.CHUNK_DURATION_SEC,
                    overlap_sec=settings.CHUNK_OVERLAP_SEC,
                )

                # Segmentlarni chunk'larga bo'lish
                segment_chunks = split_segments_into_chunks(speech_segments, video_chunks)

                # ─── Sliding Window: progressive chunk processing (промт 115 §2) ───
                chunk_ids = [f"{job_id}_c{i}" for i in range(len(video_chunks))]
                window = ChunkWindow(job_id=job_id, window_size=settings.MAX_PARALLEL_CHUNKS)
                window.init_chunks(chunk_ids)
                _metrics.set_chunks_total(job_id, len(video_chunks))
                logger.info(f"[JOB {job_id}] Sliding window initialized: {len(video_chunks)} chunks, window={settings.MAX_PARALLEL_CHUNKS}")

                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading

                # Backpressure lock для thread-safety
                _bp_lock = threading.Lock()

                def _process_chunk(chunk_idx: int) -> dict:
                    """Bitta chunk uchun TTS + MERGE (backpressure-aware)."""
                    chunk_id = f"{job_id}_c{chunk_idx}"
                    chunk_output_dir = str(output_dir / f"chunk_{chunk_idx}_tts")
                    os.makedirs(chunk_output_dir, exist_ok=True)

                    # TTS uchun bu chunkning segmentlari
                    chunk_segments = segment_chunks[chunk_idx]
                    if not chunk_segments:
                        return {"chunk_idx": chunk_idx, "merged_path": None}

                    # ─── Backpressure: ждём пока Media не освободит место (промт 115 §8) ───
                    with _bp_lock:
                        while not _backpressure.can_produce_tts(job_id):
                            backoff = _backpressure.get_backoff_seconds(job_id)
                            logger.info(f"[JOB {job_id}] Backpressure: TTS throttled for chunk {chunk_idx}, waiting {backoff}s")
                            time.sleep(backoff)
                        _backpressure.register_tts_produced(job_id, chunk_id)

                    # ─── Window: mark chunk as processing ───
                    window.start_chunk(chunk_id)
                    chunk_t0 = time.monotonic()

                    # TTS
                    chunk_audio, chunk_timings, chunk_qa = synthesizer.synthesize_segments(
                        chunk_segments, chunk_output_dir, voice_name=voice,
                        video_id=f"{job_id}_c{chunk_idx}",
                        user_id=(str(job.user_id) if job.user_id else None),
                        existing_qa=job.segment_qa,
                    )
                    tts_latency = time.monotonic() - chunk_t0
                    _metrics.record_tts_latency(job_id, chunk_id, tts_latency)

                    # ─── Media: MERGE (backpressure-tracked) ───
                    with _bp_lock:
                        _backpressure.register_media_started(job_id, chunk_id)

                    media_t0 = time.monotonic()
                    merged_chunk_path = str(output_dir / f"merged_chunk_{chunk_idx:02d}.mp4")
                    merger.merge_video_audio_chunk(
                        video_chunk_path=video_chunks[chunk_idx].video_path,
                        dubbed_audio_path=chunk_audio,
                        output_path=merged_chunk_path,
                        audio_mix_mode=job.audio_mix_mode,
                        chunk_index=chunk_idx,
                    )
                    media_latency = time.monotonic() - media_t0
                    _metrics.record_media_latency(job_id, chunk_id, media_latency)

                    # ─── Backpressure: chunk consumed ───
                    with _bp_lock:
                        _backpressure.register_media_consumed(job_id, chunk_id)
                        _backpressure.register_media_finished(job_id, chunk_id)

                    # ─── Window: mark chunk as ready ───
                    window.complete_chunk(chunk_id)
                    _metrics.record_chunk_completed(job_id)

                    # ─── TTFP: записать если это ПЕРВЫЙ готовый chunk ───
                    _metrics.record_ttfp(job_id, chunk_id)

                    logger.info(
                        f"[JOB {job_id}] Chunk {chunk_idx}/{len(video_chunks)-1} tayyor "
                        f"(TTS={tts_latency:.1f}s, Media={media_latency:.1f}s, "
                        f"window_pos={window.get_buffer_status()['window_position']})"
                    )

                    return {
                        "chunk_idx": chunk_idx,
                        "merged_path": merged_chunk_path,
                        "timings": chunk_timings,
                        "qa": chunk_qa,
                    }

                # ─── Sliding window: process chunks respecting window bounds ───
                chunk_results = [None] * len(video_chunks)
                with ThreadPoolExecutor(max_workers=settings.MAX_PARALLEL_CHUNKS) as executor:
                    future_to_chunk = {}
                    submitted = set()

                    while not window.is_complete():
                        # Получаем chunks из текущего окна
                        next_chunks = window.get_next_window()
                        for chunk_id in next_chunks:
                            chunk_idx = int(chunk_id.split("_c")[-1])
                            if chunk_idx not in submitted:
                                future = executor.submit(_process_chunk, chunk_idx)
                                future_to_chunk[future] = chunk_idx
                                submitted.add(chunk_idx)

                        # Ждём завершения хотя бы одного future
                        if future_to_chunk:
                            import concurrent.futures as _cf
                            done, _ = _cf.wait(
                                future_to_chunk.keys(),
                                timeout=1.0,
                                return_when=_cf.FIRST_COMPLETED,
                            )
                            for future in done:
                                chunk_idx = future_to_chunk.pop(future)
                                try:
                                    result = future.result()
                                    chunk_results[chunk_idx] = result
                                except Exception as exc:
                                    chunk_id = f"{job_id}_c{chunk_idx}"
                                    window.fail_chunk(chunk_id, str(exc))
                                    _metrics.record_chunk_failed(job_id)
                                    logger.error(f"[JOB {job_id}] Chunk {chunk_idx} xatosi: {exc}")
                                    raise
                        else:
                            # Все chunks submitted, ждём оставшиеся
                            done, _ = __import__("concurrent.futures", fromlist=["wait"]).wait(
                                future_to_chunk.keys(),
                                timeout=1.0,
                                return_when=__import__("concurrent.futures").FIRST_COMPLETED,
                            )
                            for future in done:
                                chunk_idx = future_to_chunk.pop(future)
                                try:
                                    result = future.result()
                                    chunk_results[chunk_idx] = result
                                except Exception as exc:
                                    chunk_id = f"{job_id}_c{chunk_idx}"
                                    window.fail_chunk(chunk_id, str(exc))
                                    _metrics.record_chunk_failed(job_id)
                                    logger.error(f"[JOB {job_id}] Chunk {chunk_idx} xatosi: {exc}")
                                    raise
                            if not future_to_chunk:
                                break

                # Barcha chunklarni birlashtirish
                merged_paths = [r["merged_path"] for r in chunk_results if r and r["merged_path"]]
                final_output = str(output_dir / "dubbed_final.mp4")
                concat_video_chunks(merged_paths, final_output)

                # Vaqtinchalik chunk fayllarini tozalash
                cleanup_chunk_files(video_chunks, str(output_dir))

                # Backpressure cleanup для этого job
                _backpressure.cleanup_job(job_id)

                # Birlashtirilgan audio (QA uchun)
                dubbed_audio_path = final_output
                actual_timings = None  # Chunked pipeline'da aniq timinglar chunk ichida
                job.segment_qa = {}  # QA results from chunks could be merged here

            else:
                # Eski sequential rejim (chunked pipeline o'chirilgan bo'lsa)
                _metrics.set_chunks_total(job_id, 1)
                _backpressure.register_tts_produced(job_id, f"{job_id}_seq")
                dubbed_audio_path, actual_timings, qa_results = synthesizer.synthesize_segments(
                    speech_segments, tts_dir, voice_name=voice,
                    video_id=job_id, user_id=(str(job.user_id) if job.user_id else None),
                    existing_qa=job.segment_qa,
                )
                _backpressure.register_media_consumed(job_id, f"{job_id}_seq")
                _metrics.record_chunk_completed(job_id)
                _metrics.record_ttfp(job_id, f"{job_id}_seq")

            job.dubbed_audio_path = dubbed_audio_path
            # Segment darajasidagi QA checkpoint — Celery qayta urinishida
            # faqat muvaffaqiyatsiz/tekshirilmagan segmentlar qayta
            # ishlanadi (synthesizer.py'ning existing_qa parametri orqali).
            if actual_timings is not None:  # Sequential rejimda
                job.segment_qa = qa_results
            # Audio gap kesilib qolmasligi uchun original vaqtdan siljigan
            # bo'lishi mumkin (synthesizer.py) — subtitr shu HAQIQIY
            # vaqtlar bilan qayta quriladi, aks holda ovoz bilan mos
            # tushmay qoladi.
            if actual_timings is not None:
                job.uzbek_srt_content = _segments_to_vtt(actual_timings)
            db.commit()
            _record_stage(stage_timings, job_id, "TTS", stage_t0, "ok")

        # BOSQICH 6: Birlashtirish
        # Checkpoint: yakuniy video allaqachon tayyor bo'lsa, ffmpeg qayta
        # ishlamaydi.
        current_stage = "MERGE"
        stage_t0 = time.monotonic()
        if job.output_video_path and Path(job.output_video_path).exists():
            _record_stage(stage_timings, job_id, "MERGE", stage_t0, "skipped")
            final_output = job.output_video_path
        else:
            _update_job(db, job, JobStatus.MERGING, 85.0, "Video birlashtirilmoqda...")
            final_output = str(output_dir / "dubbed_final.mp4")
            output_dir.mkdir(parents=True, exist_ok=True)

            # Agar chunked pipeline ishlatilgan bo'lsa — MERGE allaqachon
            # chunk'lar ichida bajarilgan va ular birlashtirilgan.
            # Faqat agar final video hali yo'q bo'lsa — sequential MERGE.
            if settings.ENABLE_CHUNKED_PIPELINE and Path(final_output).exists():
                # Chunked pipeline allaqachon final_output ni yaratgan
                logger.info(f"[JOB {job_id}] MERGE: chunked pipeline allaqachon yakuniy video yaratdi")
            else:
                # Sequential MERGE (eski rejim yoki chunked pipeline xatosi)
                merger.merge_video_audio(
                    video_path=video_path,
                    dubbed_audio_path=dubbed_audio_path,
                    output_path=final_output,
                    audio_mix_mode=job.audio_mix_mode,
                )

            job.output_video_path = final_output
            job.output_video_url = f"/outputs/{job_id}/dubbed_final.mp4"
            db.commit()
            _record_stage(stage_timings, job_id, "MERGE", stage_t0, "ok")

        # Yakuniy aralashma QA — merger.py'ning ducking/mixing natijasini
        # signal darajasida tekshiradi (clipping, loudness range, dub/fon
        # balansi). Faqat diagnostika — hozircha alohida retry mexanizmi
        # yo'q (segment-QA'dan farqli, bu butun videoni qamraydi), shuning
        # uchun muammo topilsa job baribir COMPLETED bo'ladi, lekin loglarda
        # aniq ko'rinadi. Local fayl S3'ga yuklanib o'chirilishidan OLDIN
        # ishlashi kerak.
        try:
            from backend.services.audio_qa import check_final_mix_quality
            final_qa = check_final_mix_quality(
                final_output,
                actual_timings,
                audio_mix_mode=job.audio_mix_mode,
            )
            if final_qa["flags"]:
                logger.warning(
                    f"Job {job_id}: yakuniy aralashmada muammo(lar) — {final_qa['flags']} "
                    f"(score={final_qa['score']}, peak={final_qa['peak_dbfs']}dBFS, "
                    f"LRA={final_qa['loudness_lra']}, dub={final_qa['dub_rms_dbfs']}dBFS, "
                    f"fon={final_qa['background_rms_dbfs']}dBFS)"
                )
            else:
                logger.info(f"Job {job_id}: yakuniy aralashma QA'dan o'tdi (score={final_qa['score']}).")
        except Exception as exc:
            logger.warning(f"Job {job_id}: yakuniy QA ishlamadi (pipeline davom etadi): {exc}")

        # Upload files to S3 if configured — muvaffaqiyatli yuklangandan
        # so'ng lokal nusxa DARHOL o'chiriladi (S3 endi doimiy manba,
        # disk cheklangan va cheksiz to'planib qolmasligi kerak).
        try:
            from backend.services.storage import upload_file_to_s3
            s3_audio_key = f"dubber/{job_id}/dubbed_audio.wav"
            s3_video_key = f"dubber/{job_id}/dubbed_final.mp4"
            logger.info(f"Uploading output files for job {job_id} to S3...")

            if upload_file_to_s3(dubbed_audio_path, s3_audio_key):
                try:
                    os.remove(dubbed_audio_path)
                except Exception:
                    pass
            if upload_file_to_s3(final_output, s3_video_key):
                try:
                    os.remove(final_output)
                except Exception:
                    pass
        except Exception as s3_err:
            logger.error(f"S3 upload failed for job {job_id}: {s3_err}")

        _update_job(db, job, JobStatus.COMPLETED, 100.0, "Dublyaj tayyor!")
        job.completed_at = datetime.utcnow()
        db.commit()

        # Anonim (login qilmagan) joblar uchun email yo'q — jim o'tkazib
        # yuboriladi. Email yuborish muvaffaqiyatsiz bo'lsa ham job
        # COMPLETED holatida qoladi (bildirishnoma ikkinchi darajali).
        if job.user_id and job.user and job.user.email:
            try:
                send_dubbing_complete_email(job.user.email, job.user.name or "", job.video_title or "Video", job_id)
            except Exception as email_err:
                logger.warning(f"Dublyaj tayyor email yuborilmadi (job {job_id}): {email_err}")

        # Telegram bot orqali bog'langan bo'lsa (backend/telegram_bot.py) --
        # web orqali yaratilgan job bo'lsa ham, foydalanuvchi telefon
        # raqami botga ham ulangan bo'lsa xabar boradi. Rezolyutsiya
        # tugmalari tarifga qarab cheklanadi (backend/services/plans.py) --
        # tugma bosilganda telegram_bot.py resolution_variants.request_resolution()
        # ni chaqiradi, xuddi veb bilan bir xil.
        if job.user_id and job.user and job.user.telegram_chat_id:
            frontend_url = (settings.FRONTEND_URL or "https://gapirai.uz").rstrip("/")
            from backend.services.plans import get_max_resolution_for_job, RESOLUTION_ORDER
            max_res = get_max_resolution_for_job(db, job)
            allowed = RESOLUTION_ORDER[: RESOLUTION_ORDER.index(max_res) + 1]
            keyboard = {"inline_keyboard": [[
                {"text": res, "callback_data": f"res:{job_id}:{res}"} for res in allowed
            ]]}
            send_telegram_message(
                job.user.telegram_chat_id,
                f"\u2705 Dublyaj tayyor!\n\n\U0001F3AC {job.video_title or 'Video'}\n\n{frontend_url}/video/{job_id}\n\nYuklab olish uchun sifatni tanlang:",
                reply_markup=keyboard,
            )

        _cleanup_upload_dir(job_id)

        # ─── Metrics: end tracking ───
        _metrics.end_job(job_id)
        job_metrics = _metrics.get_job_metrics(job_id)
        if job_metrics:
            logger.info(
                f"[JOB {job_id}] Metrics: TTFP={job_metrics['ttfp']}s, "
                f"total={job_metrics['total_processing']}s, "
                f"chunks={job_metrics['chunks_completed']}/{job_metrics['chunks_total']}"
            )

        # ─── Scheduler: release job ───
        _scheduler.release_job(user_id_str, job_id)

        _log_pipeline_summary(job_id, stage_timings, pipeline_start, "COMPLETED")

        return {"job_id": job_id, "status": "completed", "output_url": job.output_video_url}


    except PermanentError as exc:
        # Qayta urinish ma'nosiz — har safar bir xil natija chiqadi.
        # Status-o'tkazish endi mustaqil, yangi sessiya bilan (_mark_job_failed) —
        # eski `db` sessiyasi shu paytda qanday holatda bo'lishidan qat'i nazar.
        _mark_job_failed(job_id, exc, current_stage)
        try:
            if job.user_id and job.user and job.user.telegram_chat_id:
                send_telegram_message(
                    job.user.telegram_chat_id,
                    f"\u274c Dublyaj bajarilmadi: {job.video_title or 'Video'}\n\n{str(exc)}",
                )
        except Exception as notify_exc:
            logger.warning(f"[JOB {job_id}] Telegram xabari yuborilmadi: {notify_exc}")
        _cleanup_upload_dir(job_id)

        # ─── Metrics + Scheduler: cleanup on permanent failure ───
        _metrics.end_job(job_id)
        _metrics.record_chunk_failed(job_id)
        if user_id_str:
            _scheduler.release_job(user_id_str, job_id)
        _backpressure.cleanup_job(job_id)

        _log_pipeline_summary(job_id, stage_timings, pipeline_start, "FAILED (permanent)")
        raise exc

    except Exception as exc:
        # Slot band (YouTube rate limiter) — retry qilish ma'noli, lekin hozircha
        # qisqa countdown: 2 daqiqada slot bo'shab qoladi (AUDIT_STABILITY.md §4).
        if "slot not available" in str(exc):
            countdown = min(600, 120)
            db.close()
            raise self.retry(exc=exc, countdown=countdown)

        if self.request.retries < self.max_retries:
            # Do 600s'gacha (10 daq) — bugun kuzatilgan naqsh
            # ~10-15 daqiqada tozalanadi (2026-08-14); qayta urinishlar
            # oralig'i shu oynaga yetib borishi uchun oshirildi (avval 300s).
            countdown = min(600, 30 * (2 ** self.request.retries))
            # Qayta urinishlar mavjud bo'lsa statusni FAILED qilmaymiz, faqat xabarni yangilaymiz.
            # DIQQAT: uploads/ VA job'ning bajarilgan bosqich natijalari
            # (transcript_segments, translated_segments, ...) ATAYLAB
            # tozalanmaydi/o'chirilmaydi — keyingi urinish shu checkpoint
            # nuqtalaridan davom etadi, boshidan boshlamaydi.
            job = db.query(DubbingJob).filter(DubbingJob.id == job_id).first()
            if job:
                job.status_message = f"Vaqtinchalik xatolik (qayta urinish {self.request.retries + 1}/{self.max_retries})..."
                job.error_message = str(exc)
                job.error_code = _error_code_for(exc, current_stage)
                job.updated_at = datetime.utcnow()
                db.commit()
            db.close()
            _log_pipeline_summary(job_id, stage_timings, pipeline_start, f"RETRY {self.request.retries + 1}/{self.max_retries}")
            raise self.retry(exc=exc, countdown=countdown)

        error_code = _error_code_for(exc, current_stage)
        if current_stage == "DOWNLOAD":
            # Foydalanuvchi so'ragan aniq log formati — monitoring/grep uchun
            # (masalan `docker compose logs worker | grep PROXY_BILLING_ERROR`
            # orqali Webshare balansi tugagan holatlarni tezda topish uchun).
            # Xabar matni credential'lardan tozalangan (_scrub_secrets).
            logger.error(f"[DOWNLOAD] attempt {self.request.retries + 1}/{self.max_retries}")
            logger.error(f"[DOWNLOAD] error_type={error_code}")
            logger.error(f"[DOWNLOAD] job_id={job_id}")
            logger.error(f"[DOWNLOAD] {_scrub_secrets(str(exc))}")
            logger.error("[DOWNLOAD] max retries reached")
            logger.error("[JOB] status=FAILED")

        # Status-o'tkazish endi mustaqil, yangi sessiya bilan (_mark_job_failed) —
        # eski `db` sessiyasi shu paytda qanday holatda bo'lishidan qat'i nazar
        # (2026-08-21/22 productionda haqiqiy job shu sabab bilan abadiy qotib
        # qolgan edi — batafsili izoh _mark_job_failed'ning o'zida).
        _mark_job_failed(job_id, exc, current_stage)

        # Kvota qaytarish -- bepul/kvota bilan boshlangan job 5 marta
        # urinib ham muvaffaqiyatsiz tugasa, sarflangan kvota userga qaytadi
        # (2026-08-19, foydalanuvchi so'rovi). Pullik (Click) job'lar uchun
        # avtomatik pul qaytarish integratsiyasi yo'q -- Payment.needs_refund
        # true qilinadi, admin panelda qo'lda qaytarish uchun ko'rsatiladi.
        # O'z alohida sessiyasi va try/except bilan — bu yerdagi xato endi
        # yuqoridagi status-o'tkazishga ta'sir qilmaydi.
        refund_db = None
        try:
            refund_db = SessionLocal()
            if job.quota_consumed and job.user_id:
                from backend.services.plans import refund_quota
                refund_quota(refund_db, job.user_id)
                refund_db.query(DubbingJob).filter(DubbingJob.id == job_id).update({"quota_consumed": False})
            else:
                from backend.models.payment import Payment, PaymentStatus
                paid = refund_db.query(Payment).filter(
                    Payment.job_id == job_id, Payment.status == PaymentStatus.APPROVED
                ).first()
                if paid:
                    paid.needs_refund = True
            refund_db.commit()
        except Exception as refund_exc:
            logger.error(f"[JOB {job_id}] Kvota/to'lov qaytarish belgisini qo'yishda xatolik: {refund_exc}")
        finally:
            if refund_db is not None:
                refund_db.close()

        try:
            if job.user_id and job.user and job.user.telegram_chat_id:
                send_telegram_message(
                    job.user.telegram_chat_id,
                    f"\u274c Dublyaj bajarilmadi (bir necha marta urinildi): {job.video_title or 'Video'}\n\n{str(exc)}",
                )
        except Exception as notify_exc:
            logger.warning(f"[JOB {job_id}] Telegram xabari yuborilmadi: {notify_exc}")

        _cleanup_upload_dir(job_id)

        # ─── Metrics + Scheduler: cleanup on max retries failure ───
        _metrics.end_job(job_id)
        if user_id_str:
            _scheduler.release_job(user_id_str, job_id)
        _backpressure.cleanup_job(job_id)

        _log_pipeline_summary(job_id, stage_timings, pipeline_start, "FAILED (max retries)")

        raise exc

    finally:
        _release_job_lock(job_id)
        db.close()
