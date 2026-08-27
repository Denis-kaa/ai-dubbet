import time
from pathlib import Path
from datetime import datetime
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from backend.workers.celery_app import celery_app
from backend.workers.tasks import _record_stage, _log_pipeline_summary, _error_code_for, _cleanup_upload_dir
from backend.models.database import SessionLocal, VideoAnalysis, AnalysisStatus
from backend.services import downloader, transcriber
from backend.services.video_analysis import VideoAnalysisService, normalize_video_language
from backend.services.errors import PermanentError
from backend.config import get_settings

logger = get_task_logger(__name__)
settings = get_settings()
_service = VideoAnalysisService()


def _update_analysis(db, analysis: VideoAnalysis, status: AnalysisStatus, progress: float, message: str):
    analysis.status = status
    analysis.progress = progress
    analysis.status_message = message
    analysis.updated_at = datetime.utcnow()
    db.commit()


@celery_app.task(
    bind=True,
    name="backend.workers.analysis_tasks.analyze_video_task",
    max_retries=5,
    default_retry_delay=60,
    soft_time_limit=2400,  # 40 daqiqa
    time_limit=2700,       # 45 daqiqa
)
def analyze_video_task(self: Task, analysis_id: str) -> dict:
    db = SessionLocal()
    stage_timings: dict = {}
    pipeline_start = time.monotonic()
    current_stage = "INIT"

    try:
        analysis = db.query(VideoAnalysis).filter(VideoAnalysis.id == analysis_id).first()
        if not analysis:
            raise ValueError(f"Analysis topilmadi: {analysis_id}")

        # video-analysis o'zining uploads/ papkasini dublyajnikidan alohida
        # ushlaydi (bir xil job_id ehtimoli yo'q — UUID) — shuning uchun
        # downloader.download_video()ga alohida "job_id" sifatida uzatiladi.
        job_dir = Path(settings.UPLOAD_DIR) / analysis_id

        # BOSQICH 1: Yuklash (mavjud dublyaj pipeline'idan qayta foydalanish)
        current_stage = "DOWNLOAD"
        stage_t0 = time.monotonic()
        audio_path = str(job_dir / "audio.wav")
        if Path(audio_path).exists():
            _record_stage(stage_timings, analysis_id, "DOWNLOAD", stage_t0, "skipped")
        else:
            _update_analysis(db, analysis, AnalysisStatus.DOWNLOADING, 10.0, "YouTube'dan yuklanmoqda...")
            download_result = downloader.download_video(analysis.youtube_url, analysis_id)
            analysis.video_title = analysis.video_title or download_result["title"]
            analysis.video_duration = analysis.video_duration or download_result["duration"]
            db.commit()
            audio_path = download_result["audio_path"]
            _record_stage(stage_timings, analysis_id, "DOWNLOAD", stage_t0, "ok")

        # BOSQICH 2: Transkripsiya (mavjud transcriber.py'dan qayta foydalanish)
        # Checkpoint: transcript_segments allaqachon saqlangan bo'lsa, qimmat
        # Whisper chaqiruvi qayta bajarilmaydi.
        current_stage = "TRANSCRIBE"
        stage_t0 = time.monotonic()
        if analysis.transcript_segments:
            _record_stage(stage_timings, analysis_id, "TRANSCRIBE", stage_t0, "skipped")
        else:
            _update_analysis(db, analysis, AnalysisStatus.TRANSCRIBING, 35.0, "Nutq matnga aylantirilmoqda...")
            transcript = transcriber.transcribe_audio(audio_path)
            if not transcript["segments"] or not transcriber.has_speech(transcript["segments"]):
                _record_stage(stage_timings, analysis_id, "TRANSCRIBE", stage_t0, "error", "nutq topilmadi")
                raise PermanentError("Bu videoda nutq topilmadi.", code="NO_SPEECH_FOUND")
            analysis.transcript_segments = transcript["segments"]
            analysis.video_language = normalize_video_language(transcript.get("language"))
            db.commit()
            _record_stage(stage_timings, analysis_id, "TRANSCRIBE", stage_t0, "ok")

        # "Original" tahlil tili tanlangan bo'lsa, endi video tili ma'lum (yo hozir
        # aniqlandi, yo oldingi urinishdan saqlangan) — shu tilga hal qilamiz va
        # qayta yozamiz, shunda quiz/notes/Q&A kabi keyingi "lazy" endpointlar buni
        # qayta hal qilmasdan to'g'ridan-to'g'ri ishlatadi (video_analysis_routes.py).
        if analysis.language == "original":
            analysis.language = analysis.video_language or "en"
            db.commit()

        segments = analysis.transcript_segments

        # BOSQICH 3: Bazaviy tahlil (xulosa, asosiy fikrlar, chapterlar)
        # Checkpoint: uchalasi ham allaqachon mavjud bo'lsa qayta hisoblanmaydi.
        # notes/quiz BU YERDA generatsiya qilinmaydi — ular "lazy" (faqat
        # foydalanuvchi so'raganda, video_analysis_routes.py orqali), chunki
        # ko'p foydalanuvchi ularni umuman so'ramasligi mumkin (xarajatni
        # nazorat qilish — bugungi sessiyaning asosiy mavzusi).
        current_stage = "ANALYZE"
        stage_t0 = time.monotonic()
        if analysis.summary and analysis.key_points and analysis.chapters:
            _record_stage(stage_timings, analysis_id, "ANALYZE", stage_t0, "skipped")
        else:
            _update_analysis(db, analysis, AnalysisStatus.ANALYZING, 70.0, "AI tahlil qilinmoqda...")
            analysis.summary = _service.generate_summary(segments, analysis.language)
            analysis.key_points = _service.generate_key_points(segments, analysis.language)
            analysis.chapters = _service.generate_chapters(segments, analysis.video_duration or 0.0, analysis.language)
            db.commit()
            _record_stage(stage_timings, analysis_id, "ANALYZE", stage_t0, "ok")

        _update_analysis(db, analysis, AnalysisStatus.COMPLETED, 100.0, "Tahlil tayyor!")
        analysis.completed_at = datetime.utcnow()
        db.commit()

        _cleanup_upload_dir(analysis_id)
        _log_pipeline_summary(analysis_id, stage_timings, pipeline_start, "COMPLETED")

        return {"analysis_id": analysis_id, "status": "completed"}

    except PermanentError as exc:
        db.query(VideoAnalysis).filter(VideoAnalysis.id == analysis_id).update({
            "status": AnalysisStatus.FAILED,
            "error_message": str(exc),
            "error_code": _error_code_for(exc, current_stage),
            "updated_at": datetime.utcnow(),
        })
        db.commit()
        _cleanup_upload_dir(analysis_id)
        _log_pipeline_summary(analysis_id, stage_timings, pipeline_start, "FAILED (permanent)")
        raise exc

    except Exception as exc:
        if self.request.retries < self.max_retries:
            # backend/workers/tasks.py'dagi bir xil sabab bilan 600s'gacha oshirilgan.
            countdown = min(600, 30 * (2 ** self.request.retries))
            analysis = db.query(VideoAnalysis).filter(VideoAnalysis.id == analysis_id).first()
            if analysis:
                analysis.status_message = f"Vaqtinchalik xatolik (qayta urinish {self.request.retries + 1}/{self.max_retries})..."
                analysis.error_message = str(exc)
                analysis.updated_at = datetime.utcnow()
                db.commit()
            db.close()
            _log_pipeline_summary(analysis_id, stage_timings, pipeline_start, f"RETRY {self.request.retries + 1}/{self.max_retries}")
            raise self.retry(exc=exc, countdown=countdown)

        db.query(VideoAnalysis).filter(VideoAnalysis.id == analysis_id).update({
            "status": AnalysisStatus.FAILED,
            "error_message": "Videoni tahlil qilishda xatolik yuz berdi. Iltimos, birozdan keyin qayta urinib ko'ring.",
            "error_code": _error_code_for(exc, current_stage),
            "updated_at": datetime.utcnow(),
        })
        db.commit()
        logger.error(f"[{analysis_id}] ANALYZE FAILED (real error): {exc}")
        _cleanup_upload_dir(analysis_id)
        _log_pipeline_summary(analysis_id, stage_timings, pipeline_start, "FAILED")
        raise exc

    finally:
        db.close()
