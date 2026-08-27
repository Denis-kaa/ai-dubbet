# MOBILE INTEGRATION AUDIT — GapirAI.uz

**PHASE 0 — Repository + API Audit.** No mobile code has been written. Everything below reflects the *actual* state of `backend/` and `frontend/` in this repository as of this audit (commit `dd6fe53`). Where something could not be confirmed in code, it is explicitly marked `NOT FOUND` / `UNKNOWN` / `BLOCKED` rather than assumed.

---

## 5.1 Repository structure

```
Backend:
  backend/main.py                     FastAPI app, CORS, lifespan (job/analysis recovery), StaticFiles mount
  backend/config.py                   pydantic-settings Settings (env-driven)
  backend/api/
    auth_routes.py                    /auth/*  (register/login/verify/reset/me)
    routes.py                         /api/*   (dubbing jobs, video-info, outputs, feedback)
    video_analysis_routes.py          /api/video-analysis/*  (analysis, transcript, quiz, notes, Q&A)
    click_routes.py                   /api/payments/click/*  (Click.uz payment webhook + initiate)
    admin_routes.py                   /admin/*  (stats dashboard, admin-only)
  backend/models/
    database.py                       SQLAlchemy models: User, DubbingJob, VideoAnalysis, PronunciationMemory + JobStatus/AnalysisStatus enums
    payment.py                        Payment model, PaymentStatus/PaymentProvider enums
  backend/services/                   auth, downloader (yt-dlp), transcriber (Whisper), translator, synthesizer,
                                       speech_optimizer, speech_normalizer, merger (ffmpeg), storage (S3),
                                       click_service, email_service (Resend), telegram_service, video_analysis, tts/
  backend/workers/
    celery_app.py                     Celery app config (Redis broker/backend)
    tasks.py                          process_video — dubbing pipeline Celery task
    analysis_tasks.py                 analyze_video_task — analysis pipeline Celery task
  backend/tests/                      pytest tests (present, not audited in depth for Phase 0)

Frontend (Next.js App Router):
  frontend/lib/
    api.ts                            Central API client (axios) — dubbing + video-analysis calls, types, JobStatus/AnalysisStatus unions
    auth.ts                           Auth API calls + token storage (js-cookie) + localStorage user cache
    runtime-config.ts                 getApiUrl() — resolves API base URL by env/hostname
    admin.ts                          Admin API calls
  frontend/hooks/
    useAuth.ts                        Auth state/actions hook
    useJobPolling.ts                  2s interval polling for dubbing job status
    useAnalysisPolling.ts             2s interval polling for analysis status
  frontend/components/
    VideoPlayer.tsx                   Custom HTML5 <video> player (plays backend MP4, burns in VTT subtitles client-side)
    YouTubePlayer.tsx                 Wraps YouTube IFrame API (used only for Video Analysis — original video playback + seek)
    UrlInput.tsx / AnalysisUrlForm.tsx  Home screen forms (dub vs analyze)
    VideoResult.tsx / StepProgress.tsx / ProgressBar.tsx  Dubbing progress/result UI
    FeedbackSection.tsx / PlatformFeedbackWidget.tsx  Rating/feedback UI
  frontend/app/
    page.tsx                          Home — dub/analyze mode toggle, URL input, inline progress → result
    login/, register/, forgot-password/  Auth screens (email + 6-digit code verification flow)
    dashboard/page.tsx                 User's dubbing job history/library (GET /api/jobs), polls every 5s
    video/[id]/page.tsx                Dubbing job detail — player, payment gate, download, feedback
    video-analysis/[id]/page.tsx       Analysis detail — YouTube embed + tabs (summary/chapters/transcript/notes/quiz/Q&A)
    admin/page.tsx                     Admin stats dashboard (web-only, not in scope for mobile per spec)
    about/, faq/, privacy/, terms/     Static content pages

Existing infrastructure:
  PostgreSQL (SQLAlchemy sync engine, models above)
  Redis (Celery broker/result backend + rate limiter + yt-dlp concurrency lock)
  Celery (two task modules: dubbing tasks.py, analysis analysis_tasks.py)
  S3 (boto3, optional — only active if AWS_BUCKET_NAME + credentials are set; falls back to local disk + /outputs static mount otherwise)
  yt-dlp (video/audio download), OpenAI Whisper (transcription), OpenAI/Gemini (translation + analysis text gen), Edge/Azure/ElevenLabs/OpenAI/Gemini TTS (configurable provider), ffmpeg (merge/mux)
  Click.uz (payment provider — the only one wired up; Payme is modeled in the enum but has no route)
```

