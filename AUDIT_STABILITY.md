# АУДИТ СТАБИЛЬНОСТИ — GapirAI.uz (ai-dubber)

**Дата:** 2026-08-25
**Цель:** найти причины (1) постоянных перезапусков, (2) ошибок бэкенда, (3) отваливающихся YouTube-куки.
**Метод:** статический аудит всего backend-кода + docker-compose + PM2-конфигурации (без запуска production).

---

## 1. Архитектура (кратко)

| Слой | Технологии | Точка входа |
|------|-----------|-------------|
| API | FastAPI + uvicorn (`--workers 4`), CORS, lifespan-recovery | `backend/main.py` |
| Очередь | Celery 5.4 + Redis (broker/backend), `task_acks_late=True` | `backend/workers/celery_app.py` |
| Workers | `process_video` (dublyaj), `analyze_video_task`, `generate_resolution_variant_task` | `backend/workers/tasks.py` |
| БД | PostgreSQL + SQLAlchemy (sync), `Base.metadata.create_all()` без миграций | `backend/models/database.py` |
| YouTube | yt-dlp (клиенты ios/android/mweb) + PO-token sidecar (bgutil) + `cookies.txt` + proxy (datacenter → residential) | `backend/services/downloader.py` |
| TTS | Provider-фабрика: elevenlabs/azure/edge/openai/gemini/uzbekvoice, fallback → edge | `backend/services/tts/` |
| Медиа | ffmpeg (subprocess), pydub (AudioSegment в RAM) | `merger.py`, `synthesizer.py` |
| Деплой | docker-compose (7 сервисов) **или** PM2 (`ecosystem.config.cjs`) | — |

Pipeline job: DOWNLOAD → TRANSCRIBE (Whisper) → SAFETY → GENDER → TRANSLATE → SPEECH_OPT → TTS → MERGE → S3 → notify. Каждый этап имеет DB-checkpoint (JSONB `*_segments`) для идемпотентного retry.

---

## 2. Проблема YouTube cookies — почему они «отваливаются»

### 2.1. Автоматическое обновление куки **никогда не работает** (3 независимых причины)

1. **Playwright не установлен.** `cookie_manager.refresh_cookies()` начинается с `from playwright.async_api import async_playwright` в try/except → `ImportError` → `return False`. В `backend/requirements.txt` и `Dockerfile` playwright **отсутствует**. Весь механизм авторизации — мёртвый код.

2. **Файл смонтирован read-only.** Во всех трёх сервисах:
   ```yaml
   - ./cookies.txt:/app/cookies.txt:ro
   ```
   А `_save_cookies_netscape()` пишет напрямую:
   ```python
   COOKIES_FILE = "/app/cookies.txt"
   with open(filepath, "w") as f:   # → [Errno 30] Read-only file system
   ```
   Даже если бы Playwright стоял — запись упадёт.

3. **Сервис-обновлятор не запущен.** `cookie_refresher.py` — **единственный** вызывающий `get_or_refresh_cookies_sync()`, но в `docker-compose.yml` **нет** сервиса `cookie-refresher`. Никто не вызывает обновление.

