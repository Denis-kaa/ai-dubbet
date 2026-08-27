import asyncio
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db, VideoAnalysis, AnalysisStatus, User
from backend.services.downloader import get_video_info
from backend.services.auth import get_current_user
from backend.services.video_analysis import VideoAnalysisService
from backend.services.rate_limiter import rate_limit
from backend.workers.analysis_tasks import analyze_video_task
from backend.api.routes import _is_valid_youtube_url, MAX_VIDEO_DURATION_MINUTES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-analysis", tags=["video-analysis"])
_service = VideoAnalysisService()

# Foydalanuvchi tanlashi mumkin bo'lgan tahlil tillari + "original" — bu holda
# tahlil tili transkripsiyadan keyin aniqlangan video tiliga hal qilinadi
# (backend/workers/analysis_tasks.py). Video o'zi qaysi tilda bo'lishidan
# qat'iy nazar, transkript doim original tilda qoladi — faqat tahlil
# (summary/key_points/chapters/notes/quiz) shu tanlangan tilda chiqadi.
ALLOWED_ANALYSIS_LANGUAGES = {"uz", "en", "ru", "tr", "kk", "original"}


class CreateAnalysisRequest(BaseModel):
    youtube_url: str
    language: str = "uz"


class QuestionRequest(BaseModel):
    question: str


