# CHANGELOG — GapirAI.uz (ai-dubber)

## 2026-08-27 — UI: прогресс скачивания + предупреждение о встроенных браузерах

- `frontend/lib/download.ts`: скачивание через fetch с прогрессом (прогресс по `Content-Length`, стриминг `ReadableStream`, сохранение Blob, отмена через `AbortController`) + детект встроенных браузеров (Telegram/WhatsApp/Instagram/Facebook/Messenger/TikTok/VK/WeChat/Line/WebView) и безопасное имя файла из названия видео.
- `frontend/components/DownloadButton.tsx`: кнопка «Videoni yuklab olish (720p)» с прогресс-баром, счётчиком МБ (получено/всего), кнопкой «Bekor qilish» и обработкой ошибок (в т.ч. подсказка открыть в Chrome/Safari).
- `app/video/[id]/page.tsx`: янтарный баннер при открытии во встроенном браузере («откройте в Chrome/Safari») + кнопка скачивания с прогрессом над блоками качества `ResolutionDownloadButtons`.
- Причина: обычный `<a download>` не даёт прогресса и молча блокируется в вебвью мессенджеров — жалоба «видео идёт, но скачать не могу».
- Деплой: сборка Next.js на сервере успешна (type-check прошёл после фикса `Uint8Array → Blob`), static скопирована в standalone, `ai-dubber-frontend` перезапущен, строки UI подтверждены в бандле, `root`/`health` 200.

## 2026-08-27 — Fix: faststart для MP4 (звук с первой секунды, стабильное скачивание)

- Проблема: итоговые MP4 не были faststart — `moov`-атом в конце файла (mdat на 44-м байте, moov за пределами первых 1 МБ). На телефоне это давало «видео идёт, звука нет / длительность 0:00», т.к. плеер должен был догружать хвост файла ради метаданных.
- Исправлено: в `backend/services/merger.py` (обе ветки: copy и freeze) и `backend/services/resolution_variants.py` (360p) добавлен `-movflags +faststart` — moov пишется в начало файла.
- Все 6 существующих роликов перемультиплексированы `-c copy -movflags +faststart` (без перекодирования, без потери качества): moov теперь на байте 36.
- Деплой: `merger.py`/`resolution_variants.py` синхронизированы на сервер, `ai-dubber-api` и `ai-dubber-worker` перезапущены, сервисы active, backend-тесты **19 passed**.
- Проверено: ffprobe — h264 + aac (звук есть, mean -24 dB), длительность корректная; заголовки: inline для плеера, attachment для `?download=1`, Range 206 работает.

## 2026-08-27 — Приёмка завершена; собран handover-пакет для заказчика

- Полная приёмка на production `185.233.184.192` (SSH через ключ Termux-home `id_ed25519_whimco`):
  - backend-тесты на сервере: **`19 passed`**;
  - `/health` → JSON 200; главная `200` с переключателем «Faqat tarjima / Tarjima + original fon»; `/login` → 200;
  - БД: 6/6 jobs `COMPLETED`, все ролики отдают `206 Partial Content` (Range-запросы), субтитры и аудио — 200;
  - видео без параметра → `Content-Disposition: inline` (плеер), `?download=1` → `attachment` (скачивание); `POST /api/jobs` без авторизации → 401 (защита работает);
  - сервисы active/enabled, nginx перезагружен, `NRestarts=0`.
- Собран чистый handover-пакет без секретов (сборка из git-файлов + артефактов деплоя):
  - `gapirai_handover/gapirai-handover-v1.0.0.tar.gz` — 195 файлов, ~4.2 МБ + `SHA256SUMS.txt`;
  - в архиве: `backend/`, `frontend/`, `deploy/` (nginx.conf, build_frontend.sh, migrations), `.env.example`, отчёты, `docs/DEPLOY_FOR_CLIENT.ru.md`;
  - проверено: нет `.env`, cookies, `*.pem`, node_modules, runtime-данных; `mobile/` (Expo) не включён — отдельный релиз.
