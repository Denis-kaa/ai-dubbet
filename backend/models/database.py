from sqlalchemy import create_engine, Column, String, DateTime, Enum, Float, Integer, Text, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
import enum
from datetime import datetime
from backend.config import get_settings

settings = get_settings()

engine = create_engine(settings.DATABASE_URL, pool_size=3, max_overflow=2)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    DOWNLOADING = "DOWNLOADING"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSLATING = "TRANSLATING"
    SYNTHESIZING = "SYNTHESIZING"
    SYNCING = "SYNCING"
    MERGING = "MERGING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    # Progressive playback uchun yangi holatlar
    SPLITTING = "SPLITTING"           # Video chunk'larga bo'linmoqda
    PROCESSING_CHUNKS = "PROCESSING_CHUNKS"  # Chunk'lar parallel qayta ishlanmoqda
    PARTIALLY_READY = "PARTIALLY_READY"  # Birinchi chunk tayyor, playback mumkin
    PUBLISHING = "PUBLISHING"         # HLS segmentlar publish qilinmoqda


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Google yoki telefon orqali ro'yxatdan o'tgan foydalanuvchida email
    # bo'lmasligi mumkin (telefon-only) yoki parol bo'lmasligi mumkin
    # (Google/telefon-only) — shuning uchun ikkalasi ham nullable.
    email = Column(String(255), unique=True, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    # Telegram bot orqali ulangan bo'lsa to'ldiriladi (backend/telegram_bot.py)
    # -- job yakunlanganda foydalanuvchiga shu chat'ga xabar yuborish uchun.
    # Bir xil telefon raqami web'da ham ishlatilgan bo'lsa, xuddi shu
    # hisobga bog'lanadi (auth_routes.py'dagi phone auth bilan bir xil
    # ustun) -- kvota/obuna ikkalasida ham baravar ishlaydi.
    telegram_chat_id = Column(String(50), unique=True, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    # Uch xil auth usuli ham shu bitta flag orqali ishonch bildiradi — email
    # kodi, Google (email_verified=true bo'lsa avtomatik), yoki telefon kodi.
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_code = Column(String(6))
    verification_code_expires_at = Column(DateTime)
    phone_verification_code = Column(String(6))
    phone_verification_code_expires_at = Column(DateTime)
    # Faqat ma'lumot uchun — hech qanday kod bu maydonga qarab tarmoqlanmaydi.
    auth_provider = Column(String(20), nullable=False, default="password")  # "password" | "google" | "phone"
    role = Column(String(20), nullable=False, default="user")  # "user" | "admin"
    created_at = Column(DateTime, default=datetime.utcnow)
    # 2026-08-19: bir martalik to'lov -- Ommaviy videolar (/library)
    # kutubxonasiga umrbod kirish, tarif kvotasidan mustaqil.
    library_access_purchased_at = Column(DateTime, nullable=True)

    jobs = relationship("DubbingJob", back_populates="user", lazy="dynamic")


class DubbingJob(Base):
    __tablename__ = "dubbing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)  # list_jobs/dashboard shu ustun bo'yicha filtrlanadi
    youtube_url = Column(String(500), nullable=False)
    youtube_video_id = Column(String(20), nullable=True, index=True)  # kesh qidiruvi uchun (backend/services/job_creation.py)
    source_job_id = Column(UUID(as_uuid=True), ForeignKey("dubbing_jobs.id"), nullable=True)  # kesh-hit -- asl job'ga ishora
    video_title = Column(String(500))
    video_duration = Column(Float)
    video_thumbnail = Column(String(500))
    speaker_gender = Column(String(10))       # GPT aniqlagan: male / female
    voice_gender_setting = Column(String(10), default="auto")  # foydalanuvchi tanlagan: auto/male/female
    # Per-job audio mode: dubbed_only or ducked_mix. Nullable for old jobs;
    # new requests always persist an explicit value.
    audio_mix_mode = Column(String(20), nullable=True)
    status = Column(Enum(JobStatus, values_callable=lambda obj: [e.value for e in obj]), default=JobStatus.PENDING, nullable=False)
    progress = Column(Float, default=0.0)
    status_message = Column(String(255))

    transcript_text = Column(Text)
    translated_text = Column(Text)
    srt_content = Column(Text)
    uzbek_srt_content = Column(Text)   # O'zbekcha subtitrlar (WebVTT format)

    # Checkpoint uchun: har bosqichning xom (timestamp'li) segment ro'yxati.
    # Pipeline qayta ishga tushganda (crash/retry) shu maydonlar orqali
    # qaysi bosqichlar allaqachon bajarilganini bilib, ulardan o'tkazib
    # yuboriladi — qimmat/uzoq bosqichlar (transkripsiya, tarjima, LLM
    # nutq optimizatsiyasi) qayta bajarilmaydi.
    transcript_segments = Column(JSONB, nullable=True)
    translated_segments = Column(JSONB, nullable=True)
    speech_segments = Column(JSONB, nullable=True)

    # Har bir TTS segmentining avtomatik QA natijasi (audio_qa.py):
    # {seg_id: {"score": float, "flags": [...], "attempts": int}}. Celery
    # qayta urinishida synthesize_segments() shu maydonga qarab faqat
    # muvaffaqiyatsiz/yo'q segmentlarnigina qayta sintez qiladi — butun TTS
    # bosqichini emas.
    segment_qa = Column(JSONB, nullable=True)

    original_video_path = Column(String(500))
    dubbed_audio_path = Column(String(500))
    output_video_path = Column(String(500))
    output_video_url = Column(String(500))

    # Progressive playback uchun qo'shimcha maydonlar
    hls_playlist_url = Column(String(500), nullable=True)  # HLS playlist URL
    chunks_ready = Column(Integer, default=0)  # Tayyor chunk'lar soni
    chunks_total = Column(Integer, default=0)  # Jami chunk'lar soni
    first_playable_at = Column(DateTime, nullable=True)  # Birinchi chunk tayyor bo'lgan vaqt

    error_message = Column(Text)
    error_code = Column(String(50), nullable=True)  # masalan: VIDEO_UNAVAILABLE, TRANSCRIBE_FAILED, TIMEOUT
    # 2026-08-19: shu job uchun tarif kvotasi sarflanganmi (consume_quota
    # chaqirilganmi) -- pipeline 5 marta urinib ham muvaffaqiyatsiz tugasa,
    # backend/workers/tasks.py shu bayroqqa qarab kvotani avtomatik qaytaradi.
    quota_consumed = Column(Boolean, default=False, nullable=False)
    # 2026-08-19: Safety Gate ogohlantirish (blocklamaydi, lekin kategoriya
    # topilgan) bergan bo'lsa true -- frontend foydalanuvchiga "video tayyor,
    # lekin ommaviy kutubxonaga chiqarilmaydi" xabarini shu orqali ko'rsatadi.
    content_flagged = Column(Boolean, default=False, nullable=False)
    rating = Column(Integer, nullable=True)
    feedback_comment = Column(Text, nullable=True)
    feedback_created_at = Column(DateTime, nullable=True)
    feedback_voice_ok = Column(Boolean, nullable=True)
    feedback_translation_ok = Column(Boolean, nullable=True)
    feedback_speed_ok = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="jobs")

    @property
    def storage_id(self) -> str:
        """S3 kalitlari qaysi job ID ostida saqlanganini aniqlaydi -- kesh-hit
        joblar uchun bu ASL job'ning ID'si (source_job_id), oddiy joblar
        uchun o'zining ID'si. Barcha S3 kalit hisoblovchi kod (routes.py
        download endpointlari, resolution_variants.py) shu propertydan
        foydalanadi, job.id'dan emas.

        job_creation.py'dagi kesh qidiruvi ilgari ENG SO'NGGI tugagan mos
        job'ni tanlar edi -- bu kesh-hit BOSHQA kesh-hitga ishora qilib,
        zanjir hosil bo'lishiga olib kelardi (bitta video uchun 13 bosqichgacha
        kuzatilgan, 2026-08-21). Kesh-hit job'larning o'zi HECH QACHON S3'ga
        fayl yuklamaydi, shuning uchun zanjirning istalgan oraliq bo'g'ini
        "storage_id" sifatida ishlatilsa doim mavjud bo'lmagan kalitga olib
        keladi. Yozish tomoni (job_creation.py) endi to'g'ridan-to'g'ri asl
        ildizga ishora qiladi, lekin bazadagi eski zanjirlar davolanishi
        uchun bu yerda ham to'liq zanjir bosib o'tiladi (aylanma himoya
        bilan)."""
        from sqlalchemy.orm import object_session

        seen = {str(self.id)}
        current = self
        for _ in range(50):
            if not current.source_job_id:
                return str(current.id)
            next_id = str(current.source_job_id)
            if next_id in seen:
                return str(current.id)
            seen.add(next_id)
            session = object_session(self)
            if session is None:
                return next_id
            nxt = session.get(DubbingJob, current.source_job_id)
            if nxt is None:
                return next_id
            current = nxt
        return str(current.id)


class AnalysisStatus(str, enum.Enum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    EXTRACTING_AUDIO = "EXTRACTING_AUDIO"
    TRANSCRIBING = "TRANSCRIBING"
    ANALYZING = "ANALYZING"
    GENERATING_RESULTS = "GENERATING_RESULTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VideoAnalysis(Base):
    """YouTube video -> transcript/summary/chapters/key-points/notes/quiz/Q&A.

    Bir marta transkripsiya va bazaviy tahlil qilinadi (transcript_segments,
    key_points, chapters); notes/quiz esa so'ralganda "lazy" generatsiya
    qilinib shu yerga keshlanadi — har safar qayta hisoblanmaydi
    (backend/api/video_analysis_routes.py).
    """
    __tablename__ = "video_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    youtube_url = Column(String(500), nullable=False)
    video_title = Column(String(500))
    video_duration = Column(Float)
    video_thumbnail = Column(String(500))
    # "language" — foydalanuvchi so'ragan tahlil tili (uz/en/ru/tr/kk yoki "original").
    # "original" video transkripsiyadan keyin aniqlangan video_language'ga hal qilinadi
    # (backend/workers/analysis_tasks.py) va shu yerga qayta yoziladi — shundan keyin
    # quiz/notes/Q&A kabi "lazy" endpointlar uni qayta hal qilmasdan to'g'ridan-to'g'ri ishlatadi.
    language = Column(String(10), default="uz")
    video_language = Column(String(10), nullable=True)  # Whisper aniqlagan original til kodi

    status = Column(Enum(AnalysisStatus, values_callable=lambda obj: [e.value for e in obj]), default=AnalysisStatus.PENDING, nullable=False)
    progress = Column(Float, default=0.0)
    status_message = Column(String(255))

    # [{"start": float, "end": float, "text": str}, ...] — transcriber.py bilan bir xil shakl
    transcript_segments = Column(JSONB, nullable=True)

    summary = Column(JSONB, nullable=True)        # {"short": str, "medium": str, "detailed": str}
    key_points = Column(JSONB, nullable=True)      # [{"title","description","timestamp"}]
    chapters = Column(JSONB, nullable=True)        # [{"title","start","end"}]
    notes = Column(Text, nullable=True)
    quiz = Column(JSONB, nullable=True)            # [{"question","options","correct_answer","explanation","timestamp"}]
    qa_history = Column(JSONB, default=list)       # [{"question","answer","timestamps","asked_at"}]
    bilingual_segments = Column(JSONB, nullable=True)  # [{"start","end","original","translated"}] — lazy

    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User")


class PronunciationMemory(Base):
    """
    O'rganilgan talaffuz tuzatishlari: term -> Azure/Edge TTS uchun og'zaki shakl.
    Static PRONUNCIATION_DICT'ni ustidan yozadi (backend/services/speech_optimizer.py).
    Hozircha faqat o'qish uchun ishlatiladi; yozish yo'li (avtomatik yoki qo'lda
    talaffuz QA'sidan) keyingi bosqichda qo'shiladi.
    """
    __tablename__ = "pronunciation_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term = Column(String(255), unique=True, nullable=False, index=True)
    spoken_form = Column(String(500), nullable=False)
    source = Column(String(20), default="manual")  # manual | qa_auto
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TTSUsageLog(Base):
    """Har bir muvaffaqiyatli TTS sintez chaqiruvi uchun xarajat yozuvi.

    Maqsad: "1 daqiqa dublyaj qilingan video bizga qancha tushadi" savoliga
    provider bo'yicha aniq javob berish (backend/services/tts_cost.py).
    currency provider bo'yicha farqlanadi (uzbekvoice -> UZS, qolganlari -> USD)
    — sun'iy almashtirish kursi bilan bitta valyutaga majburan keltirilmaydi;
    agregatsiya (provider, currency) bo'yicha guruhlanadi.
    """
    __tablename__ = "tts_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(30), nullable=False, index=True)
    characters = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=True)  # generatsiya qilingan audio uzunligi
    estimated_cost = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    video_id = Column(String(64), nullable=True, index=True)  # DubbingJob yoki VideoAnalysis id (FK emas — ikkalasidan ham bo'lishi mumkin)
    user_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    # True bo'lsa, bu yozuv TTSCache'dan qaytarilgan (haqiqiy sintez bo'lmagan,
    # estimated_cost=0) — xarajat hisobotida keshning ta'sirini ko'rish uchun.
    cache_hit = Column(Boolean, nullable=False, default=False)


class TTSCache(Base):
    """Segment darajasidagi TTS audio keshi — bir xil matn+ovoz+provider
    kombinatsiyasi qayta sintez qilinmasdan S3'dagi mavjud audio qaytariladi
    (backend/services/tts_cache.py). Lokal diskda emas — job tugagach mahalliy
    fayllar o'chiriladi (tasks.py), shuning uchun kesh S3'da yashashi shart.
    """
    __tablename__ = "tts_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cache_key = Column(String(64), unique=True, nullable=False, index=True)  # sha256(text+voice+provider)
    provider = Column(String(30), nullable=False)
    s3_key = Column(String(500), nullable=False)
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlanTier(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"


class Subscription(Base):
    """Foydalanuvchining oylik tarif obunasi. Har bir userda ko'pi bilan bitta
    qator bo'ladi (user_id unique) — tarif o'zgartirilganda shu qator yangilanadi,
    yangi qator ochilmaydi. Aniq tarif ta'riflari (narx/kvota) bazada emas,
    backend/services/plans.py'dagi PLANS lug'atida — bu jadval faqat "kim qaysi
    tarifda va qachongacha" holatini saqlaydi.

    Hech qanday qator yo'q foydalanuvchi = FREE tarifda (lazy — birinchi
    kvota tekshiruvida avtomatik yaratiladi, PronunciationMemory'dagi kabi).
    """
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    plan = Column(Enum(PlanTier, values_callable=lambda obj: [e.value for e in obj]), default=PlanTier.FREE, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # FREE uchun null (muddatsiz)
    period_started_at = Column(DateTime, default=datetime.utcnow)  # joriy davr kvotasi shu vaqtdan hisoblanadi
    videos_used_this_period = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")


class ResolutionVariant(Base):
    """Video ma'lumot bazasida rezolyutsiya kesimidagi versiyalar --
    360p/1080p bosqichma-bosqich, faqat haqiqatan so'ralganda yaratiladi
    (backend/services/resolution_variants.py). 720p uchun qator yaratilmaydi
    -- u allaqachon master fayl (dubber/{job_id}/dubbed_final.mp4)."""
    __tablename__ = "resolution_variants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("dubbing_jobs.id"), nullable=False, index=True)
    resolution = Column(String(10), nullable=False)  # "360p" | "1080p"
    status = Column(String(20), default="pending")   # pending|processing|ready|failed
    s3_key = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("job_id", "resolution"),)


class ContentViolation(Base):
    """Safety Gate tomonidan bloklangan har bir urinish shu yerda saqlanadi
    (backend/services/content_safety.py). Ikki bosqichdan biri belgilaydi:
    "metadata" (job yaratilishidan oldin, sarlavha/tavsif asosida) yoki
    "transcript" (transkripsiyadan keyin, videoning haqiqiy nutqi asosida).
    Admin panelda foydalanuvchi bo'yicha guruhlab ko'rsatiladi -- "bloklangan
    akkauntlar soni va kimligi" talabiga javob beradi."""
    __tablename__ = "content_violations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    youtube_url = Column(String(500), nullable=False)
    video_title = Column(String(500))
    stage = Column(String(20), nullable=False)  # "metadata" | "transcript"
    category = Column(String(50), nullable=False)
    reason = Column(Text)
    blocked = Column(Boolean, default=True, nullable=False)  # False = faqat ogohlantirish, video bloklanmadi (2026-08-16)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    # 2026-08-19: bu yerda ilgari o'nlab bir martalik "ALTER TABLE ... ADD
    # COLUMN IF NOT EXISTS" iboralari bor edi -- ularning BARCHASI allaqachon
    # qo'llanilgan (tekshirilgan: barcha ustun/indekslar production'da
    # mavjud). Har biri ACCESS EXCLUSIVE qulf talab qilardi va backend HAR
    # safar qayta ishga tushganda ishga tushardi -- agar shu payt boshqa
    # birorta ulanish (masalan Celery worker) dubbing_jobs'da ochiq
    # tranzaksiyaga ega bo'lsa, bu butun saytni bir necha daqiqaga
    # to'xtatib qo'yardi (2026-08-19 kechasi bir necha marta shu tarzda
    # tanaffus bo'ldi -- ildiz sababi shu edi). Yangi ustun kerak bo'lsa,
    # bir martalik `ALTER TABLE` to'g'ridan-to'g'ri production DB'da qo'lda
    # bajariladi (bu funksiyaga umuman qo'shilmaydi).
    Base.metadata.create_all(bind=engine)