def _get_owned_analysis(analysis_id: str, db: Session, current_user: User) -> VideoAnalysis:
    analysis = db.query(VideoAnalysis).filter(VideoAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Tahlil topilmadi.")
    if analysis.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu tahlilga kirish huquqingiz yo'q.")
    return analysis


def _analysis_to_dict(analysis: VideoAnalysis) -> dict:
    raw_status = analysis.status.value if hasattr(analysis.status, "value") else analysis.status
    return {
        "id": str(analysis.id),
        "status": str(raw_status).lower() if raw_status else "pending",
        "progress": analysis.progress or 0.0,
        "status_message": analysis.status_message,
        "youtube_url": analysis.youtube_url,
        "video_title": analysis.video_title,
        "video_duration": analysis.video_duration,
        "video_thumbnail": analysis.video_thumbnail,
        "language": analysis.language,
        "video_language": analysis.video_language,
        "summary": analysis.summary,
        "key_points": analysis.key_points,
        "chapters": analysis.chapters,
        "notes": analysis.notes,
        "quiz": analysis.quiz,
        "qa_history": analysis.qa_history or [],
        "error_message": analysis.error_message,
        "error_code": analysis.error_code,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }


@router.post("", status_code=201, dependencies=[Depends(rate_limit("video_analysis_create", 8, 600))])
async def create_analysis(
    request: CreateAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not _is_valid_youtube_url(request.youtube_url):
        raise HTTPException(status_code=400, detail="Faqat YouTube URL qabul qilinadi.")

    if request.language not in ALLOWED_ANALYSIS_LANGUAGES:
        raise HTTPException(status_code=400, detail="Noto'g'ri tahlil tili.")

    try:
        # Thread'da ishga tushiriladi — get_video_info bloklovchi (yt-dlp
        # tarmoq so'rovlari + bot-check qayta urinishlarida time.sleep),
        # to'g'ridan-to'g'ri await qilinsa butun asyncio event loop'ni to'sib
        # qo'yadi (backend/api/routes.py'da xuddi shu sababdan tuzatilgan).
        info = await asyncio.to_thread(get_video_info, request.youtube_url)
    except Exception as e:
        logger.exception(f"video_info xato (tahlil): {request.youtube_url}")
        raise HTTPException(status_code=400, detail="Video ma'lumotlarini olib bo'lmadi. Havola to'g'riligini tekshiring yoki birozdan so'ng qaytadan urinib ko'ring.")

    duration_minutes = info.get("duration", 0) / 60.0
    if duration_minutes > MAX_VIDEO_DURATION_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=f"Video juda uzun ({duration_minutes:.0f} daqiqa). Maksimal ruxsat etilgan davomiylik — {MAX_VIDEO_DURATION_MINUTES} daqiqa.",
        )

    analysis = VideoAnalysis(
        user_id=current_user.id,
        youtube_url=request.youtube_url,
        video_title=info.get("title"),
        video_duration=info.get("duration"),
        video_thumbnail=info.get("thumbnail"),
        language=request.language,
        status=AnalysisStatus.PENDING,
        progress=0.0,
        status_message="Navbatga qo'shildi",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    analyze_video_task.apply_async(args=[str(analysis.id)], task_id=str(analysis.id))

    return {"analysis_id": str(analysis.id), "status": "pending"}


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    return _analysis_to_dict(analysis)


@router.get("/{analysis_id}/transcript")
def get_transcript(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    return {"segments": analysis.transcript_segments or []}


@router.get("/{analysis_id}/chapters")
def get_chapters(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    return {"chapters": analysis.chapters or []}


@router.post("/{analysis_id}/question", dependencies=[Depends(rate_limit("video_analysis_question", 20, 600))])
def ask_question(
    analysis_id: str,
    request: QuestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    if analysis.status != AnalysisStatus.COMPLETED or not analysis.transcript_segments:
        raise HTTPException(status_code=400, detail="Tahlil hali tayyor emas.")
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Savol bo'sh bo'lishi mumkin emas.")

    qa_history = analysis.qa_history or []
    result = _service.answer_question(
        analysis.transcript_segments, request.question.strip(), qa_history
    )
    entry = {
        "question": request.question.strip(),
        "answer": result["answer"],
        "timestamps": result["timestamps"],
        "asked_at": datetime.utcnow().isoformat(),
    }
    analysis.qa_history = qa_history + [entry]
    db.commit()
    return entry


@router.post("/{analysis_id}/quiz")
def get_or_generate_quiz(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    if analysis.status != AnalysisStatus.COMPLETED or not analysis.transcript_segments:
        raise HTTPException(status_code=400, detail="Tahlil hali tayyor emas.")
    if not analysis.quiz:
        analysis.quiz = _service.generate_quiz(analysis.transcript_segments, analysis.language)
        db.commit()
    return {"quiz": analysis.quiz}


@router.post("/{analysis_id}/bilingual")
def get_or_generate_bilingual(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    if analysis.status != AnalysisStatus.COMPLETED or not analysis.transcript_segments:
        raise HTTPException(status_code=400, detail="Tahlil hali tayyor emas.")
    if not analysis.bilingual_segments:
        if analysis.video_language and analysis.video_language == analysis.language:
            # Tahlil tili video tili bilan bir xil — tarjima ma'nosiz, LLM
            # chaqiruvisiz original matnni ikkalasi sifatida qaytaramiz.
            analysis.bilingual_segments = [
                {"start": s.get("start", 0.0), "end": s.get("end", 0.0), "original": s.get("text", ""), "translated": s.get("text", "")}
                for s in analysis.transcript_segments
            ]
        else:
            analysis.bilingual_segments = _service.generate_bilingual_segments(analysis.transcript_segments, analysis.language)
        db.commit()
    return {"segments": analysis.bilingual_segments}


@router.post("/{analysis_id}/notes")
def get_or_generate_notes(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    if analysis.status != AnalysisStatus.COMPLETED or not analysis.transcript_segments:
        raise HTTPException(status_code=400, detail="Tahlil hali tayyor emas.")
    if not analysis.notes:
        analysis.notes = _service.generate_notes(analysis.transcript_segments, analysis.language)
        db.commit()
    return {"notes": analysis.notes}


@router.get("/{analysis_id}/search")
def search_transcript(
    analysis_id: str,
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = _get_owned_analysis(analysis_id, db, current_user)
    query = q.strip().lower()
    if not query:
        return {"results": []}
    results = [
        seg for seg in (analysis.transcript_segments or [])
        if query in (seg.get("text") or "").lower()
    ]
    return {"results": results}