---

## 5.2 Authentication

```
Login endpoint:            POST /auth/login            {email, password} → does NOT return a token directly
Register endpoint:         POST /auth/register          {name, email, password} → does NOT return a token directly
Verify (completes login):  POST /auth/verify-code       {email, code} → AuthResponse {access_token, token_type, user}
Resend code:                POST /auth/resend-code       {email}
Forgot password:            POST /auth/forgot-password    {email}
Reset password:              POST /auth/reset-password     {email, code, new_password} → AuthResponse (also logs in)
Current user:                GET  /auth/me                  (Bearer token) → {id, name, email, role, created_at}
Logout:                     NOT FOUND (client-side only — frontend just deletes the stored token/cookie, no server endpoint)
Token type:                  JWT (python-jose, HS256)
Access token:                 Single token, no separate refresh token
Refresh token:                NOT FOUND — backend issues no refresh token; ACCESS_TOKEN_EXPIRE_MINUTES = 60*24*7 (7 days), then the user must log in again
Cookie/JWT:                   JWT only. Web stores it in a JS-readable cookie (`js-cookie`, `auth_token`, 7-day expiry, sameSite=lax, NOT httpOnly) — this is a bearer token pattern, not a session cookie
Authorization header:        `Authorization: Bearer <token>` — required on all authenticated endpoints (backend/services/auth.py uses FastAPI's HTTPBearer)
Token expiration:            7 days (604800 min... actually 10080 minutes = 7 days), hardcoded in backend/services/auth.py: ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
Password rules:               Minimum 6 characters, enforced server-side on register and reset-password
Email verification:           Mandatory — register/login both trigger a 6-digit code emailed via Resend; login is NOT complete (no token issued) until /auth/verify-code succeeds. This means "login" is effectively a 2-step OTP flow, not a single-call login.
Optional auth:                Some endpoints accept an OPTIONAL bearer token (get_optional_user) — e.g. creating a dubbing job works anonymously; the job is only attached to a user if a valid token is present.
```

**Important implication for mobile:** there is no single `POST /login → token` call. The real flow is `POST /auth/login` (sends OTP email) → `POST /auth/verify-code` (returns the actual JWT). The same 2-step pattern applies to registration and password reset. Mobile must implement this OTP UI, not a plain email/password form that expects an immediate token.

**Security note (informational, not a mobile task):** `SECRET_KEY` in `backend/services/auth.py` is a hardcoded string literal, not read from `Settings`/env. This is a backend concern, out of scope for the mobile client, but relevant if a "rewrite backend" temptation ever comes up — per the rules of this spec, it is not to be touched.

---

## 6. API Contract Audit

Base path note: FastAPI mounts `auth` router at `/auth`, dubbing/misc router at `/api`, video-analysis router at `/api/video-analysis`, payments at `/api/payments/click`, admin at `/admin`. CORS is wide open (`allow_origins=["*"]`, `allow_credentials=False`) — no cookie-based auth is possible cross-origin by design, which is consistent with the bearer-token approach (good for mobile: no cookie jar needed, just send the header).

### Auth

| Method | Endpoint | Auth | Request | Response | Purpose |
|---|---|---|---|---|---|
| POST | `/auth/register` | none | `{name, email, password}` | `{pending_verification: true, email, message}` | Create account, triggers OTP email |
| POST | `/auth/login` | none | `{email, password}` | `{pending_verification: true, email, message}` | Verify credentials, triggers OTP email |
| POST | `/auth/verify-code` | none | `{email, code}` | `{access_token, token_type: "bearer", user: {id, name, email, role}}` | Completes login/register, issues JWT |
| POST | `/auth/resend-code` | none | `{email}` | `{pending_verification, email, message}` | Resend OTP |
| POST | `/auth/forgot-password` | none | `{email}` | `{pending_verification, email, message}` | Sends reset OTP |
| POST | `/auth/reset-password` | none | `{email, code, new_password}` | `AuthResponse` (same shape as verify-code) | Resets password + logs in |
| GET | `/auth/me` | Bearer (required) | — | `{id, name, email, role, created_at}` | Fetch current user |

