# AGENTS.md

## Architecture

- **Monorepo**: `frontend/` (Next.js 15 App Router, React 19, Tailwind CSS) + `backend/` (FastAPI + Celery worker)
- **AI Pipeline** (Celery → `backend/workers/tasks.py`): yt-dlp download → OpenAI Whisper STT → GPT-4o translate → Azure TTS → FFmpeg merge
- **Infra**: PostgreSQL 16, Redis 7 (Celery broker), Flower (monitoring on :5555)
- **Production server**: `51.21.35.247`, deployed to `/opt/xadichai`, Nginx reverse proxy → FastAPI :8000

## Critical: PYTHONPATH

**Python is always run from the repo root, never from `backend/`.** All imports use `backend.` prefix:

```
PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000
PYTHONPATH=. celery -A backend.workers.celery_app worker -l info -Q video_processing -c 2
```

This affects `docker-compose.yml`, `ecosystem.config.cjs`, CI deploy script (via `PYTHONPATH` env), and all manual commands.

## Commands

### Docker (full stack)
```bash
docker compose up -d --build          # Start all: postgres, redis, backend, worker, flower
docker compose up -d --scale worker=4 # Scale workers
docker logs dubber_backend -f         # Backend logs
docker logs dubber_worker -f          # Worker logs
```

### Frontend (local, no Docker)
```bash
cd frontend && npm install
cd frontend && npm run dev            # :3000
cd frontend && npm run build          # output: "standalone" mode
cd frontend && npm run lint           # only lint check, no test runner
```

### Backend (local venv, no Docker)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
celery -A backend.workers.celery_app worker -l info -Q video_processing -c 2
celery -A backend.workers.celery_app flower --port=5555    # monitoring UI
```

### PM2 (production alternative to Docker)
```bash
pm2 start ecosystem.config.cjs        # reads .env, auto-detects .venv/bin/python
pm2 status
pm2 logs ai-dubber-api
pm2 logs ai-dubber-worker
```

## Build quirks

- **Backend Dockerfile** installs ffmpeg + Node.js + Deno and configures yt-dlp with `--js-runtimes deno --remote-components ejs:github` for PO tokens + JS challenge solving. Without these, YouTube downloads fail with "signature solving failed" or "please sign in".
- **Auth**: yt-dlp uses `cookies.txt` (mounted read-only via `docker-compose.yml`). OAuth was deprecated by yt-dlp and no longer works. If `cookies.txt` is missing, falls back to unauthenticated iOS client (limited formats, may not work for all videos).
- **YouTube rate limiting**: `YoutubeRateLimiter` in `downloader.py` uses Redis to ensure max 1 concurrent download + 30s cooldown between downloads, with exponential backoff (up to 5 min) on failures. Celery task route also has `rate_limit="1/m"` as a safety net.
- **DB enum hack**: `create_tables()` in `backend/models/database.py:84` tries `ALTER TYPE jobstatus ADD VALUE 'awaiting_payment'` on startup. Creates the missing enum value in existing DBs. If the PG enum is out of sync, this is the fix.

## CI/CD

- **Primary workflow**: `.github/workflows/ci-cd.yml` — triggers on `main` and `develop`, runs `python -m pytest tests` (backend) + `npm run lint` + `npm run build` (frontend), then deploys to server via SSH. NOTE: no actual test files exist yet.
- **Legacy workflow**: `.github/workflows/main.yml` — simpler SSH deploy, may be redundant.
- CI deploys only on push to `main`; artifacts from `frontend/.next/standalone/` are rsync'd to `/var/www/xadichai.uz/public/`.

## Key conventions

- **API client**: Always use `apiClient` from `frontend/lib/api.ts` — it auto-attaches Bearer token and resolves `NEXT_PUBLIC_API_URL`.
- **Database**: Sync SQLAlchemy (`psycopg2-binary`), not async. Sessions via `SessionLocal` or FastAPI `Depends(get_db)`.
- **Long jobs**: Never process video in a FastAPI route. Always enqueue via `process_video.apply_async(args=[job_id], task_id=job_id)` and poll `GET /api/jobs/:id`.
- **Language**: UI copy and documentation in Uzbek. Code identifiers in English.
- **Payments**: Videos >10min require auth + Click payment. `voice_gender` param selects Azure voice (`auto` → GPT-4o detects gender from transcript).

## No test suite

The CI references `python -m pytest tests` but no test files exist under `backend/tests/`. Add them before this step will pass.
