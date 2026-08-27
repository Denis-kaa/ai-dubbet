# AI Dubber — Handoff заказчику

**Дата аудита:** 2026-08-26
**Production:** `whimco` / `185.233.184.192`
**Текущий вариант:** web-продукт GapirAI.uz
**Последняя проверка:** 2026-08-27 — production задеплоен и проверен по IP: backend `19 passed`, переключатель аудиорежима в UI, `inline`/`attachment` заголовки работают. Открытый блокер: DNS `gapirai.uz` указывает на старый сервер 13.61.168.79 (AWS), а не на 185.233.184.192.

## 1. Итог

Проект не переписан заново. Основной backend/frontend сохранён; изменения выполнены как исправления и добавления вокруг существующего конвейера:

- авторизация и подтверждение email;
- создание и обработка dubbing jobs;
- транскрипция, перевод, TTS и FFmpeg merge;
- библиотека готовых роликов;
- платежные интеграции Click/Payme/Uzum/Paynet;
- frontend-плеер, разрешения качества и fallback хранения.

Production-сервисы на момент проверки работают и включены в автозапуск:

| Компонент | Статус |
|---|---|
| nginx | active/enabled |
| FastAPI `ai-dubber-api` | active/enabled |
| Celery `ai-dubber-worker` | active/enabled |
| Next.js `ai-dubber-frontend` | active/enabled |

Проверки предыдущего server-среза: health `200`, backend tests `15 passed`, готовые MP4 возвращали `206 Partial Content`, headless Chromium видел `readyState=4`, положительную длительность и размеры видеопотока. Режим результата `AUDIO_MIX_MODE=dubbed_only`: готовый MP4 содержит только обработанную узбекскую TTS-дорожку; legacy-режим `ducked_mix` сохранён отдельно. В текущем локальном коде для новых задач пользователь выбирает режим в форме; просмотр использует `inline`, скачивание `attachment`. После последнего изменения production повторно не перезапускался: SSH-ключ не принят.

## 2. Что передавать заказчику

Передавать исходный web-срез проекта:

- `backend/`;
- `frontend/`;
- `docker-compose.yml` и `backend/requirements.txt`;
- `.env.example` без реальных значений;
- `README.md`;
- актуальную production-инструкцию после сверки с сервером;
- `deploy/nginx.conf` и `deploy/build_frontend.sh`;
- `AUDIT_STABILITY.md`, `REPORT_TECHNICAL.ru.md`, `REPORT_SIMPLE.ru.md`;
- `COOKIES_UPDATE_GUIDE.md`;
- `CHANGELOG.md`;
- этот файл.

## 3. Что не включать в архив исходников

Нельзя отправлять заказчику без отдельного согласования:

- `.env`, `frontend/.env.local`, `frontend/.env.production.local`;
- `cookies.txt`;
- любые `*.pem`, SSH-ключи и файлы доступа;
- `.claude/settings.local.json` и локальные журналы команд;
- `uploads/`, `outputs/`, `.next/`, `node_modules/`, `.venv/`, `__pycache__/`;
- реальные JWT, пароли, API keys, webhook credentials и данные тестовой почты.

`outputs/` — это runtime-данные сервера. Если заказчику нужна библиотека готовых роликов, передавать её отдельно как контентный архив после согласования прав и размера.

## 4. Mobile

`mobile/` — отдельный React Native/Expo слой. Он не входит в проверенный web-production handoff. В текущем рабочем состоянии Git есть большой набор изменений/переносов mobile-файлов, поэтому его нельзя выдавать как готовое мобильное приложение без отдельного build/test-приёмочного цикла.

Варианты:

1. передать только проверенный web-срез и явно указать mobile как следующий этап;
2. провести отдельную приёмку mobile и включить его отдельным релизом.

## 5. Тестовые аккаунты

Тестовая учётная запись и выданный вручную Pro/library access предназначены только для приёмки. Перед передачей нужно выбрать одно действие:

- удалить тестовую учётную запись и связанные тестовые jobs;
- или переименовать её в согласованный demo account и заменить пароль;
- или оставить только при явном письменном согласовании заказчика.

Текущий доступ нельзя считать частью исходного кода: он находится в production PostgreSQL.

## 6. Известные эксплуатационные условия