Errors: `400` (validation / duplicate email / bad code / expired code), `401` (wrong password), `404` (email not found), `500` (email send failure). Error body shape: `{"detail": "<Uzbek message string>"}` (FastAPI default `HTTPException` shape). There is also a global exception handler in `main.py` returning `{"detail": str(exc)}` with status 500 for uncaught exceptions.

### Dubbing

| Method | Endpoint | Auth | Request | Response | Purpose |
|---|---|---|---|---|---|
| GET | `/api/video-info` | none (rate-limited) | query `?url=` | `{title, duration, thumbnail, uploader}` | Preview YouTube video before submitting |
| POST | `/api/jobs` | optional Bearer | `{youtube_url, target_language: "uz" (fixed), voice_gender: "auto"\|"male"\|"female"}` | `{job_id, status: "pending"}` OR `{job_id, status: "awaiting_payment", amount}` | Create a dubbing job |
| GET | `/api/jobs/{job_id}` | none | — | `JobResponse` (see below) | Poll job status |
| GET | `/api/jobs` | Bearer (required) | query `limit` (≤100, default 20), `offset` | `JobResponse[]` | List current user's jobs (history/library) |
| DELETE | `/api/jobs/{job_id}` | Bearer (required, owner only) | — | 204 no body | Delete a job |
| GET | `/api/jobs/{job_id}/subtitles.vtt` | none | — | `text/vtt` body | WebVTT subtitles for the dubbed video |
| GET | `/api/outputs/{job_id}/audio` | none | — | 307 redirect to S3 presigned URL, or `audio/wav` file stream | Download dubbed audio |
| GET | `/api/outputs/{job_id}/video` | none | — | 307 redirect to S3 presigned URL, or `video/mp4` file stream | **Playback source for the dubbed video** — this is what `VideoPlayer.tsx` uses as `<video src>` |
| POST | `/api/jobs/{job_id}/cancel` | none | — | `{success, message}` | Cancel an active job |
| POST | `/api/jobs/{job_id}/feedback` | none | `{rating: 1-5, comment?, chat_id?, voice_ok?, translation_ok?, speed_ok?}` | `{success, message}` | Rate a completed job |
| POST | `/api/platform-feedback` | optional Bearer | `{message, rating?}` | `{success, message}` | General platform feedback (goes to Telegram) |

`JobResponse` shape (from `_job_to_response` in `backend/api/routes.py`):
```json
{
  "job_id": "uuid", "status": "pending|awaiting_payment|downloading|transcribing|translating|synthesizing|syncing|merging|completed|failed",
  "progress": 0.0, "status_message": "string|null",
  "video_title": "string|null", "video_duration": 0.0, "video_thumbnail": "url|null",
  "output_video_url": "string|null", "transcript_text": "string|null", "translated_text": "string|null",
  "error_message": "string|null", "error_code": "string|null", "created_at": "iso8601|null",
  "speaker_gender": "male|female|null", "voice_gender_setting": "auto|male|female|null",
  "uzbek_srt_content": "webvtt string|null", "expected_end_time": "iso8601|null",
  "rating": "int|null", "feedback_comment": "string|null",
  "feedback_voice_ok": "bool|null", "feedback_translation_ok": "bool|null", "feedback_speed_ok": "bool|null"
}
```
Note: `output_video_url` is defined on the model/response but the frontend never reads it for playback — it always constructs the URL itself as `{API_URL}/api/outputs/{job_id}/video`. Treat `getVideoUrl(jobId)` (i.e. hitting that endpoint directly) as the source of truth for playback, not the `output_video_url` field.

`expected_end_time` is a server-computed *estimate*, not a real ETA guarantee — it's a heuristic (`(30 + 0.3*duration) * remaining_factor`). Do not present it to users as precise; the web UI labels it "taxminan" (approximately).

**Statuses (`JobStatus` enum, `backend/models/database.py`):** `PENDING, AWAITING_PAYMENT, DOWNLOADING, TRANSCRIBING, TRANSLATING, SYNTHESIZING, SYNCING, MERGING, COMPLETED, FAILED`. Serialized to the frontend lowercase (`status_str = str(raw_status).lower()`). There is no percentage guarantee at each status beyond whatever `progress` (0–100 float) the worker sets — treat it as coarse, not linear.