- Написан полный гайд развёртывания для заказчика `docs/DEPLOY_FOR_CLIENT.ru.md`: PostgreSQL/Redis, `.env`, systemd-юниты, сборка frontend, nginx + certbot, приёмочный сценарий, troubleshooting — всё с placeholders `<ДОМЕН>`/`<IP_СЕРВЕРА>`.
- Внешние шаги для текущего стенда остаются: смена DNS `gapirai.uz` на ahost.uz (13.61.168.79 → 185.233.184.192) + выпуск SSL.

## 2026-08-27 — Deploy завершён; блокер — DNS домена

- SSH восстановлен: рабочий ключ — `~/.ssh/id_ed25519_whimco` из Termux-home (алиас `whims`/`whim`).
- Backend/frontend синхронизированы, frontend standalone пересобран, nginx-конфиг обновлён (`server_name gapirai.uz www.gapirai.uz 185.233.184.192 _;`), сервисы перезапущены, backend-тесты `19 passed`.
- Проверено по IP: `/health` JSON 200, главная содержит переключатель «Faqat tarjima / Tarjima + original fon», видео без параметра = `inline`, с `?download=1` = `attachment`, `accept-ranges: bytes`.
- **Корневая причина «домен не работает» — DNS:** `gapirai.uz`/`www` указывают на `13.61.168.79` (AWS, старая копия приложения), NS — `rdns1/2/3.ahost.uz`. Требуется смена A-записей на `185.233.184.192` в панели ahost.uz + выпуск SSL после этого.

## 2026-08-27 — Verification: production SSH/domain routing blocker persists

- локальная Python syntax-проверка изменённых backend-модулей прошла;
- локальный полный pytest по-прежнему заблокирован отсутствующими в Termux зависимостями (`pydantic_settings`, `pydub`, `yt_dlp`), поэтому результат `15 passed` относится к предыдущему server `venv`-срезу;
- локальный TypeScript check не запускался: в телефонной копии отсутствует `frontend/node_modules`;
- `http://185.233.184.192/health` отвечает JSON `200`, но `https://gapirai.uz/health` отвечает HTML `404` через другой nginx server block;
- текущий SSH alias `whim` отсутствует, а ключ `id_ed25519_whimco` не принят сервером для `root`, `ubuntu` и `whimco`; повторный production deploy/restart невозможен до восстановления доступа;
- deploy-артефакт `deploy/nginx.conf` обновлён явным `server_name` для домена и IP;
- повторная проверка 2026-08-27 подтверждает: IP `/health` = JSON `200`, домен `/health` = Next.js HTML `404`; SSH снова отвечает `Permission denied (publickey,password)` для доступных ключей и пользователей;
- production restart/deploy автоматически не выполнен, чтобы не создавать ложный статус «обновлено».


## 2026-08-26 — Feature: выбор аудиорежима и раздельные ссылки просмотра/скачивания

- добавлен выбор режима для каждой новой задачи: `dubbed_only` или `ducked_mix`;
- выбор сохраняется в `dubbing_jobs.audio_mix_mode` и передаётся в обычный merge и генерацию 1080p;
- старые job без значения поля не используются как кэш для нового запроса, чтобы не перепутать режимы;
- URL для `<video>` отдаётся как `inline`, кнопка скачивания использует `?download=1` и получает `attachment`;
- тот же `inline/attachment`-контракт добавлен для S3 presigned URL и вариантов качества;
- миграция: `deploy/migrations/2026-08-26_add_audio_mix_mode.sql`.

**Верификация:** frontend `next build` завершён успешно; backend `15 passed`; production health `200`; просмотр и скачивание возвращают `206 video/mp4` с правильным `Content-Disposition`; сервисы active, `NRestarts=0`.

## 2026-08-26 — Fix: итоговый ролик действительно содержит узбекский дубляж

**Проблема:** предыдущий merge всегда смешивал исходную дорожку и TTS через `amix`. В результате готовый MP4 мог технически содержать перевод, но пользователь слышал преимущественно оригинальную речь. При этом браузер и скачивание работали корректно.

