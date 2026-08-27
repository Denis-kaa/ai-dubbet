# AI Dubber - Copilot Instructions

## High-Level Architecture
- **Frontend**: Next.js App Router (`frontend/app/`), React 19, and Tailwind CSS. Axios is used for API fetching with a pre-configured `apiClient` (in `frontend/lib/api.ts`) that handles Bearer tokens.
- **Backend**: FastAPI (`backend/api/`) serving REST endpoints.
- **Task Queue**: Heavy video processing tasks are offloaded to Celery (`backend/workers/tasks.py`) backed by Redis.
- **AI Pipeline**: The pipeline runs in the background and follows these steps: Downloader (`yt-dlp`) -> Transcriber (Faster-Whisper) -> Translator (GPT-4o) -> Synthesizer (Azure TTS) -> Merger (FFmpeg). Code for these steps is isolated in `backend/services/`.

## Key Conventions
- **App Router**: The frontend strictly uses Next.js App Router conventions (Server and Client Components in `app/`).
- **Axios Interceptors**: Always use the configured `apiClient` from `frontend/lib/api.ts` for backend requests to ensure the auth token is automatically attached.
- **Dependency Injection**: FastAPI routes use `Depends()` for DB sessions and authentication (e.g. `get_current_user`). 
- **Long-running Jobs**: Do not process video synchronously in FastAPI routes. Always enqueue tasks via Celery and return a job ID. The frontend polls for progress.
- **Language**: The codebase and user interface are in Uzbek. Write UI copy and functional documentation in Uzbek, but keep variable names, classes, and code elements in English.

## Build and Lint Commands
### Frontend
- **Install dependencies**: `cd frontend && npm install`
- **Development server**: `cd frontend && npm run dev`
- **Lint**: `cd frontend && npm run lint`
- **Build**: `cd frontend && npm run build`

### Backend
- **Docker Compose (Full Stack)**: `docker compose up -d --build` (Starts FastAPI, Celery, Redis, and PostgreSQL)
- **Run API (Local)**: `cd backend && uvicorn main:app --reload`
- **Run Celery Worker**: `cd backend && celery -A workers.celery_app worker --loglevel=info`

*(Note: No test suite is currently configured in the repository.)*