**Polling mechanism:** plain HTTP polling, no WebSocket/SSE. Web polls every 2000ms (`frontend/hooks/useJobPolling.ts`) until status is `completed` or `failed`; on network error it backs off to 4000ms and keeps retrying; on 404 it stops and flags `is404`.

**Pricing / payment gate:** Videos under 45 minutes are free. Videos ≥45 min cost `ceil(minutes) * 500` UZS — UNLESS it is the user's first video ever (checked via `DubbingJob` count for that `user_id`), in which case it's also free. This means the free/first-video rule only applies to **logged-in** users (anonymous jobs have no `user_id` to count against). If `amount > 0`, job status starts as `AWAITING_PAYMENT` and processing does not start until payment.

### Payments (Click.uz)

| Method | Endpoint | Auth | Request | Response | Purpose |
|---|---|---|---|---|---|
| POST | `/api/payments/click/initiate` | optional Bearer | `{job_id}` | `{success, payment_url, payment_id, amount}` | Get a Click.uz checkout URL for a job |
| POST | `/api/payments/click/prepare` | none (Click webhook, signature-validated) | Click form-data | Click protocol response | Click.uz server-to-server prepare step |
| POST | `/api/payments/click/complete` | none (Click webhook, signature-validated) | Click form-data | Click protocol response | Click.uz server-to-server complete step — triggers job processing |