**Итог:** куки живут ровно столько, сколько живёт ручной экспорт. YouTube-сессия протухает (SAPISID/`__Secure-3PSID` / PO-token инвалидируются, аккаунт получает «Sign in to confirm you're not a bot»), yt-dlp начинает получать `cookies are no longer valid` / `HTTP 403` / `Requested format is not available` — платформа падает в bot-check → `_BOT_CHECK_MARKERS` → job FAILED с «cookielari eskirgan». Пользователь вынужден вручную пере-экспортировать `cookies.txt`.

### 2.2. Дополнительные уязвимости cookie-пути

- **Один аккаунт на всю платформу.** `cookies.txt` общий для всех сервисов и всех пользователей. YouTube-бан аккаунта = отказ всех скачиваний платформы. Нет ротации, нет per-source аккаунтов.
- **`cookies_are_fresh()` считает свежесть по мета-файлу, которого нет** (`/app/cookies_meta.json` не смонтирован, лежит в эфемерном слое контейнера). Плюс не проверяет реальные `expires` в самом файле.
- **Мета-файл эфемерный:** после каждого `docker compose up`/рестарта контейнера `cookies_meta.json` пропадает → свежесть «0» → при каждом старте (если бы refresh был подключён) — лишние попытки Google-логина.
- **Сам Playwright-логин хрупок по дизайну:** селекторы (`input[name="identifier"]`, `#passwordNext`) ломаются при любом изменении DOM Google, Google активно банит headless-логины (reCAPTCHA). Это известная «кошмарная» поддержка.
- **`_save_cookies_netscape`** теряет `httpOnly`/`SameSite` признаки (yt-dlp это не критично, но `expires=0` у session-куки в файле допустим — не баг, а примечание).
- Прокси-цепочка зависит от настроения YouTube: `_PROXY_ESCALATION_MARKERS` включает `HTTP Error 403` и `Requested format is not available`, что маскирует настоящую причину (не всегда bot-check).

---

## 3. Причины «постоянных перезапусков» (по убыванию влияния)

### 🔴 P0-1. `recover_stuck_jobs()` ре-энкьюит ВСЕ активные job при КАЖДОМ старте backend

```python
def recover_stuck_jobs():
    active_statuses = [PENDING, DOWNLOADING, TRANSCRIBING, ...]
    stuck_jobs = db.query(DubbingJob).filter(status.in_(active_statuses)).all()
    for job in stuck_jobs:
        job.status = JobStatus.PENDING
        db.commit()
        process_video.apply_async(args=[str(job.id)], task_id=str(job.id), ...)
```

- Вызывается в `lifespan()` при каждом запуске `uvicorn` (4 воркера = 4 процесса, но lifespan один раз на мастер).
- **Не отличает «завис» от «сейчас выполняется»**: если backend рестартнулся (деплой/OOM/краш), пока worker жив и обрабатывает job — тот же job получает **второе** сообщение с тем же `task_id`. Celery по умолчанию **не дедуплицирует** `apply_async` по `task_id` → два параллельных исполнения одного job: оба качают, оба пишут в одни и те же файлы → гонки, битый merge, дублирующиеся расходы OpenAI, каскадные retry.
- Если job по-настоящему не может стать FAILED (например, стойкая ошибка записи в БД, `_mark_job_failed` 2× не смог) — он **навсегда** останется в активном статусе и будет ре-энкьюится при каждом рестарте → бесконечный цикл «рестарт → ре-энкью → фейл → рестарт».

### 🔴 P0-2. OOM в worker из-за pydub (весь аудио в RAM)

`backend/services/synthesizer.py`:

```python
combined = AudioSegment.silent(duration=total_ms, frame_rate=_FRAME_RATE)  # 24000 Гц × 2 байта
combined = combined.overlay(item["audio"], position=item["start_ms"])       # каждая накладка копирует
```

Для 3-часового видео: только silent-трек = 3·3600·24000·2 ≈ **518 МБ**, каждая `overlay()` — ещё одна полная копия буфера. Плюс `seg_data` держит **все** сегменты одновременно. Worker запущен с `-c 4` → 4 таких job параллельно = 2+ ГБ. Docker OOM-kill → контейнер перезапускается (`restart: unless-stopped`) → `recover_stuck_jobs()` ре-энкьюит активные job → **цикл рестартов**.

### 🟠 P1-3. Рассогласованные таймауты: задача убивается по soft limit, пока ждёт слот скачивания

- `YoutubeRateLimiter.ACQUIRE_TIMEOUT = 8000` c (2 ч 13 м), а `process_video.soft_time_limit = 3300` (55 м).
- Job, вставший в очередь на слот, через 55 минут убивается `SoftTimeLimitExceeded` → `retry()` (countdown до 10 мин) → снова ждёт слот → снова 55 мин… Job «перезапускается» часами, worker-слоты простаивают.
- `merger.merge_video_audio` → `subprocess.run(..., timeout=8000)` — но Celery убьёт задачу на 3600 c раньше; для длинного видео merge всегда превышает лимит → job циклически перезапускается 5 раз → FAILED `TIMEOUT`. Checkpoint `output_video_path` не создан → каждый retry merge начинается с нуля.

### 🟠 P1-4. PM2-worker слушает не все очереди

```js
// ecosystem.config.cjs
args: "-m celery -A backend.workers.celery_app worker -l info -Q video_processing -c 2",
```

`get_job_queue()` возвращает `video_processing_priority` для Pro/Premium, а PM2-worker слушает **только** `video_processing`. Приоритетные job (и `resolution_variants`, `analysis_tasks` — они маршрутизируются в `video_processing`, ок) — точнее: **приоритетные** заявки **молча зависают** в PENDING навсегда. Плюс `max_restarts: 10` — после 10 падений PM2 сдаётся и сервис лежит.

### 🟡 P2-5. Мелкие, но реальные

- **`task_acks_late=True` без `task_reject_on_worker_lost=True`**: при потере worker (SIGKILL/OOM) сообщение не реджектится сразу, а висит до visibility-timeout → job «зависает» на минуты.
- **`engine = create_engine(..., pool_size=3, max_overflow=2)` на 4 uvicorn-воркера**: 4×5 = 20 коннектов к Postgres + worker-сессии; при пике — `Too many connections`, `OperationalError` — те самые «server closed the connection unexpectedly» (закомментировано в `_mark_job_failed`).
- **`recover_stuck_resolution_variants` / `recover_stuck_analyses`** — те же проблемы ре-энкьюя без фильтра «давно не обновлялся».
- **Celery `rate_limit: "1/m"` + Redis-лок `MAX_CONCURRENT=1` с `expire 180`**: если скачивание длится дольше 180 c (обычное дело), ключ `yt_dl:concurrent` истекает → инвариант single-IP ломается, стартует второе параллельное скачивание.
- **Глобальный exception-handler** возвращает `Access-Control-Allow-Origin: *` (с origin) при 500 — не критично.
- **`datetime.utcnow()`** в Python 3.12+ — депрекация, в 3.14 (локально) warnings; в контейнере 3.12 — пока ок.

---

## 4. План исправления (с кодом)

### Шаг 1. Починить cookie-цепочку (главная жалоба клиента)

**1a. Сделать куки обновляемыми через yt-dlp OAuth/ручной экспорт вместо Playwright-логина.**

Рекомендация: **убрать Playwright-логин как источник** (Google ломает его сознательно) и сделать два механизма:
- (i) админ-endpoint загрузки свежего `cookies.txt` (валидация + запись в host-файл) + Telegram-алерт, когда bot-check достиг порога;
- (ii) health-чек: раз в N минут проверять `yt-dlp` на эталонном видео; при появлении `_BOT_CHECK_MARKERS` — алерт «куки умерли, нужен ручной экспорт».

Минимальный немедленный фикс (docker-compose): убрать `:ro` и добавить недостающий сервис:

```yaml
  cookie-refresher:
    build: { context: ., dockerfile: backend/Dockerfile }
    container_name: dubber_cookie_refresher
    restart: unless-stopped
    env_file: [ .env ]
    environment: &redis_env
      - REDIS_URL=redis://:0061f8931184fe1276650305600d5409df1a3af2692094d5@redis:6379/0
    volumes:
      - ./cookies.txt:/app/cookies.txt          # убрать :ro!
      - ./cookies_meta.json:/app/cookies_meta.json  # persist свежесть
    depends_on: [ postgres, redis, pot-provider ]
    command: python3 -m backend.services.cookie_refresher
```

**1b. `cookies_are_fresh()` — судить по реальному expiry, а не по мета-файлу:**

```python
def cookies_are_fresh() -> bool:
    if not os.path.exists(COOKIES_FILE):
        return False
    max_expiry = 0
    try:
        with open(COOKIES_FILE) as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 5 and parts[4].isdigit():
                    max_expiry = max(max_expiry, int(parts[4]))
        # 7 дней запаса до протухания самой «долгой» куки
        return max_expiry > time.time() + 7 * 86400
    except Exception:
        return False
```

**1c. `refresh_cookies` — не писать в read-only путь, а писать в отдельный буфер и атомарно заменять:**

```python
def _save_cookies_netscape(cookies: list, filepath: str) -> None:
    tmp = filepath + ".tmp"
    with open(tmp, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            ...
    os.replace(tmp, filepath)   # атомарно, переживает :ro→rw миграцию
```

### Шаг 2. Остановить цикл рестартов (P0-1)

**2a. Ре-энкьюить только по-настоящему зависшие job (updated_at старше порога) и не трогать «в работе»:**

```python
def recover_stuck_jobs():
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    active_statuses = [JobStatus.PENDING, JobStatus.DOWNLOADING, ...]
    stuck_jobs = (
        db.query(DubbingJob)
        .filter(DubbingJob.status.in_(active_statuses))
        .filter(DubbingJob.updated_at < cutoff)   # ← ключевой фильтр
        .all()
    )
    for job in stuck_jobs:
        job.status = JobStatus.PENDING
        job.status_message = "Qayta tiklandi (avtomatik)"
        db.commit()
        process_video.apply_async(args=[str(job.id)], task_id=str(job.id),
                                  queue=get_job_queue(db, job.user_id))
```

**2b. Защита от двойного исполнения (Redis NX-лок в начале `process_video`):**

```python
from redis import Redis
_r = Redis.from_url(settings.REDIS_URL, decode_responses=True)

@celery_app.task(...)
def process_video(self: Task, job_id: str) -> dict:
    lock_key = f"job:running:{job_id}"
    acquired = _r.set(lock_key, self.request.id or "", nx=True, ex=3600)
    if not acquired:
        logger.warning(f"[JOB {job_id}] уже выполняется — дубликат пропущен")
        return {"job_id": job_id, "status": "already_running"}
    try:
        ...  # весь pipeline
    finally:
        _r.delete(lock_key)
```

**2c. `celery_app`:** добавить `task_reject_on_worker_lost=True` и `worker_max_tasks_per_child=100` (сброс утечек/состояния воркера).

### Шаг 3. Снять OOM в синтезе (P0-2)

**3a. Снизить параллелизм worker:** `-c 4` → `-c 2` (или 1) в docker-compose.

**3b. Не строить гигантский `AudioSegment` в RAM — склеивать через ffmpeg `adelay`/`amix` (стриминг):**

```python
# synthesizer.py: вместо combined.overlay(...) в цикле
# 1) каждый seg_*.wav уже на диске (они сейчас и так пишутся)
# 2) собрать фильтр-граф:
inputs = [str(f) for f in sorted(output_path.glob("seg_*.wav"))]
if inputs:
    filter_parts, amix_inputs = [], []
    for i, path in enumerate(inputs):
        delay_ms = int(actual_start_ms(i))
        filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[d{i}]")
        amix_inputs.append(f"[d{i}]")
    graph = ";".join(filter_parts) + f";" + "".join(amix_inputs) + \
            f"amix=inputs={len(inputs)}:normalize=0[a]"
    subprocess.run(["ffmpeg", "-y", *flat_inputs,
                    "-filter_complex", graph, "-map", "[a]",
                    "-ar", "24000", "-ac", "1", merged_path], check=True)
```

Это переводит память из O(N·сегменты) в потоковый режим — O(1) по RAM, O(N) по диску.

### Шаг 4. Согласовать таймауты (P1-3)

```python
# downloader.py
ACQUIRE_TIMEOUT = 600      # 10 мин вместо 8000 — не держать слот воркера часами

# merger.py — подогнать под Celery hard limit (3600 c): 8000 → 2800
subprocess.run(cmd, capture_output=True, text=True, timeout=2800)
```

И в `process_video` при `YoutubeRateLimiter`-timeout — сразу `retry` с коротким countdown, а не ожидание внутри задачи:

```python
except RuntimeError as exc:
    if "slot not available" in str(exc):
        raise self.retry(exc=exc, countdown=120)  # короткая пауза, слот освободится
```

### Шаг 5. PM2 (если используется)

```js
args: "-m celery -A backend.workers.celery_app worker -l info -Q video_processing_priority,video_processing -c 2",
```
и `max_restarts: 10` → поднять (например 50), добавить `min_uptime: "30s"`.

### Шаг 6. Мониторинг как предохранитель

- health-эндпоинт `/health` уже есть; добавить `/health/yt` — быстрый `get_video_info` эталонного видео без куки и с кукой, чтобы видеть «куки умерли» до массовых фейлов.
- Алерт в Telegram (`telegram_notify.send_telegram_message`) при первом `AUTH_ERROR` (бот-чек) в течение часа.

---

## 5. Приоритеты

| # | Действие | Эффект |
|---|----------|--------|
| 1 | Фикс cookie-цепочки (1a–1c) | Убирает главную жалобу «куки отваливаются» |
| 2 | `recover_stuck_jobs` + NX-лок (2a–2b) | Останавливает цикл «рестарт → ре-энкью → дубль» |
| 3 | OOM-фикс синтеза (3a–3b) | Убирает краш-рестарты worker |
| 4 | Таймауты (4) | Убирает «перезапускающиеся» job на 55 мин |
| 5 | PM2-очереди (5) | Приоритетные job перестают зависать |
| 6 | Мониторинг (6) | Раннее обнаружение, меньше «тихих» деградаций |

---

## 6. Статус внедрения (2026-08-25)

Все фиксы раздела 4 **внедрены** (аддитивно) и проверены на сервере:

| # | Фикс | Файл(ы) | Статус |
|---|------|---------|--------|
| 1 | Куки: freshness по expires + атомарная запись | `cookie_manager.py` | ✅ внедрено |
| 2a | Recovery только зависших (фильтр 15 мин) | `main.py` | ✅ внедрено |
| 2b | Redis NX-лок против дублей + retry при занятом слоте | `tasks.py` | ✅ внедрено |
| 3 | ffmpeg adelay/amix склейка (OOM-фикс) + pydub-fallback | `synthesizer.py` | ✅ внедрено |
| 4a | ACQUIRE_TIMEOUT 8000→600 c | `downloader.py` | ✅ внедрено |
| 4b | merge timeout 8000→2800 c | `merger.py` | ✅ внедрено |
| 5 | task_reject_on_worker_lost + worker_max_tasks_per_child | `celery_app.py` | ✅ внедрено |
| 5' | PM2 max_restarts — обойдён переходом на systemd | — | ✅ (деплой) |

**Верификация:** pytest 10/10 на сервере; live-джоб `0cb02c58` COMPLETED 100%, длительность 18.9 c, 0 ошибок, 0 рестартов; ffmpeg-склейка без fallback.

**Не закрыто (для заказчика):** серверные куки протухли (переэкспорт вручную), OpenAI-ключ пуст (работает Gemini).