- Для email-кодов нужен рабочий Resend sender/domain.
- YouTube cookies не являются обязательными для текущего успешного сценария, но могут понадобиться при изменении антибот-политики YouTube.
- S3 lifecycle может удалять старые объекты. API теперь использует локальный MP4 как fallback, если локальная копия существует; для долгого хранения нужно согласовать S3 retention/backup policy.
- Production проверен 2026-08-27 по IP: `http://185.233.184.192/health` = JSON `200`, главная содержит переключатель «Faqat tarjima / Tarjima + original fon», видео без параметра отдаётся как `inline`, с `?download=1` — как `attachment`, `accept-ranges: bytes` работает.
- **Корневая причина «домен не работает» — DNS:** `gapirai.uz` и `www.gapirai.uz` указывают на `13.61.168.79` (AWS) — там развёрнута старая/другая копия приложения (Next.js, `/health` = HTML 404). Наш сервер — `185.233.184.192`. NS-серверы: `rdns1/2/3.ahost.uz` (регистратор ahost.uz).
- **Требуется действие:** в панели DNS ahost.uz поменять A-записи `gapirai.uz` и `www.gapirai.uz` с `13.61.168.79` на `185.233.184.192`. После смены DNS дополнительно настроить HTTPS (certbot/Let's Encrypt), т.к. сейчас nginx слушает только :80, а SSL на сервере нет.
- При миграции существующей базы нужно выполнить `deploy/migrations/2026-08-26_add_audio_mix_mode.sql`; по предыдущему отчёту production-миграция была применена, но после текущей недоступности SSH повторно подтвердить это нельзя.
- 2026-08-27 деплой завершён: backend/frontend синхронизированы, миграция `audio_mix_mode` подтверждена (колонка EXISTS), frontend standalone пересобран, nginx-конфиг обновлён (`server_name gapirai.uz www.gapirai.uz 185.233.184.192 _;`), сервисы перезапущены, backend-тесты `19 passed`.
- Остаётся единственный внешний шаг: смена DNS на ahost.uz (см. выше). После неё — выпуск SSL-сертификата на нашем сервере.
- Перед включением реальных платежей заказчик должен подтвердить merchant/webhook credentials и провести sandbox/live acceptance отдельно.
- `deploy.sh` и старые инструкции с `/opt/xadichai` относятся к прежнему окружению и не должны использоваться для текущего `whimco`; актуальный runtime — systemd в `/opt/ai-dubber`.

## 7. Действие, необходимое заказчику: DNS

1. Зайти в панель DNS регистратора ahost.uz.
2. Найти A-записи `gapirai.uz` и `www.gapirai.uz`.
3. Поменять значение с `13.61.168.79` на `185.233.184.192`.
4. Сохранить. Распространение DNS занимает от минут до нескольких часов (TTL).
5. После этого написать нам — выпустим SSL-сертификат (certbot) на сервере.

## 8. Минимальный recovery/deploy после восстановления SSH

1. Добавить новый публичный ключ на сервер в `/root/.ssh/authorized_keys` либо использовать пользователя, указанного провайдером.
2. Синхронизировать проект в `/opt/ai-dubber` без `.env`, cookies и runtime-данных.
3. Выполнить миграцию `deploy/migrations/2026-08-26_add_audio_mix_mode.sql`.
4. Выполнить `bash deploy/build_frontend.sh` либо эквивалентную сборку standalone.
5. Проверить `nginx -t && systemctl reload nginx`.
6. Перезапустить `ai-dubber-api`, `ai-dubber-worker`, `ai-dubber-frontend`.
7. Проверить `curl -fsS https://gapirai.uz/health` — должен быть JSON `200`, затем проверить login, переключатель аудио, просмотр и скачивание.

## 9. Приёмочный checklist

- [ ] заказчик получил очищенный архив без секретов;
- [ ] создан новый production `.env` с уникальным `SECRET_KEY`;
- [ ] настроены собственные API keys и sender email;
- [ ] проверены регистрация, email-код и выход из аккаунта;
- [ ] проверен новый dubbing job на коротком видео;
- [ ] проверены воспроизведение, Range-запрос и скачивание MP4;
- [ ] проверена библиотека готовых роликов;
- [ ] проверены платежные webhook'и в согласованном окружении;
- [ ] оформлен домен/HTTPS или письменно принят HTTP по IP;
- [ ] определён срок хранения outputs/S3 и политика резервных копий;
- [ ] отдельно решён статус mobile;
- [ ] тестовые аккаунты и демонстрационные права удалены либо переданы по согласованию.

## 10. Фактические артефакты проверки

- `backend/tests/`: `19 passed` на production `venv` (полный набор, включая `test_audio_mode_contract.py`);
- `deploy/e2e_video_playback.py`: Chromium smoke test;
- `CHANGELOG.md`: журнал исправлений;
- `REPORT_TECHNICAL.ru.md`: технический отчёт;
- `REPORT_SIMPLE.ru.md`: отчёт для нетехнического заказчика.

## 11. Приёмка 2026-08-27 (production 185.233.184.192)

После восстановления SSH (рабочий ключ — `/data/data/com.termux/files/home/.ssh/id_ed25519_whimco` на телефоне) деплой доведён до конца и **подтверждён снаружи**:

| Проверка | Результат |
|---|---|
| Backend-тесты на сервере | ✅ `19 passed` |
| `/health` | ✅ JSON `200` `{"status":"ok","service":"GapirAI.uz"}` |
| Главная страница | ✅ `200`, HTML содержит переключатель «Faqat tarjima» / «Tarjima + original fon» |
| `/login` | ✅ `200` |
| Готовые ролики в БД | ✅ 6/6 jobs `COMPLETED`, все отдают `206 Partial Content` |
| Видео (плеер) | ✅ `Content-Disposition: inline`, `accept-ranges: bytes`, Range `206` |
| Видео (`?download=1`) | ✅ `Content-Disposition: attachment` |
| Аудио (`/api/outputs/<id>/audio`) | ✅ `200 audio/wav` |
| Субтитры (`subtitles.vtt`) | ✅ `200` |
| `POST /api/jobs` без авторизации | ✅ `401` (эндпоинт жив и защищён) |
| Сервисы | ✅ `ai-dubber-api`, `ai-dubber-worker`, `ai-dubber-frontend` active/enabled, nginx перезагружен |

Старые job (созданные до фичи) имеют `audio_mix_mode = NULL` — по дизайну они остаются доступны по своим ссылкам и не используются как кэш для новых задач с явным режимом.

**Доп. фикс 2026-08-27 (после жалобы «видео идёт, звука нет / не скачивается»):** итоговые MP4 не были faststart (`moov` в конце файла) — на телефоне плеер не получал метаданные сразу, что давало отсутствие звука/0:00. Добавлен `-movflags +faststart` в `merger.py` (обе ветки) и `resolution_variants.py` (360p); все 6 существующих роликов перемультиплексированы без перекодирования (moov теперь в начале, байт 36). Сервисы перезапущены, тесты `19 passed`.

**UI 2026-08-27 (скачивание):** на странице `/video/[id]` добавлены кнопка «Videoni yuklab olish (720p)» с прогресс-баром и отменой (`frontend/lib/download.ts` + `frontend/components/DownloadButton.tsx`, fetch-стриминг с прогрессом по Content-Length) и янтарный баннер при открытии во встроенном браузере (Telegram/WhatsApp/Instagram и др.) с рекомендацией Chrome/Safari. Причина: `<a download>` не даёт прогресса и блокируется в вебвью мессенджеров. Собрано и задеплоено на сервере, строки подтверждены в бандле.

## 12. Handover-пакет для заказчика (готов)

Собран чистый пакет исходников **без секретов** (собран из git-трекаемых файлов + файлов деплоя):

- 📦 `/storage/emulated/0/ПРОЕКТ/gapirai_handover/gapirai-handover-v1.0.0.tar.gz` — 195 файлов, ~4.2 МБ;
- 🔐 `/storage/emulated/0/ПРОЕКТ/gapirai_handover/SHA256SUMS.txt` — контрольная сумма;
- 📘 внутри: `docs/DEPLOY_FOR_CLIENT.ru.md` — полный гайд развёртывания на **своём** домене/IP (placeholders `<ДОМЕН>`, `<IP_СЕРВЕРА>`): PostgreSQL/Redis, `.env`, systemd-юниты, сборка frontend, nginx + certbot, приёмочный сценарий, troubleshooting.

**Проверено:** в архиве нет `.env`, `cookies.txt`, `*.pem`, `node_modules`, `__pycache__`, `outputs/`, `uploads/`; `.env.example`, `deploy/nginx.conf`, `deploy/build_frontend.sh`, `deploy/migrations/` и гайд на месте. `mobile/` (Expo-приложение) в пакет не включён — это отдельный релиз (см. §4).

Заказчик разворачивает платформу на своих серверах; DNS/домен и платёжные credentials — его зона ответственности. Обновление домена `gapirai.uz` (ahost.uz → 185.233.184.192) и выпуск SSL остаются отдельными внешними шагами для текущего стенда.