For mobile: `initiate` returns a `payment_url` that must be opened in a browser/WebView (Click.uz's own hosted checkout page — this is external, not something to build native UI for). The `prepare`/`complete` webhooks are server-to-server only and irrelevant to the mobile client directly, but their side effect (flipping job status from `AWAITING_PAYMENT` → `PENDING` → processing) is what the mobile app should detect via polling `GET /api/jobs/{id}`.

### Video Analysis

| Method | Endpoint | Auth | Request | Response | Purpose |
|---|---|---|---|---|---|
| POST | `/api/video-analysis` | Bearer (required) | `{youtube_url, language: "uz"\|"en"\|"ru"\|"tr"\|"kk"\|"original"}` | `{analysis_id, status: "pending"}` | Create an analysis job |
| GET | `/api/video-analysis/{id}` | Bearer (required, owner only) | — | Full analysis object (see below) | Poll analysis status / get results |
| GET | `/api/video-analysis/{id}/transcript` | Bearer (required, owner) | — | `{segments: [{start,end,text}]}` | Full transcript with timestamps |
| GET | `/api/video-analysis/{id}/chapters` | Bearer (required, owner) | — | `{chapters: [{title,start,end}]}` | Chapters only (also embedded in the main object) |
| POST | `/api/video-analysis/{id}/question` | Bearer (required, owner) | `{question}` | `{question, answer, timestamps: number[], asked_at}` | Ask AI a question about the video (Q&A / "AI tutor") |
| POST | `/api/video-analysis/{id}/quiz` | Bearer (required, owner) | — (no body) | `{quiz: [{question,options,correct_answer,explanation,timestamp}]}` | Lazily generate (or return cached) quiz |
| POST | `/api/video-analysis/{id}/notes` | Bearer (required, owner) | — (no body) | `{notes: "string"}` | Lazily generate (or return cached) notes/konspekt |
| GET | `/api/video-analysis/{id}/search` | Bearer (required, owner) | query `?q=` | `{results: [{start,end,text}]}` | Substring search over transcript segments |

`VideoAnalysis` object shape (`_analysis_to_dict`):
```json
{
  "id": "uuid", "status": "pending|downloading|extracting_audio|transcribing|analyzing|generating_results|completed|failed",
  "progress": 0.0, "status_message": "string|null",
  "youtube_url": "string", "video_title": "string|null", "video_duration": 0.0, "video_thumbnail": "url|null",
  "language": "string (requested/resolved analysis language)", "video_language": "string|null (Whisper-detected original language)",
  "summary": {"short": "", "medium": "", "detailed": ""} | null,
  "key_points": [{"title","description","timestamp"}] | null,
  "chapters": [{"title","start","end"}] | null,
  "notes": "string | null",
  "quiz": [{"question","options","correct_answer","explanation","timestamp"}] | null,
  "qa_history": [{"question","answer","timestamps","asked_at"}],
  "error_message": "string|null", "error_code": "string|null", "created_at": "iso8601|null"
}
```

**Statuses (`AnalysisStatus` enum):** `PENDING, DOWNLOADING, EXTRACTING_AUDIO, TRANSCRIBING, ANALYZING, GENERATING_RESULTS, COMPLETED, FAILED`. Web polls every 2000ms, same pattern as dubbing (`useAnalysisPolling.ts`).

**Ownership:** every analysis endpoint (except create) calls `_get_owned_analysis`, which 404s if not found and 403s if `analysis.user_id != current_user.id`. There is no sharing/public-view mechanism.

**No listing endpoint.** There is no `GET /api/video-analysis` (list) route anywhere in `backend/api/video_analysis_routes.py`. Unlike dubbing jobs (which have `GET /api/jobs`), a user cannot fetch "all my past analyses" from the backend. See §29/§53 — this is a hard **BLOCKED** for an Analysis history/library screen.

**Lazy generation confirmed:** `summary`, `key_points`, `chapters` are generated eagerly as part of the Celery pipeline (`analyze_video_task`) and are present as soon as status becomes `completed`. `notes` and `quiz` are generated lazily — only on the first `POST .../notes` or `POST .../quiz` call, then cached on the row (`if not analysis.notes: ... generate ...`). `qa_history` is always user-driven, never pre-generated.

### Admin (not in mobile scope, documented for completeness)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/stats` | Bearer + role=`admin` + email in `ADMIN_ALLOWED_EMAILS` | Dashboard stats (users/jobs/payments/trends) |

---

## 7. Video Dubbing Audit

Confirmed real flow (`backend/workers/tasks.py` orchestrates; not fully read line-by-line for this Phase 0 pass beyond status transitions, which are authoritative from `JobStatus` enum + `routes.py`):

```
YouTube URL
 ↓
POST /api/jobs  (video-info fetched synchronously first to validate URL/duration/get title+thumbnail)
 ↓
DubbingJob row created, status = PENDING (free) or AWAITING_PAYMENT (>=45min, not first video)
 ↓ (if AWAITING_PAYMENT) POST /api/payments/click/initiate → external Click.uz checkout → webhook flips to PENDING
 ↓
Celery task `process_video` enqueued (task_id = job_id, so it's revocable by id)
 ↓
status progression: DOWNLOADING → TRANSCRIBING → TRANSLATING → SYNTHESIZING → SYNCING → MERGING → COMPLETED
    (or → FAILED at any stage, with error_message + error_code set)
 ↓
Result: GET /api/outputs/{job_id}/video (MP4, S3 presigned redirect or local file),
        GET /api/jobs/{job_id}/subtitles.vtt (WebVTT, O'zbek),
        GET /api/outputs/{job_id}/audio (WAV)
```

- **Create dubbing endpoint:** `POST /api/jobs` — confirmed above.
- **Job ID:** UUID, generated client-side-in-backend before insert (`job_id = str(uuid.uuid4())`), also used as the Celery `task_id` — this is what enables `cancel_job` to call `celery_app.control.revoke(str(job_id), terminate=True)`.
- **Job status endpoint:** `GET /api/jobs/{job_id}` — no auth required (any UUID holder can poll; this is how anonymous dubbing works before login).
- **Possible statuses:** confirmed 10-value enum above (§6).
- **Polling mechanism:** confirmed — plain HTTP GET, 2s interval, client-driven, no push/WebSocket.
- **Result response:** `JobResponse` includes `output_video_url` field but it is **not populated with a usable value in observed usage** — `output_video_path`/`output_video_url` model columns exist but the frontend always derives the playback URL itself from the fixed `/api/outputs/{id}/video` route rather than trusting the field. Mobile should do the same (build the URL, don't trust `output_video_url` blindly — verify it's non-null before use if you do read it, but prefer the fixed endpoint).
- **Video URL:** `{API_URL}/api/outputs/{job_id}/video` → 307 redirect to S3 presigned URL (1 hour expiry, `backend/services/storage.py: generate_presigned_download_url(..., expiration=3600)`) if S3 is configured, else a direct file stream from local disk. **Mobile video players must follow HTTP redirects** (standard for `expo-av`/`expo-video`, but worth stating explicitly since presigned URLs expire in 1 hour — a long-paused video may need a fresh fetch of the endpoint to get a new presigned URL rather than caching the redirected URL indefinitely).
- **Failure response:** job status becomes `FAILED`, `error_message` (Uzbek, human-readable) and `error_code` (machine code e.g. `VIDEO_UNAVAILABLE`, `TRANSCRIBE_FAILED`, `TIMEOUT`, `NO_SPEECH_FOUND` — exact set defined in `backend/services/errors.py`/`tasks.py`, not fully enumerated in this pass) are both set.
- **Retry possibility:** No user-facing "retry" endpoint. A failed job is terminal — the mobile UI should offer "start a new job with the same URL" (client-side, POST /api/jobs again), not a retry-in-place button, since none exists server-side. (The backend does have automatic Celery-level retries with backoff for *transient* errors, but that's internal, invisible to the client, and does not change job status back to non-failed once it truly fails.)
- **Cancel:** `POST /api/jobs/{job_id}/cancel`, only works while job is in an active (non-terminal) status; cleans up upload/output dirs server-side.

---

## 8. Video Analysis Audit

Confirmed flow (`backend/workers/analysis_tasks.py`):

```
YouTube URL
 ↓
POST /api/video-analysis  (requires login — unlike dubbing, no anonymous path)
 ↓
VideoAnalysis row created, status = PENDING
 ↓
Celery task `analyze_video_task`:
   DOWNLOADING (reuses the same downloader.download_video as dubbing)
   → TRANSCRIBING (Whisper; also detects/stores video_language)
   → if language == "original": resolve analysis.language = detected video_language
   → ANALYZING (generates summary + key_points + chapters together, checkpointed)
   → COMPLETED
 ↓
notes / quiz generated lazily on first request; qa_history grows via /question calls
```

Feature-by-feature, confirmed present:

| Feature | Endpoint | Generation | Notes |
|---|---|---|---|
| Summary | embedded in `GET /{id}` | Eager (during pipeline) | `{short, medium, detailed}` |
| Key Points | embedded in `GET /{id}` | Eager | `[{title, description, timestamp}]`, timestamp seeks the player |
| Chapters | embedded in `GET /{id}` + `GET /{id}/chapters` | Eager | `[{title, start, end}]` |
| Transcript | `GET /{id}/transcript` (also `embedded.transcript_segments` used server-side, not returned in main object) | Eager | `[{start, end, text}]`; **not** in `_analysis_to_dict` output directly — must call the dedicated endpoint |
| Notes / Konspekt | `POST /{id}/notes` | **Lazy** (user-triggered) | Plain text, cached after first generation |
| Quiz / Test | `POST /{id}/quiz` | **Lazy** (user-triggered) | `[{question, options[], correct_answer, explanation, timestamp}]`, cached |
| Q&A / AI Tutor | `POST /{id}/question` | Always on-demand | Free-text question → GPT-generated answer + relevant timestamps; history accumulates in `qa_history` |
| Transcript search | `GET /{id}/search?q=` | On-demand | Simple substring match, not semantic search |

No lazy-generation for summary/key_points/chapters — they always exist once status is `completed`. Do not build a "Generate Summary" button; only "Generate Quiz" and "Generate Notes" buttons make sense (matches web behavior).

---

## 9. Analysis Language

Confirmed: **video language ≠ analysis language**, exactly as the spec hypothesized, and this is a real, deliberate backend behavior (see extensive Uzbek comments in `backend/models/database.py` and `backend/workers/analysis_tasks.py`).

- **Transcript** is always produced and stored in the video's **original spoken language** (whatever Whisper detects) — never translated.
- **Analysis outputs** (`summary`, `key_points`, `chapters`, and the lazy `notes`/`quiz`) are generated in whichever language the user selected at creation time (`language` field on `CreateAnalysisRequest`).
- If the user picks `"original"`, the backend resolves it to the detected `video_language` once transcription completes, and overwrites `analysis.language` with that resolved value — subsequent lazy endpoints (`notes`, `quiz`) then use the resolved language directly.

**Real allowed language list (backend-enforced, `ALLOWED_ANALYSIS_LANGUAGES` in `backend/api/video_analysis_routes.py`):**
```
uz, en, ru, tr, kk, original
```
This is the authoritative list — do not invent additional languages in the mobile UI. `video_language` (the detected original language) can be any language Whisper supports/detects and is displayed read-only (e.g. via `LANGUAGE_DISPLAY` map in `frontend/lib/api.ts`, which has friendly labels for a superset: uz/en/ru/tr/kk/es/fr/de/ko/ja/zh/ar/pt/it/hi — falls back to the raw code if not in that map).

Example (matches the spec's hypothetical exactly): a video in English, transcript stays in English, user selects `uz` as analysis language → summary/chapters/notes/quiz come back in Uzbek.

---

## 10. Video Player Audit

Two **distinct** player components exist for two **distinct** purposes — this distinction must be preserved in mobile, not merged:

1. **`VideoPlayer.tsx`** — used only on the **dubbing result** screen (`/video/[id]`). Plays the **dubbed MP4** produced by the backend via a plain HTML5 `<video>` tag, `src = {API_URL}/api/outputs/{job_id}/video`. Custom controls (play/pause/seek/volume/fullscreen/theater-mode), plus client-side WebVTT subtitle rendering (parses `job.uzbek_srt_content` — the raw VTT text is embedded directly in the job JSON, not fetched separately, though `/api/jobs/{id}/subtitles.vtt` also exists as a standalone route) and a subtitle-appearance settings panel (font size/color/background/opacity, persisted to `localStorage`). No YouTube dependency at all for this screen.
2. **`YouTubePlayer.tsx`** — used only on the **video analysis** screen (`/video-analysis/[id]`). Wraps the official YouTube IFrame API to play the **original YouTube video** (not a downloaded/re-hosted copy), because analysis doesn't produce a new video file — it only produces text/metadata about the existing YouTube video. Exposes a `seekTo(seconds)` imperative handle so that clicking a chapter/key-point/transcript-segment/quiz-timestamp jumps the YouTube player to that time.

**Source summary:**
- Dubbing playback source: **MP4 from backend** (`S3 signed URL` via 307 redirect, or local file stream) — `/api/outputs/{job_id}/video`, only available once `status === "completed"`.
- Analysis "playback" source: **the original YouTube video**, embedded via YouTube's own player (extracted video ID via regex from the stored `youtube_url`). The backend never re-hosts or downloads a playable copy for the user in the analysis flow — the downloaded audio is deleted after transcription (`_cleanup_upload_dir`).
- Signed URL expiration: 3600s (1 hour) for S3-backed dubbing outputs.
- Public URL: local-disk fallback (`/outputs/{id}/...` static mount, or the `/api/outputs/...` route) has no expiration/signing at all — it's just an open file path once you know the job UUID.
- Playback restrictions: none beyond needing the job's UUID (dubbing) — job GET and output GET endpoints require no auth, so anyone with the link can view/download a completed dub. Analysis, by contrast, is 100% auth+ownership gated (403 if not owner).

**Mobile implication:** use a native video player (e.g. `expo-video`) pointed at the backend MP4 URL for dubbing results — do not build a WebView wrapper. For analysis, embedding the actual YouTube video natively on mobile requires either `react-native-youtube-iframe` (WebView-based, since there's no native YouTube SDK equivalent to the web IFrame API) or opening YouTube via deep link/Linking for playback — this is an architecture decision for Phase 5/6, not Phase 0, but flagging now: a pure "no webview" mandate (§46) is in tension with the fact that the *existing backend contract* only gives mobile a YouTube URL for analysis videos, not a downloadable file. This should be called out explicitly to the user before Phase 6 design.

---

## 11. Storage Audit

```
S3 bucket:            configurable via AWS_BUCKET_NAME (default in code: "hr-lodex-recordings" — looks like a stale/inherited default value, not gapirai-specific; actual production value is in the untracked .env, not committed)
Media URL:             GET /api/outputs/{job_id}/video and .../audio — backend decides S3-vs-local per request
Signed URL:             Yes, when S3 is configured — boto3 generate_presigned_url("get_object", ExpiresIn=3600)
Signed URL expiration:  3600 seconds (1 hour) from the moment the /api/outputs/... endpoint is hit — NOT from job completion. Re-hitting the endpoint gets a fresh URL.
Access control:         None beyond "know the job UUID" for dubbing outputs (no auth check on GET /api/outputs/{id}/video|audio or GET /api/jobs/{id}). Video Analysis media (the YouTube embed) has no separate storage — it's not re-hosted.
Download endpoint:      Same as media URL — GET /api/outputs/{job_id}/video (video/mp4, browser triggers download via `download` attribute on web; mobile should treat this as a file download when the user explicitly requests "download", vs. streaming playback which is the same URL)
S3 credentials:         AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY read from backend .env — confirmed never exposed to the frontend/mobile client anywhere; all S3 interaction is server-mediated (redirects/streams), which is exactly the safe pattern §11/§38 of the spec require. No changes needed here — this already satisfies Rule 7.
```

---

## Mobile Blockers (Rule 53 — features with no backend support)

| Requested mobile feature | Backend status | Verdict |
|---|---|---|
| Video Analysis history/library (list past analyses) | No `GET /api/video-analysis` list route exists — only single-item `GET /{id}` | **BLOCKED** |
| Push notifications (job/analysis done) | No FCM/APNs/webhook/notification infrastructure found anywhere in `backend/` (no `notification`, `fcm`, `apns`, `firebase` references) | **BLOCKED** — mobile push implementation is `READY code-wise` but has nothing to call; must stay `BLOCKED BY BACKEND` per §34 |
| Real-time updates (WebSocket/SSE) | Confirmed absent — grepped, none found; both web hooks use plain polling | Not blocked, just: **use polling**, same as web (§19 already anticipates this) |
| Refresh tokens | Not implemented — single 7-day JWT, no refresh flow | Not "blocked" (nothing to build), but per §17 rule ("agar backend qo'llamasa, o'zingcha refresh system yaratma") — mobile must NOT invent a refresh mechanism; handle 401 by forcing re-login |
| Payme payment provider | Modeled in `PaymentProvider` enum but zero routes implemented — Click.uz is the only working provider | **N/A for mobile** — only Click.uz exists to integrate against |
| Server-side "retry failed job" | No such endpoint | **BLOCKED** — client must resubmit a new job |
| Notes/Quiz/Q&A pre-fetch | These are correctly lazy by design (not a gap) | Not blocked — implement as user-triggered actions, matches §27 exactly |
| Logout endpoint | No server-side logout/token-invalidation route | Not blocked — logout is inherently client-only (clear stored token) here, same as web |

## Backend changes that would help mobile (report only — do not implement)

- A `GET /api/video-analysis` (list, paginated, owner-scoped) endpoint would be needed for any Analysis history/library screen. Currently impossible to build one without this.
- No push notification channel exists; if "job completed" push notifications are desired later, the backend needs a device-token registration endpoint plus a hook in `tasks.py`/`analysis_tasks.py` to fire on terminal status.

---

## Summary for Phase 1+ planning

- Auth is JWT bearer + mandatory OTP-by-email, 7-day expiry, no refresh token, no logout endpoint.
- Dubbing works anonymously (job creation + polling + playback need no auth) but job history (`GET /api/jobs`) requires login. First video is free for logged-in users; ≥45min videos are paid via Click.uz (external checkout URL, opened in browser).
- Video Analysis is 100% auth-gated, has no history-listing endpoint (blocked feature), and has a real video-language-vs-analysis-language distinction that must be surfaced in the UI (two separate language badges, exactly as the web does).
- Dubbing playback = native MP4 URL (good for native video player). Analysis playback = original YouTube video (no re-hosted file), which will need a WebView-based or deep-link-based solution — a deviation worth flagging against the "no WebView" mandate before Phase 6.
- All polling is plain HTTP, 2s interval, client-driven — directly portable to a `useDubbingJob()`/`useAnalysisJob()` TanStack Query pattern with `refetchInterval` and app-foreground gating, per §19.
- No secrets of any kind (OpenAI, AWS, Click, Telegram, Resend) are exposed to the frontend today — the existing web app is already a clean client of the backend, which is the correct model to replicate in mobile.

**PHASE 0 COMPLETE.** Awaiting explicit go-ahead before starting Phase 1 (Expo Foundation).