**Исправлено:**
- добавлен `AUDIO_MIX_MODE`;
- режим `dubbed_only` включён по умолчанию и использует только второй FFmpeg-вход, сохранённый `dubbed_audio.wav`;
- прежний режим сохранён как `ducked_mix` для обратной совместимости;
- неизвестное значение режима безопасно возвращается к `dubbed_only`;
- production `.env` установлен в `AUDIO_MIX_MODE=dubbed_only`.

**Верификация:**
- серверный focused-набор: `3 passed`;
- полный backend-набор: `13 passed`;
- smoke merge: H.264 + один AAC-аудиотрек, длительность `18.93 s`;
- шесть существующих роликов пересобраны атомарно из сохранённых TTS-файлов;
- все шесть итоговых MP4 содержат ровно одну AAC-дорожку;
- `audio_qa` больше не выдаёт ложный `background_missing` в режиме чистого дубляжа;
- серверный полный набор после QA-фикса: `15 passed`;
- Chromium E2E: `readyState=4`, длительность `18.93 s`, ошибка декодирования отсутствует;
- API и worker после перезапуска: `active`, `/health` отвечает `200`, `NRestarts=0`.

Новые job используют `dubbed_only` автоматически. Уже готовые ролики были обновлены на сервере; повторно скачивать исходные видео или заново вызывать AI не потребовалось.

## 2026-08-26 — Fix: локальный fallback для воспроизведения видео после S3 TTL

**Проблема:** у готовых роликов S3-объект мог быть удалён lifecycle-политикой, хотя локальный MP4 ещё существовал. API сразу возвращал `410 Gone`, из-за чего браузерный `<video>` показывал чёрный экран и длительность `0:00`.

**Исправлено:**
- `backend/api/routes.py` теперь использует доступный локальный `output_video_path`, если S3-объект отсутствует или presigned URL не был создан;
- такой же fallback добавлен для аудио;
- `backend/services/resolution_variants.py` учитывает локальный master при проверке `expired` и генерации 360p.

**Верификация на `whimco` (`185.233.184.192`):**
- проблемный ролик `3ae1064f-1294-4de3-92d1-e0b5419c60ad`: `GET /api/outputs/.../video` → `206 Partial Content`;
- `Content-Type: video/mp4`, `Content-Range: bytes 0-1048575/167722195`;
- `ffprobe`: H.264 + AAC, MP4, длительность `1036.9` секунд;
- все 6 готовых роликов проверены внешним Range-запросом, каждый вернул `206`;
- API после перезапуска: active, `NRestarts=0`;
- headless Chromium: `readyState=4`, `duration=1036.9`, `videoWidth=640`, `videoHeight=360`, `error=null`.

Артефакт браузерной проверки: `deploy/e2e_video_playback.py`.

## 2026-08-26 — E2E: проверен вход через headless Chromium и реальную почту

Установлены Playwright/Chromium на сервере. Автоматический браузерный тест подтвердил:
`/login` рендерится, `POST /auth/login` идёт на same-origin IP, код принимается,
`auth_token` создаётся, `GET /auth/me` возвращает пользователя (HTTP 200).
Проверены тестовый аккаунт и `den4ikorm@gmail.com`; Resend принимает отправку кода (HTTP 200/201).
Диагностический и E2E-скрипты: `deploy/e2e_diag.py`, `deploy/e2e_login_test.py`.

## 2026-08-25 — Fix: логин по IP (runtime-config + nginx /auth,/admin)

**Проблема:** фронтенд был собран с жёстким `API_URL=https://api.gapirai.uz` — при заходе
по IP все запросы авторизации уходили на несуществующий домен → «не получается зайти».

**Фиксы:**
1. `frontend/lib/runtime-config.ts` — API_URL по умолчанию same-origin (`""`),
   запросы идут относительными путями через nginx (работает и по IP, и по домену).
2. `deploy/build_frontend.sh` — исправлен баг путей копирования статики
   (`cd frontend` ломал `$STANDALONE`); добавлен `cd ..` после сборки.
