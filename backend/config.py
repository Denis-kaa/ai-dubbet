from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "GapirAI.uz"
    DEBUG: bool = False
    FREE_MODE: bool = False

    # Dublyaj pipeline — segment darajasidagi avtomatik QA (audio_qa.py,
    # tasks.py'ning TTS bosqichiga ulangan). Har bir segment uchun qo'shimcha
    # Whisper chaqiruvi kerak bo'lgani uchun (haqiqiy, doimiy xarajat),
    # kerak bo'lsa kodga tegmasdan o'chirish mumkin.
    ENABLE_SEGMENT_QA: bool = True
    SEGMENT_QA_THRESHOLD: float = 0.75
    # Tarjima tayyor bo'lgach, taxminiy TTS davomiyligi original segment
    # uzunligidan shu nisbatdan ko'p oshsa, bitta cheklangan qisqartirish
    # bosqichi ishga tushadi (translator.py). Avval 1.15 edi — foydalanuvchi
    # aniq talab qildi: "Hello 1 sekundda aytilsa, o'zbekchasi 1.5 sekundda
    # chiqmasin" — original video ritmiga imkon boricha yaqinroq bo'lishi
    # kerak (2026-08-12). Qattiqroq chegara ko'proq segmentni original
    # davomiylikka moslab qisqartirishga majbur qiladi, TTS pleyback tezligini
    # sun'iy o'zgartirishga (notabiiy eshitiladi) tayanish o'rniga.
    # Yana ham qattiqlashtirildi (1.08->1.03) — foydalanuvchi keyingi
    # tinglovda segmentlar orasidagi siljish ("it's a problem" 2.57 o'rniga
    # 2.58-2.59da chiqishi) hali sezilarli ekanini aytdi. Qisqa segment
    # sekinlashtirish logikasi ham butunlay olib tashlandi (synthesizer.py)
    # — endi TTS deyarli har doim tabiiy tezlikda gapiradi, siljish faqat
    # tarjima bosqichida (matn qisqartirish orqali) oldini olinadi.
    DURATION_OVERAGE_TOLERANCE: float = 1.03

    # Dynamic audio ducking (merger.py) — original audio dub gapirayotganda
    # butunlay o'chirilmaydi, faqat pasaytiriladi (kino dublyajidagi kabi).
    # sidechaincompress dub trekini "trigger" sifatida ishlatadi — original
    # qanchalik baland/past bo'lishidan qat'i nazar, moslashuvchan pasayadi.
    # threshold: sidechain (dub) shu darajadan baland bo'lsa duck ishga tushadi.
    # ratio: qanchalik kuchli pasayish. attack: duck necha ms'da boshlanadi
    # (tez — dub boshlanishi bilan sezilarli bo'lishi uchun). release: necha
    # ms'da asl holatga qaytadi (sekinroq — "pumping" effektidan qochish uchun).
    # threshold/ratio dastlab 0.05/8.0 edi — real tinglovda original ovoz
    # dub ostida hali sezilib turdi ("bilinib qoladi"). Threshold pasaytirilib
    # (past darajadagi dub ham duck'ni ishga tushiradi) va ratio oshirilib
    # (2026-08-12) original deyarli to'liq bostirilishi ta'minlandi — bu
    # foydalanuvchining aniq talabi ("ustidan dublaj qilganda bilinmasin").
    # Foydalanuvchi yana ham kuchliroq farq so'radi (2026-08-12): "fondagi
    # ovozni gapirayotganda pastlatib, dublaj ovozini ko'tarib qo'y."
    # RATIO=20 — ffmpeg'ning sidechaincompress filtri qabul qiladigan ENG
    # YUQORI qiymat (allaqachon shu chegarada edi; 30 sinab ko'rilganda
    # ffmpeg xato berdi: "Value out of range [1 - 20]" — productionda
    # haqiqiy job orqali aniqlangan). Bitta 20:1 bosqich ham yetarli
    # bo'lmadi — foydalanuvchi haqiqiy production videosini tinglab, dub
    # ostida original hali ham eshitilib, dublyaj ovozi bosilib qolayotganini
    # xabar qildi (2026-08-14). Shuning uchun merger.py'da sidechaincompress
    # IKKI marta ketma-ket qo'llaniladi (har biri shu RATIO/THRESHOLD bilan) —
    # ffmpeg'ning bitta filtrdagi [1,20] chegarasini buzmasdan, effektiv
    # bosishni chuqurlashtiradi.
    DUCKING_THRESHOLD: float = 0.012
    DUCKING_RATIO: float = 20.0
    DUCKING_ATTACK_MS: int = 5
    DUCKING_RELEASE_MS: int = 400
    # Dub trekining o'zini ham baland qilish (fonni pasaytirish bilan bir
    # qatorda) — limiterdan OLDIN qo'llaniladi, shunda hosil bo'lgan
    # cho'qqilarni limiter xavfsiz ushlab qoladi (clipping bo'lmaydi).
    VOICE_GAIN_BOOST_DB: float = 5.0
    # Dub ovoz protsessing zanjiri (merger.py): xirillashni kesish, aniqlik
    # uchun subtle boost, dinamika siqish, "s"/"sh" tovushlarini yumshatish,
    # limiter — barchasi bitta filtergraph ichida, alohida ffmpeg pass emas.
    VOICE_HIGHPASS_HZ: int = 80
    VOICE_EQ_FREQ_HZ: int = 3000
    VOICE_EQ_GAIN_DB: float = 2.5
    VOICE_COMPRESSOR_RATIO: float = 3.0
    VOICE_LIMITER_LIMIT: float = 0.95
    # Yakuniy aralashma EBU R128 standartiga normallashtiriladi (I = integrated
    # loudness, TP = true peak, LRA = loudness range).
    FINAL_LOUDNORM_I: float = -16.0
    FINAL_LOUDNORM_TP: float = -1.5
    FINAL_LOUDNORM_LRA: float = 11.0

    # Audio aralashtirish rejimi (merger.py): "dubbed_only" — faqat tarjima/
    # TTS ovozi saqlanadi (yangi default — foydalanuvchi talabi: "dub haqiqatan
    # eshitilsin"); "ducked_mix" — original + TTS sidechain ducking bilan
    # (eski kino-dublyaj rejimi, asl kod mantiqi aynan shu edi). Noto'g'ri
    # qiymat kelsa xavfsiz tarzda dubbed_only ga tushadi.
    AUDIO_MIX_MODE: str = "dubbed_only"

    # ─────────────────────────────────────────────────────────────────────
    # Chunked Pipeline — video va audio ni vaqt bo'yicha qismlarga bo'lib,
    # TTS va MERGE ni parallel ravishda bajarish (pipeline parallelism).
    # Natija: ~1.7-2x tezroq ishlash (ba'zan 3x ga yaqin GPU bilan).
    # ─────────────────────────────────────────────────────────────────────
    # Har bir chunkning davomiyligi (soniyada). 180 = 3 daqiqa.
    #kichik qiymat = ko'proq chunklar = ko'proq parallellik, lekin
    #concat xarajatlari oshadi. Optimal: 120-360 soniya.
    CHUNK_DURATION_SEC: int = 180
    # Bir vaqtda qancha chunk parallel qayta ishlanadi.
    # CPU limitations: 2 chunk = ~4 GB RAM, 3 chunk = ~6 GB RAM.
    MAX_PARALLEL_CHUNKS: int = 2
    # Chunklar orasidagi overlap (soniyada) — boundary artifacts
    # oldini olish uchun. Har bir chunk N секунd OLDINGI chunk bilan
    # overlap qiladi, keyin裁切 qilinadi.
    CHUNK_OVERLAP_SEC: float = 1.5
    # Chunked pipeline ni yoqish/o'chirish. False = eski sequential rejim.
    ENABLE_CHUNKED_PIPELINE: bool = True

    # ─────────────────────────────────────────────────────────────────────
    # NVENC GPU Encoding — NVIDIA GPU bilan tezroq video encoding.
    # Agar serverda NVENC mavjud bo'lsa, avtomatik ishlatiladi.
    # Yo'q bo'lsa — CPU (libx264) ga fallback.
    # ─────────────────────────────────────────────────────────────────────
    # NVENC ni yoqish/o'chirish. False = doimo CPU (libx264).
    ENABLE_NVENC: bool = True
    # NVENC preset: p1 (eng tez) → p7 (eng sifatli). p1 = max speed.
    NVENC_PRESET: str = "p1"
    # NVENC tune: ull (ultra low latency), ll (low latency),hq (high quality)
    NVENC_TUNE: str = "ull"
    # NVENC rate control: vbr (variable bitrate), cbr (constant)
    NVENC_RC: str = "vbr"
    # NVENC quality (cq): 0-51, past = yuqori sifat. 23 = libx264 CRF 23 ga teng.
    NVENC_CQ: int = 23

    # JWT imzolash kaliti — MAJBURIY .env orqali beriladi. Bo'sh bo'lsa
    # (yoki eski, kodda commit qilingan qiymat ishlatilsa) istalgan kishi
    # o'zi token yasab, istalgan foydalanuvchi (shu jumladan admin) nomidan
    # kira oladi — 2026-08-20 audit paytida topilgan va tuzatilgan (server
    # .env'ga haqiqiy tasodifiy qiymat qo'shildi).
    SECRET_KEY: str = ""

    # Database
    DATABASE_URL: str = "postgresql://dubber:dubber123@localhost:5432/dubber_db"
    ASYNC_DATABASE_URL: str = "postgresql+asyncpg://dubber:dubber123@localhost:5432/dubber_db"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # OpenAI
    OPENAI_API_KEY: str = ""
    # Dublajdan oldingi kontent xavfsizligi tekshiruvi (Safety Gate) —
    # backend/services/content_safety.py. Diniy/terroristik/pornografik/
    # zo'ravonlik kontentini job yaratilishidan oldin (metadata) va
    # transkripsiyadan keyin (transkript) bloklaydi.
    CONTENT_SAFETY_ENABLED: bool = True

    # Telegram bot -- @BotFather'dan olingan token. Bo'sh bo'lsa bot
    # jarayoni ishga tushmaydi va bildirishnomalar jimgina o'tkazib
    # yuboriladi (backend/services/telegram_notify.py: fail-open).
    TELEGRAM_BOT_TOKEN: str = ""
    # Tarjima uchun — gpt-4o-mini sifat jihatidan gpt-4o'ga deyarli teng
    # chiqdi (real taqqoslashda tasdiqlangan), narxi esa ~17x arzon.
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TRANSCRIPTION_MODEL: str = "whisper-1"
    # Nutq optimallashtirish (raqam/ohang moslashtirish) va jins aniqlash kabi
    # mexanik, sifatga unchalik sezgir bo'lmagan vazifalar uchun — OPENAI_MODEL
    # dan alohida saqlanadi, shunda kerak bo'lsa tarjima sifatini mustaqil
    # oshirish/pasaytirish mumkin, bu vazifalarga ta'sir qilmasdan.
    OPENAI_LIGHT_MODEL: str = "gpt-4o-mini"

    # Google AI Studio / Gemini API
    GEMINI_API_KEY: str = ""
    # Запасные ключи для ротации (AUDIT_STABILITY §6): бесплатный тариф
    # ограничивает ~20 запросов/день/ключ на модель. При 429 RESOURCE_EXHAUSTED
    # transcriber/translator автоматически переключаются на следующий ключ.
    GEMINI_API_KEY_2: str = ""
    GEMINI_API_KEY_3: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # Tarjima provayderi: "openai" | "gemini" | "claude" | "mistral" | "deepseek" | "groq"
    TRANSLATE_PROVIDER: str = "openai"
    # Fallback ketma-ketligi (vergul bilan ajratilgan)
    TRANSLATE_FALLBACK_CHAIN: str = "openai,gemini,claude,mistral,deepseek,groq,cohere"

    # Gemini native TTS (tayyor ovozlar: Autonoe, Charon va h.k.)
    GEMINI_TTS_MODEL: str = "gemini-2.5-flash-preview-tts"
    GEMINI_MALE_VOICE: str = "Charon"
    GEMINI_FEMALE_VOICE: str = "Autonoe"

    # Vertex AI orqali ulanish (AI Studio'ning "preview" modellar uchun qattiq
    # kunlik chegarasini chetlab o'tish uchun — Vertex AI daqiqalik Dynamic
    # Shared Quota ishlatadi, kunlik qattiq devor yo'q, va kerak bo'lsa
    # Google'dan rasman oshirtirish so'ralishi mumkin).
    GEMINI_USE_VERTEX: bool = False
    GCP_PROJECT_ID: str = ""
    GCP_LOCATION: str = "us-central1"
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # OpenAI (Whisper/GPT) krediti tugagan holatda transkripsiya va tarjima
    # uchun Vertex AI zaxirasi ishlatadigan matn modeli — GEMINI_MODEL'dan
    # alohida, chunki u AI Studio katalogiga mo'ljallangan va Vertex'da
    # mavjud bo'lmasligi mumkin (masalan "gemini-3.5-flash" Vertex'da 404).
    GEMINI_VERTEX_TEXT_MODEL: str = "gemini-2.5-flash"

    # ─────────────────────────────────────────────────────────────────────
    # Qo'shimcha LLM provayderlar
    # ─────────────────────────────────────────────────────────────────────
    # Anthropic Claude
    CLAUDE_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-3-5-haiku-20241022"

    # Mistral AI
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"

    # DeepSeek (arzon va tez)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # Groq (eng tez inference — LPU chip)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # Cohere (arzon va sifatli, RAG qo'llab-quvvatlaydi)
    COHERE_API_KEY: str = ""
    COHERE_MODEL: str = "command-r-plus"
    COHERE_LIGHT_MODEL: str = "command-r"

    # ─────────────────────────────────────────────────────────────────────
    # Qo'shimcha TTS provayderlar
    # ─────────────────────────────────────────────────────────────────────
    # Amazon Polly
    AWS_POLLY_ACCESS_KEY: str = ""
    AWS_POLLY_SECRET_KEY: str = ""
    AWS_POLLY_REGION: str = "us-east-1"
    AWS_POLLY_VOICE_MALE: str = "Filiz"  # O'zbek erkak ovozi
    AWS_POLLY_VOICE_FEMALE: str = "Filiz"  # O'zbek ayol ovozi

    # Google Cloud TTS
    GOOGLE_CLOUD_TTS_CREDENTIALS: str = ""
    GOOGLE_CLOUD_TTS_VOICE_MALE: str = "uz-UZ-Wavenet-A"
    GOOGLE_CLOUD_TTS_VOICE_FEMALE: str = "uz-UZ-Wavenet-B"

    # Play.ht
    PLAYHT_API_KEY: str = ""
    PLAYHT_USER_ID: str = ""
    PLAYHT_VOICE_MALE: str = ""  # Voice ID
    PLAYHT_VOICE_FEMALE: str = ""  # Voice ID

    # ─────────────────────────────────────────────────────────────────────
    # Qo'shimcha STT provayderlar
    # ─────────────────────────────────────────────────────────────────────
    # AssemblyAI
    ASSEMBLYAI_API_KEY: str = ""

    # Deepgram
    DEEPGRAM_API_KEY: str = ""

    # Azure TTS
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "eastus"
    AZURE_VOICE_NAME: str = "uz-UZ-SardorNeural"  # O'zbek erkak ovozi

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = "hr-lodex-recordings"
    AWS_REGION: str = "eu-north-1"


    # Paths
    UPLOAD_DIR: str = "./uploads"
    OUTPUT_DIR: str = "./outputs"

    # TTS Provider abstraction
    # Qiymatlar: "elevenlabs" | "azure" | "edge" | "openai" | "gemini" | "uzbekvoice" | "polly" | "playht" | "bark"
    TTS_PROVIDER: str = "edge"
    # Fallback ketma-ketligi (vergul bilan ajratilgan)
    TTS_FALLBACK_CHAIN: str = "edge,elevenlabs,azure,gemini,openai,polly,playht"
    # Asosiy provider muvaqqat xatolik bilan (timeout/429/5xx) ishlamasa shu
    # providerga o'tiladi. Doimiy xatolikda (noto'g'ri kalit/kirish) fallback
    # ishlatilmaydi — backend/services/tts/base.py: PermanentTTSError.
    TTS_FALLBACK_PROVIDER: str = "edge"

    # UzbekVoiceAI TTS (https://uzbekvoice.ai/videos/api-docs/tts)
    UZBEKVOICE_API_KEY: str = ""
    UZBEKVOICE_BASE_URL: str = "https://uzbekvoice.ai/api/v1"
    UZBEKVOICE_DEFAULT_MODEL: str = "shoira"

    # ElevenLabs TTS
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID_MALE: str = "bIHbv24MWmeRgasZH58o"    # Will (Relaxed Optimist)
    ELEVENLABS_VOICE_ID_FEMALE: str = "EXAVITQu4vr4xnSDxMaL"  # Sarah (Mature, Reassuring)
    ELEVENLABS_MODEL: str = "eleven_multilingual_v2"
    ELEVENLABS_STABILITY: float = 0.45
    ELEVENLABS_SIMILARITY_BOOST: float = 0.80
    ELEVENLABS_STYLE: float = 0.20
    ELEVENLABS_SPEED: float = 1.0
    ELEVENLABS_FALLBACK_TO_EDGE: bool = True

    # Telegram Notification Bot -- token .env orqali beriladi (yuqoridagi
    # TELEGRAM_BOT_TOKEN maydoni bilan bir xil; ilgari shu yerda ikkinchi
    # marta e'lon qilinib, haqiqiy tokenni kod ichida ochib qo'ygan edi).
    TELEGRAM_CHAT_ID: str = "-1004431243067"

    # Resend (email tasdiqlash kodlari uchun — gapirai.uz domenida SPF/DKIM tasdiqlangan)
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@gapirai.uz"
    RESEND_FROM_NAME: str = "GapirAI.uz"

    # Google bilan kirish — faqat CLIENT_ID kerak (frontend'dagi Google
    # Identity Services token beradi, backend uni shu ID orqali tekshiradi;
    # server-side auth-code almashinuvi ishlatilmagani uchun CLIENT_SECRET
    # kerak emas). Bo'sh bo'lsa, frontend tugmani ko'rsatmaydi.
    GOOGLE_CLIENT_ID: str = ""

    # Mobil ilova (mobile/) uchun ALOHIDA Android turidagi OAuth mijoz
    # (2026-08-22) — Google endi "Web application" mijozlar uchun custom-scheme
    # redirect_uri'ni (gapirai://) rad etadi ("doesn't comply with Google's
    # OAuth 2.0 policy"), shuning uchun mobil ilova o'zining Android mijozidan
    # foydalanadi. ID token'ning "aud" maydoni shu ID bo'ladi, GOOGLE_CLIENT_ID
    # (web) emas — backend/services/google_auth.py ikkalasini ham qabul qiladi.
    GOOGLE_ANDROID_CLIENT_ID: str = ""

    # Eskiz.uz SMS OTP (https://notify.eskiz.uz/api) — email+parol orqali
    # login qilib bearer token oladi (Redis'da keshlanadi, sms_service.py),
    # Resend'ning statik API key'idan farqli. Bo'sh bo'lsa, SMS yuborilmaydi
    # va foydalanuvchiga aniq xatolik qaytariladi.
    ESKIZ_EMAIL: str = ""
    ESKIZ_PASSWORD: str = ""
    ESKIZ_FROM: str = "4546"  # Eskiz sandbox/test sender nickname — productionda tasdiqlangan nom kerak

    # Admin panel — role='admin' bo'lsa ham, faqat shu ro'yxatdagi email
    # kira oladi (vergul bilan ajratilgan). Bo'sh bo'lsa, faqat role tekshiriladi.
    ADMIN_ALLOWED_EMAILS: str = "lochinbeksetor@gmail.com"

    # Click Payment
    CLICK_MERCHANT_ID: str = "56653"
    CLICK_SERVICE_ID: str = "108780"
    CLICK_SECRET_KEY: str = ""
    CLICK_MERCHANT_USER_ID: str = "89102"

    # Payme (Paycom) Payment -- Merchant API (backend/api/payme_routes.py).
    # PAYME_KEY ishlab chiqarish (checkout.paycom.uz) uchun, PAYME_TEST_KEY
    # esa pesochnitsa (test.paycom.uz) uchun -- ikkalasi ham Basic Auth
    # orqali kiruvchi so'rovlarni tekshirishda ishlatiladi.
    PAYME_MERCHANT_ID: str = ""
    PAYME_KEY: str = ""
    PAYME_TEST_KEY: str = ""
    # Kassa Payme kabinetida hali production uchun faollashtirilmagan bo'lsa
    # True qoldiring -- checkout havolalari test.paycom.uz'ga yo'naltiriladi.
    # PAYME_KEY to'ldirilgan bo'lishi kassa faollashganini ANGLATMAYDI (haqiqiy
    # checkoutda "Поставщик не найден или заблокирован" xatosi orqali
    # 2026-08-19 aniqlangan) -- shuning uchun bu alohida, qo'lda boshqariladigan
    # flag. Payme kassani production uchun tasdiqlagach, False qiling.
    PAYME_SANDBOX_MODE: bool = True

    # Uzum Bank (Merchant webhook API) -- integratsiya hali ishlab chiqilmoqda
    # (2026-08-20). Uzum bizga POST /check, /create, /confirm, /reverse,
    # /status so'rovlarini shu login/parol bilan Basic Auth orqali yuboradi
    # -- Click/Payme'dan farqli, bu qiymatlarni BIZ tanlaymiz va Uzum'ga
    # beramiz (ular bizga bermaydi). UZUM_SERVICE_ID ham shunday -- test
    # bosqichida biz belgilaymiz, keyin Uzum production ID beradi.
    UZUM_WEBHOOK_USERNAME: str = ""
    UZUM_WEBHOOK_PASSWORD: str = ""
    UZUM_SERVICE_ID: int = 1

    # Paynet (UZPAYNET) Universal Web-Service (JSON-RPC 2.0, Basic Auth) --
    # backend/api/paynet_routes.py. Xuddi Uzum kabi, login/parol va
    # serviceId'ni BIZ tanlaymiz va Paynet'ga beramiz (ular bermaydi).
    PAYNET_USERNAME: str = ""
    PAYNET_PASSWORD: str = ""
    PAYNET_SERVICE_ID: int = 1

    FRONTEND_URL: str = "https://gapirai.uz"

    # yt-dlp orqali YouTube'dan yuklab olishda ishlatiladigan HTTP(S) proxy —
    # http://user:pass@host:port. Butunlay IXTIYORIY — AWS/GCP kabi datacenter
    # IP'larni YouTube ko'pincha bot deb belgilab, PO token/cookie holatidan
    # qat'iy nazar "Video unavailable" qaytaradi (2026-08-12 productionda
    # tasdiqlangan); bo'sh/false bo'lsa to'g'ridan-to'g'ri ulanishga tushadi
    # (lokal/rezident IP yoki PO token o'zi yetarli bo'lsa kerak emas).
    # Standart qiymat False — production o'z .env faylida buni aniq "true"
    # deb belgilaydi, shuning uchun bu yerdagi standart faqat local/dev uchun.
    # ENABLED alohida flag — provayderda muammo chiqsa (masalan 2026-08-22
    # Webshare balansi tugagan real hodisa), URL'ni o'chirmasdan tezda
    # proxysiz rejimga qaytarish uchun.
    YOUTUBE_PROXY_ENABLED: bool = False
    YOUTUBE_PROXY_URL: str = ""

    # Ikkinchi (zaxira) proksi — residential, YOUTUBE_PROXY_URL (datacenter,
    # tezkor) bot-check xatosiga uchraganda ishlatiladi. Datacenter proksi
    # tez lekin ko'proq bloklanadi; residential sekin (~1.9 Mbps, 2026-08-13
    # o'lchangan) lekin YouTube uni oddiy foydalanuvchi deb hisoblaydi.
    # Aksariyat so'rovlar datacenter orqali muvaffaqiyatli o'tadi — residential
    # faqat zaxira sifatida, cheklangan trafik hajmini tejash uchun.
    YOUTUBE_RESIDENTIAL_PROXY_URL: str = ""

    # YouTube Data API v3 (https://console.cloud.google.com) -- video metadata
    # (sarlavha/davomiylik/thumbnail) olishda yt-dlp skrapping o'rniga rasman
    # API ishlatiladi, bot-check xavfisiz. Bo'sh bo'lsa, eski yt-dlp yo'liga
    # tushadi. Faqat METADATA uchun -- video faylining o'zini yuklab olish
    # (dublyaj uchun) hamon yt-dlp orqali, chunki Data API video oqimini
    # bermaydi (2026-08-20, rezident proksi balansi tugagach qo'shildi).
    YOUTUBE_DATA_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
