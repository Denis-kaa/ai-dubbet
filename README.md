# AI Dubber 🎬

YouTube videolarini **sun'iy intellekt** yordamida avtomatik ravishda o'zbek tiliga dublyaj qilish platformasi.

---

## Mundarija

- [Loyiha haqida](#loyiha-haqida)
- [Arxitektura](#arxitektura)
- [Texnologiyalar](#texnologiyalar)
- [AI Pipeline](#ai-pipeline)
- [Papkalar strukturasi](#papkalar-strukturasi)
- [O'rnatish](#ornatish)
- [Ishga tushirish](#ishga-tushirish)
- [API dokumentatsiya](#api-dokumentatsiya)
- [Production uchun](#production-uchun)
- [Konfiguratsiya](#konfiguratsiya)

---

## Loyiha haqida

**AI Dubber** — foydalanuvchi YouTube linkini yuboradi, tizim esa to'liq avtomatik tarzda:

1. Videoni yuklab oladi
2. Inglizcha nutqni matnga aylantiradi (STT)
3. O'zbek tiliga tarjima qiladi (GPT-4o)
4. O'zbekcha ovoz yaratadi (Azure TTS)
5. Yangi ovozni video ustiga qo'yadi (FFmpeg)
6. Tayyor videoni foydalanuvchiga qaytaradi

Foydalanuvchi faqat link yuboradi — hech qanday texnik bilim talab qilinmaydi.

---

## Arxitektura

```
┌─────────────────────────────────────────────────────────────┐
│                        FOYDALANUVCHI                        │
│                   (Brauzer / localhost:3000)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (REST API)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   FRONTEND — Next.js                        │
│  • YouTube URL kiritish formasi                             │
│  • Real-time progress bar (polling har 2 soniyada)          │
│  • Video player + yuklab olish tugmasi                      │
│  • TypeScript + Tailwind CSS                                │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API (axios)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND — FastAPI                          │
│  • POST /api/jobs      → Job yaratish                       │
│  • GET  /api/jobs/:id  → Status va natija olish             │
│  • GET  /api/video-info → YouTube preview                   │
│  • GET  /api/outputs/:id/video → Yuklab olish               │
│  Port: 8000                                                 │
└──────────┬────────────────────────┬────────────────────────┘
           │ Job navbatga qo'shish  │ Status yangilash
           ▼                        ▼
┌──────────────────┐    ┌───────────────────────────────────┐
│   REDIS          │    │         PostgreSQL                 │
│   (Task Queue    │    │  • dubbing_jobs jadvali            │
│    + Cache)      │    │  • Status, progress, natijalar     │
│   Port: 6379     │    │  Port: 5432                        │
└──────────┬───────┘    └───────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              CELERY WORKER — AI Pipeline                    │
│                                                             │
│  [1] yt-dlp         → YouTube dan video yuklash             │
│       ↓                                                     │
│  [2] OpenAI STT API  → Inglizcha nutq → matn (STT)          │
│       ↓                                                     │
│  [3] GPT-4o API     → Inglizcha → O'zbekcha (tarjima)       │
│       ↓                                                     │
│  [4] Azure TTS      → O'zbekcha matn → ovoz fayllar         │
│       ↓                                                     │
│  [5] FFmpeg         → Video + yangi ovoz → tayyor MP4       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│              CELERY FLOWER (Monitoring)                     │
│  • Worker holati, vazifalar statistikasi                    │
│  Port: 5555                                                 │
└─────────────────────────────────────────────────────────────┘
```

### Komponentlar o'rtasidagi muloqot

```
Frontend → FastAPI: YouTube URL yuborish
FastAPI  → Redis:   Celery task navbatga qo'shish
FastAPI  → Postgres: Job yozuvi yaratish
Celery   → Postgres: Har bosqichda status yangilash
Frontend → FastAPI: Har 2 soniyada status so'rash (polling)
Celery   → Disk:    Video/audio fayllarni saqlash
```

---

## Texnologiyalar

### Backend
| Texnologiya | Versiya | Maqsad |
|---|---|---|
| Python | 3.12 | Asosiy til |
| FastAPI | 0.115 | REST API framework |
| Celery | 5.4 | Fon vazifalar (task queue) |
| Redis | 7 | Celery broker + cache |
| PostgreSQL | 16 | Ma'lumotlar bazasi |
| SQLAlchemy | 2.0 | ORM |
| Pydantic | 2.10 | Data validation |

### AI / ML
| Texnologiya | Maqsad |
|---|---|
| OpenAI Audio API (`whisper-1`) | Speech-to-Text (inglizcha transkripsiya) |
| GPT-4o (OpenAI) | Inglizcha → O'zbekcha tarjima |
| Azure TTS (uz-UZ-SardorNeural) | Text-to-Speech (o'zbekcha ovoz) |

### Video qayta ishlash
| Texnologiya | Maqsad |
|---|---|
| yt-dlp | YouTube dan video/audio yuklash |
| FFmpeg | Audio ajratish, video/audio birlashtirish |
| pydub | Audio segmentlarni birlashtirish va tezlashtirish |

### Frontend
| Texnologiya | Versiya | Maqsad |
|---|---|---|
| Next.js | 15.1 | React framework |
| TypeScript | 5 | Tip xavfsizligi |
| Tailwind CSS | 3.4 | Styling |
| Axios | 1.7 | HTTP so'rovlar |
| lucide-react | 0.469 | Ikonlar |

### Infratuzilma
| Texnologiya | Maqsad |
|---|---|
| Docker + Docker Compose | Konteynerizatsiya |
| Playwright | YouTube cookie auto-refresh |
| Celery Flower | Worker monitoring |

---

## AI Pipeline

### Bosqich 1 — Download (yt-dlp)
```
YouTube URL → yt-dlp → video.mp4 + audio.wav
```
- Cookie authentication (bot blokirovkasini chetlab o'tish)
- Eng yuqori sifatli format tanlanadi
- FFmpeg audio ajratib oladi (16kHz mono — OpenAI transkripsiyasi uchun optimal)

### Bosqich 2 — Speech-to-Text (OpenAI)
```
audio.wav → ffmpeg chunking → OpenAI `whisper-1` → matn + vaqt belgilari (SRT)
```
- Audio 8 daqiqalik bo'laklarga bo'linadi, so'ng OpenAI'ga yuboriladi
- Lokal model yuklab olinmaydi va worker ichida STT modeli ishlatilmaydi
- Natija: `[{id, start, end, text}, ...]` — har bir gap alohida segment

### Bosqich 3 — Tarjima (GPT-4o)
```
[{id, start, end, "Hello world"}, ...] → GPT-4o → [{id, start, end, "Salom dunyo"}, ...]
```
- Faqat `text` maydoni tarjima qilinadi, `start/end` o'zgarmasdan qoladi
- 30 ta segmentdan iborat bo'laklarda yuboriladi (token limitini chetlab o'tish)
- Dublyajga mo'ljallangan: qisqa, tabiiy, og'zaki uslubda

### Bosqich 4 — Text-to-Speech (Azure TTS)
```
"O'zbek matni" → Azure uz-UZ-SardorNeural → segment_001.wav, segment_002.wav ...
```
- Har bir segment alohida audio faylga aylantiriladi
- Original vaqt oralig'iga sig'masa — audio tezlashtiriladi (pitch o'zgarmasdan)
- Barcha segmentlar bitta `dubbed_audio.wav` fayliga birlashtiriladi

### Bosqich 5 — Merge (FFmpeg)
```
video.mp4 + dubbed_audio.wav → FFmpeg → dubbed_final.mp4
```
- Video qayta encode qilinmaydi (`-c:v copy`) — tezroq va sifat yo'qolmaydi
- Audio AAC formatiga o'tkaziladi (192kbps)

### Progress tracking
| Bosqich | Progress |
|---|---|
| Navbatda | 0% |
| Yuklanmoqda | 5% |
| Transkripsiya | 20% |
| Tarjima | 40% |
| TTS | 60% |
| Birlashtirish | 85% |
| Tayyor | 100% |

---

## Papkalar strukturasi

```
ai-dubber/
│
├── backend/                        # FastAPI + Celery
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── __init__.py
│   │
│   ├── main.py                     # FastAPI app, CORS, lifespan
│   ├── config.py                   # Pydantic Settings (.env o'qish)
│   │
│   ├── models/
│   │   └── database.py             # SQLAlchemy modeli, DubbingJob jadvali
│   │
│   ├── api/
│   │   └── routes.py               # Barcha REST endpointlar
│   │
│   ├── workers/
│   │   ├── celery_app.py           # Celery konfiguratsiyasi
│   │   └── tasks.py                # Asosiy dublyaj vazifasi (5 bosqich)
│   │
│   └── services/
│       ├── downloader.py           # yt-dlp, cookie management
│       ├── transcriber.py          # OpenAI STT (chunked transcription)
│       ├── translator.py           # GPT-4o tarjima
│       ├── synthesizer.py          # Azure TTS + audio sync
│       ├── merger.py               # FFmpeg video birlashtirish
│       └── cookie_manager.py       # Playwright YouTube auto-login
│
├── frontend/                       # Next.js
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                # Bosh sahifa
│   │   └── globals.css
│   │
│   ├── components/
│   │   ├── ProgressBar.tsx         # 6 qadamli progress
│   │   └── VideoPlayer.tsx         # Video player + yuklab olish
│   │
│   ├── hooks/
│   │   └── useJobPolling.ts        # Har 2 soniyada status tekshirish
│   │
│   ├── lib/
│   │   └── api.ts                  # Barcha API chaqiruvlari
│   │
│   ├── package.json
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── uploads/                        # Yuklangan YouTube videolar (vaqtinchalik)
├── outputs/                        # Tayyor dublyaj videolar
├── cookies.txt                     # YouTube session cookies
├── docker-compose.yml              # Barcha servicelar
├── .env                            # API kalitlar va konfiguratsiya
└── README.md
```

---

## O'rnatish

### Talablar
- Docker Desktop (v4.0+)
- Node.js 20+ (frontend uchun)
- OpenAI API kaliti
- Azure Speech Service kaliti

### 1. Reponi klonlash
```bash
git clone https://github.com/username/ai-dubber.git
cd ai-dubber
```

### 2. `.env` faylini to'ldirish
```bash
cp .env.example .env
```

`.env` faylida quyidagilarni kiriting:
```env
# OpenAI
OPENAI_API_KEY=sk-...

# Azure TTS
AZURE_SPEECH_KEY=your_key
AZURE_SPEECH_REGION=eastus
AZURE_VOICE_NAME=uz-UZ-SardorNeural

# YouTube dedicated account
YOUTUBE_EMAIL=your_bot_account@gmail.com
YOUTUBE_PASSWORD=your_password
```

### 3. YouTube Cookie olish (birinchi marta)
```bash
# yt-dlp o'rnatish (Mac)
brew install yt-dlp

# Chrome dan YouTube cookie eksport qilish
yt-dlp --cookies-from-browser chrome \
       --cookies ./cookies.txt \
       --skip-download "https://www.youtube.com"
```

### 4. Backend ishga tushirish (Docker)
```bash
docker compose up -d --build
```

### 5. Frontend ishga tushirish
```bash
cd frontend
npm install
npm run dev
```

---

## Ishga tushirish

```bash
# Barcha servicelarni ishga tushirish
docker compose up -d

# Loglarni kuzatish
docker logs dubber_backend -f
docker logs dubber_worker -f

# To'xtatish
docker compose down
```

### Manzillar

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Celery Flower | http://localhost:5555 |

---

## API Dokumentatsiya

### `GET /api/video-info`
YouTube video haqida ma'lumot olish (yuklamasdan).

**So'rov:**
```
GET /api/video-info?url=https://youtu.be/xxxxx
```

**Javob:**
```json
{
  "title": "Video nomi",
  "duration": 312,
  "thumbnail": "https://img.youtube.com/...",
  "uploader": "Channel nomi"
}
```

---

### `POST /api/jobs`
Yangi dublyaj vazifasini yaratish.

**So'rov:**
```json
{ "youtube_url": "https://youtu.be/xxxxx" }
```

**Javob:**
```json
{ "job_id": "uuid", "status": "pending" }
```

---

### `GET /api/jobs/:id`
Job holati va natijasini olish.

**Javob:**
```json
{
  "job_id": "uuid",
  "status": "translating",
  "progress": 40.0,
  "status_message": "O'zbek tiliga tarjima qilinmoqda...",
  "video_title": "Video nomi",
  "video_duration": 312,
  "output_video_url": "/outputs/uuid/dubbed_final.mp4",
  "transcript_text": "Original inglizcha matn...",
  "translated_text": "O'zbekcha tarjima...",
  "error_message": null
}
```

**Status qiymatlari:**
`pending` → `downloading` → `transcribing` → `translating` → `synthesizing` → `merging` → `completed` / `failed`

---

### `GET /api/outputs/:id/video`
Tayyor videoni yuklab olish.

---

## Production uchun

### Cookie boshqaruvi
Production muhitida YouTube cookie'lari avtomatik boshqariladi:

```
1. YOUTUBE_EMAIL + YOUTUBE_PASSWORD → .env ga kiriting
2. Playwright har 12 soatda avtomatik login qiladi
3. cookies.txt yangilanadi
4. yt-dlp yangi cookie bilan ishlaydi
```

Agar Playwright ishlamasa — qo'lda yangilash:
```bash
yt-dlp --cookies-from-browser chrome \
       --cookies ./cookies.txt \
       --skip-download "https://www.youtube.com"
docker compose restart backend worker
```

### OpenAI modellari
```env
OPENAI_MODEL=gpt-4o
OPENAI_TRANSCRIPTION_MODEL=whisper-1
```
Loyiha endi lokal STT model yuklamaydi. Transkripsiya to'liq OpenAI Audio API orqali bajariladi.

### O'zbek ovoz tanlash (Azure TTS)
```env
AZURE_VOICE_NAME=uz-UZ-SardorNeural  # Erkak ovozi
AZURE_VOICE_NAME=uz-UZ-MadinaNeural  # Ayol ovozi
```

### Kengaytirish (Scaling)
Bir vaqtda ko'p video qayta ishlash uchun worker sonini oshirish:
```bash
docker compose up -d --scale worker=4
```

### PM2 bilan backend

`ecosystem.config.cjs` bitta PM2 faylda API va Celery worker'ni boshqaradi.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install -g pm2

pm2 start ecosystem.config.cjs
pm2 status
pm2 logs ai-dubber-api
pm2 logs ai-dubber-worker
pm2 save
```

PM2 config rootdagi `.env` faylini o'qiydi va agar mavjud bo'lsa `.venv/bin/python` ni ishlatadi. Production serverda PostgreSQL va Redis alohida servis sifatida ishlashi kerak.

---

## Konfiguratsiya

`.env` faylida barcha sozlamalar:

```env
# ─── OpenAI ───────────────────────────────────
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_TRANSCRIPTION_MODEL=whisper-1

# ─── Azure TTS ────────────────────────────────
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=eastus
AZURE_VOICE_NAME=uz-UZ-SardorNeural

# ─── YouTube ──────────────────────────────────
YOUTUBE_EMAIL=bot@gmail.com
YOUTUBE_PASSWORD=...

# ─── Database ─────────────────────────────────
DATABASE_URL=postgresql://<db_user>:<db_password>@postgres:5432/<db_name>

# ─── Redis ────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ─── AWS S3 (ixtiyoriy) ───────────────────────
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_BUCKET_NAME=ai-dubber-videos
AWS_REGION=us-east-1
```

---

## Litsenziya

MIT License