3. nginx — добавлены `location /auth/` и `location /admin/` → backend :8000
   (фронтенд зовёт их без префикса `/api`).

**Верификация:** rebuild + redeploy; `api.gapirai.uz` отсутствует в бандле;
полный цикл `POST /auth/login → код → POST /auth/verify-code → JWT` — 200 OK.


Формат: [Дата] — краткое описание (стабильность-релиз после аудита).

---
## [2026-08-25] — Деплой на сервер: nginx + фронтенд + внешний доступ

### Что сделано
- **nginx reverse proxy** установлен и настроен (`/etc/nginx/sites-enabled/ai-dubber`, артефакт в репо: `deploy/nginx.conf`):
  - `/` → Next.js standalone на :3000 (frontend)
  - `/api/*` → backend uvicorn на :8000
  - `/health` → JSON напрямую с :8000 (не HTML)
  - `/outputs/*` → готовые видео с диска (alias, Cache-Control)
- **Фронтенд собран** (`npm run build`, standalone-режим) и запущен через systemd на :3000.
- **Права на `/opt/ai-dubber`** исправлены (o+rx) — nginx (www-data) мог получать 403 на `/outputs/*`.

### Верификация (снаружи, с телефона)
| Проверка | Результат |
|----------|:---------:|
| `http://185.233.184.192/` | HTTP 200, HTML (главная GapirAI.uz) |
| `http://185.233.184.192/health` | HTTP 200, **application/json** |
| `http://185.233.184.192/api/jobs` | HTTP 401 (API проксируется, auth работает) |
| `http://185.233.184.192/outputs/<job_id>/dubbed_final.mp4` | HTTP 206, **video/mp4**, range-загрузка работает (стриминг 46 МБ) |

Публичный адрес: **http://185.233.184.192/** (порт 80).
### ⚠️ Критический фикс: статика Next.js (CSS/JS) не загружалась
**Проблема:** Next.js standalone-сервер не находит `/_next/static/*` файлы (CSS 64 КБ, JS чанки, шрифты) — браузер получает HTML без стилей/скриптов → «белый экран» или «не загружается».

**Корень:** standalone-сборка копирует только `server.js` и `node_modules`, но **не копирует `.next/static/`**. Нужен явный `cp -r .next/static .next/standalone/.next/static` после `npm run build`.

**Исправлено:**
- Скопирована статика в `.next/standalone/.next/static/` на сервере
- **`ExecStartPre`** в systemd-unit: автокопирование при старте, если `static/` отсутствует (safety-net)
- Создан `deploy/build_frontend.sh` — скрипт сборки + деплоя (включает копирование static)
- Проверено: `GET /_next/static/css/*` → 200 64678b ✅, `GET /_next/static/chunks/*` → 200 ✅

## [2026-08-25] — Аудит стабильности + 4 фикса (AUDIT_STABILITY.md)

### Контекст
Клиент жаловался на: (1) нестабильную работу (постоянные перезапуски), (2) регулярные ошибки бэкенда, (3) отваливающиеся YouTube-куки. Проведён глубокий аудит всего backend-кода → `AUDIT_STABILITY.md`. Найдено 5 корневых причин; внедрены 4 фикса (5-й — «ПМ2 mаx_restarts» — обойдён переходом на systemd при развёртывании на сервере).

### Изменения (аддитивные, обратная совместимость сохранена)

| Файл | Фикс |
|------|------|
| `backend/services/cookie_manager.py` | **Фикс 1 — куки-цепочка:** `cookies_are_fresh()` теперь оценивает свежесть по **реальному `expires`** в файле куки (не по эфемерному мета-файлу); `min_cookie_expiry()` — новый health-метод; `_save_cookies_netscape()` — **атомарная запись** (tmp + `os.replace`), не оставляет полубитый файл при сбое |
| `backend/main.py` | **Фикс 2a — recovery:** `recover_stuck_jobs()` и `recover_stuck_analyses()` теперь ре-энькьюят **только зависшие** job (фильтр `updated_at < now - 15 мин`), не трогают живые; добавлена константа `RECOVERY_STUCK_MINUTES = 15`. См. AUDIT §3 P0-1 |
| `backend/workers/tasks.py` | **Фикс 2b — защита от дублей:** Redis **NX-лок** `job:running:{id}` (TTL 3600 c) в начале/конце `process_video`; fail-open при недоступности Redis. Плюс обработка «slot not available» — короткий `retry(countdown=120)` вместо длинного ожидания |
| `backend/services/synthesizer.py` | **Фикс 3 — OOM:** склейка сегментов через **ffmpeg `adelay`+`amix`** (потоковая, O(1) по RAM) вместо `AudioSegment.silent()`+`overlay()` (держало весь звук в памяти); pydub-метод сохранён как **fallback** при ошибке ffmpeg |
| `backend/services/downloader.py` | **Фикс 4a — таймаут:** `ACQUIRE_TIMEOUT` 8000 c → **600 c** (10 мин), чтобы worker не висел в ожидании слота дольше мягкого лимита задачи |
| `backend/services/merger.py` | **Фикс 4b — таймаут:** merge `timeout` 8000 c → **2800 c** (в пределах hard limit Celery 3600 c) |
| `backend/workers/celery_app.py` | **Фикс 5 — конфиг:** `task_reject_on_worker_lost=True` (зависшие задачи при потере воркера отклоняются сразу), `worker_max_tasks_per_child=100` (сброс утечек) |

### Верификация
- `pytest backend/tests/` — **15 passed** (на сервере, venv).
- Live-джоб после фиксов: `0cb02c58` — **COMPLETED 100%**, выходной `dubbed_final.mp4` 764 КБ, длительность 18.9 c (совпадает с исходником), **0 ошибок в логах**, ffmpeg-склейка отработала без fallback.
- Сервисы `ai-dubber-api`/`ai-dubber-worker` активны, **0 рестартов** после деплоя фиксов.

### Известные ограничения (не закрыто)
- **Куки на сервере протухли (5.5 дней назад)** — парсер фикса это честно показывает; нужно переэкспортировать свежий `cookies.txt` вручную (инструкция — в AUDIT_STABILITY §4 Шаг 1a).
- OpenAI-ключ пуст — транскрипция и перевод работают через **Gemini** (проверено live).
- Деплой **нативный (systemd)**, не docker; docker-compose сохранён для совместимости, но фиксы внесены в общие файлы.

## [2026-08-25] — Доработка: ротация Gemini-ключей + проверка «куки не критичны»

### Контекст
При live-тесте выяснилось:
1. **YouTube-куки не критичны для этого сервера** — джоб на новом видео (`681a2794`, Rick Astley 3:32) отработал `DOWNLOAD=3.4s ok` **без файла cookies.txt** (yt-dlp обходит блокировку через ios/android/mweb + PO-token).
2. **Gemini упёрся в суточную квоту** бесплатного тарифа (`limit: 20 запросов/день/ключ`) — транскрипция/перевод начали получать 429.

### Изменения (аддитивные)
| Файл | Что |
|------|-----|
| `backend/config.py` | Добавлены поля `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3` |
| `backend/services/transcriber.py` | Ротация: при 429 перед retry — `_rotate_gemini_key()` (следующий ключ из 3, клиент пересоздаётся) |
| `backend/services/translator.py` | То же для перевода (thread-local индекс, ротация + инвалидация клиента) |

Эффективно: 3 ключа × 20 запросов/день = **до ~60 запросов/день** на модель.

### Верификация
- Live-джоб `681a2794` (3:32 видео, без cookies.txt): **COMPLETED 100%** — DOWNLOAD ok, TRANSCRIBE/TRANSLATE ok, TTS ok (Azure после 429-retry), MERGE 37.7 s ok.
- Полный цикл прошёл несмотря на кратковременную 429 на одном ключе.

### Статус куки
- Куки на сервере протухшие (автомониторинг видит), **но не критичны** — скачивание работает без них.
- Гайд `COOKIES_UPDATE_GUIDE.md` оставлен на случай, если YouTube начнёт блокировать (тогда — переэкспорт вручную).
