# GapirAI.uz — Руководство по развёртыванию (для заказчика)

> Версия пакета: 1.0.0 (2026-08-27)
> Платформа: AI-дубляж YouTube-видео на узбекский язык (FastAPI + Celery + Next.js + PostgreSQL + Redis)
>
> В этом документе — полная инструкция, как развернуть платформу на **вашем** сервере
> с **вашим** доменом. Все значения вида `<ДОМЕН>`, `<IP_СЕРВЕРА>`, `<пароль>`
> нужно заменить на свои.

---

## 1. Что входит в пакет

| Путь | Назначение |
|---|---|
| `backend/` | API (FastAPI), Celery-воркер, модель данных, сервисы (скачивание, TTS, сведение, оплата) |
| `frontend/` | Веб-интерфейс (Next.js) |
| `deploy/` | Готовые артефакты деплоя: `nginx.conf`, `build_frontend.sh`, `migrations/` |
| `.env.example` | Шаблон переменных окружения (скопировать в `.env`) |
| `docs/DEPLOY_FOR_CLIENT.ru.md` | Этот документ |
| `CHANGELOG.md`, `HANDOFF.md`, `REPORT_TECHNICAL.ru.md` | История изменений и аудит |

**В пакете нет секретов:** `.env`, файлы cookies, приватные ключи и данные пользователей
не передаются. Всё это создаётся на вашем сервере.

---

## 2. Требования к серверу

| Компонент | Версия / объём |
|---|---|
| ОС | Ubuntu 22.04 / 24.04 (Debian 12 подойдёт) |
| CPU/RAM | от 2 vCPU / 4 GB (8 GB рекомендуется — ffmpeg-сведение) |
| Диск | от 40 GB (готовые видео весят по ~150 МБ) |
| Python | 3.12 |
| Node.js | 20.x |
| PostgreSQL | 14+ |
| Redis | 7.x |
| ffmpeg | 6.x (с `libmp3lame`) |
| Домен | A-запись `@` и `www` указывают на IP вашего сервера |

---

## 3. Установка базового ПО

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip \
  postgresql postgresql-contrib redis-server nginx ffmpeg curl \
  ca-certificates

# Node.js 20 (LTS)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## 4. PostgreSQL и Redis

```bash
sudo systemctl enable --now postgresql redis-server

# База и пользователь (пароль придумайте свой)
sudo -u postgres psql <<'SQL'
CREATE USER gapirai WITH PASSWORD '<пароль_бд>';
CREATE DATABASE gapirai OWNER gapirai;
GRANT ALL PRIVILEGES ON DATABASE gapirai TO gapirai;
SQL
```

> Схема таблиц создаётся автоматически при первом старте API (`create_all`).
> SQL-файл из `deploy/migrations/` нужен **только** при обновлении уже существующей базы.

---

## 5. Распаковка и окружение

```bash
sudo mkdir -p /opt/gapirai
sudo tar -xzf gapirai-handover.tar.gz -C /opt/gapirai
cd /opt/gapirai

# Python-окружение
python3.12 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r backend/requirements.txt

# Файл окружения — из шаблона
cp .env.example .env
nano .env
```

Обязательные переменные в `.env`:

| Переменная | Пример | Комментарий |
|---|---|---|
| `DATABASE_URL` | `postgresql://gapirai:<пароль_бд>@localhost:5432/gapirai` | строка подключения |
| `ASYNC_DATABASE_URL` | `postgresql+asyncpg://gapirai:<пароль_бд>@localhost:5432/gapirai` | для async-кода |
| `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | как в шаблоне |
| `SECRET_KEY` | сгенерируйте: `openssl rand -hex 32` | безопасность JWT |
| `FRONTEND_URL` | `https://<ДОМЕН>` | для редиректов оплаты |
| `TTS_PROVIDER` | `edge` | движок озвучки (см. шаблон: elevenlabs/azure/edge/openai/gemini/uzbekvoice) |
| `AUDIO_MIX_MODE` | `dubbed_only` | режим по умолчанию: `dubbed_only` (чистый дубляж) / `ducked_mix` (оригинал+перевод) |
| `OPENAI_API_KEY` | `sk-...` | нужно, если используете OpenAI-модель/whisper |
| `CLICK_MERCHANT_ID` и `CLICK_SECRET_KEY` | от платёжного провайдера | только если подключаете оплату Click |

Опционально: `GOOGLE_CLIENT_ID` (вход через Google), `ESKIZ_EMAIL/PASSWORD` (SMS-коды),
`YOUTUBE_EMAIL/PASSWORD` и proxy-переменные (если сервер в дата-центре и YouTube
блокирует IP — см. комментарии в шаблоне).

---

## 6. Запуск сервисов (systemd)

Создайте три unit-файла:

**`/etc/systemd/system/gapirai-api.service`**
```ini
[Unit]
Description=GapirAI.uz FastAPI backend
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
Type=simple
WorkingDirectory=/opt/gapirai
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/gapirai/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/gapirai-worker.service`**
```ini
[Unit]
Description=GapirAI.uz Celery worker
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
WorkingDirectory=/opt/gapirai
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/gapirai/venv/bin/celery -A backend.workers.celery_app worker -l info -Q video_processing_priority,video_processing -c 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/gapirai-frontend.service`**
```ini
[Unit]
Description=GapirAI.uz Next.js frontend (standalone)
After=network.target
Wants=network.target

[Service]
Type=simple
WorkingDirectory=/opt/gapirai/frontend/.next/standalone
Environment=PORT=3000
Environment=HOSTNAME=127.0.0.1
ExecStartPre=/bin/bash -c 'test -d /opt/gapirai/frontend/.next/standalone/.next/static || (cp -r /opt/gapirai/frontend/.next/static /opt/gapirai/frontend/.next/standalone/.next/static && cp -r /opt/gapirai/frontend/public /opt/gapirai/frontend/.next/standalone/public 2>/dev/null || true)'
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Сборка фронтенда и запуск:

```bash
# Каталоги для файлов
mkdir -p /opt/gapirai/outputs /opt/gapirai/uploads

# Сборка Next.js standalone (займёт несколько минут)
bash /opt/gapirai/deploy/build_frontend.sh

# Включить и запустить
sudo systemctl daemon-reload
sudo systemctl enable --now gapirai-api gapirai-worker gapirai-frontend
```

---

## 7. nginx + SSL (ваш домен)

Скопируйте шаблон и замените домен:

```bash
sudo cp /opt/gapirai/deploy/nginx.conf /etc/nginx/sites-available/gapirai
sudo nano /etc/nginx/sites-available/gapirai
```

В шаблоне замените `gapirai.uz www.gapirai.uz 185.233.184.192 _` на
`<ДОМЕН> www.<ДОМЕН> <IP_СЕРВЕРА> _`, а в `location /outputs/` — путь на `/opt/gapirai/outputs/`.

```bash
sudo ln -s /etc/nginx/sites-available/gapirai /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

**HTTPS (Let's Encrypt):**

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <ДОМЕН> -d www.<ДОМЕН>
```

Certbot сам пропишет SSL и настроит редирект с HTTP на HTTPS.

---

## 8. Проверка после установки

```bash
# 1. Сервисы активны
systemctl --no-pager --full status gapirai-api gapirai-worker gapirai-frontend

# 2. Health — должен вернуть JSON, а не HTML
curl -sS https://<ДОМЕН>/health
# → {"status":"ok","service":"GapirAI.uz"}

# 3. Главная страница открывается
curl -sS -o /dev/null -w '%{http_code}\n' https://<ДОМЕН>/

# 4. Вход в аккаунт
curl -sS -o /dev/null -w '%{http_code}\n' https://<ДОМЕН>/login
# → 200

# 5. Логи воркера (после создания первого задания)
journalctl -u gapirai-worker -f
```

**Приёмка (ручной сценарий):**
1. Зарегистрируйтесь / войдите на `https://<ДОМЕН>/login`.
2. Вставьте ссылку на YouTube-видео и создайте дубляж.
3. В форме выберите режим: **«Faqat tarjima»** (чистый дубляж) или **«Tarjima + original fon»** (перевод поверх оригинала).
4. Дождитесь завершения (статус «Dublyaj tayyor!»), откройте ролик:
   - в плеере видео **воспроизводится** (ответ сервера `Content-Disposition: inline`, поддержка `206 Partial Content`);
   - кнопка **скачивания** отдаёт файл (`Content-Disposition: attachment`);
   - субтитры доступны (`/api/jobs/<id>/subtitles.vtt`).

---

## 9. Частые проблемы

| Симптом | Причина | Решение |
|---|---|---|
| `https://<ДОМЕН>/health` возвращает HTML 404 | Домен не попадает в server block nginx (или DNS указывает не на ваш сервер) | Проверьте A-запись домена → IP сервера; в `sites-enabled` должен быть только ваш конфиг с `server_name <ДОМЕН>` |
| Видео скачивается вместо воспроизведения | Кнопка использует `?download=1`, плеер — обычный URL | Проверьте, что `<video>` берёт URL без `download`, а кнопка — с `download=true` |
| «Video fayl endi mavjud emas» (410) | Файл удалён по TTL-очистке | В `config.py` увеличьте срок хранения или включите S3-хранилище |
| YouTube не скачивает видео на сервере | IP дата-центра в блэклисте YouTube | Настройте `YOUTUBE_PROXY_URL` (см. комментарии в `.env.example`) |
| Не приходят SMS-коды | Не настроен Eskiz | Заполните `ESKIZ_EMAIL`/`ESKIZ_PASSWORD` или включите вход по email-коду |
| Сайт «падает» при нагрузке | Мало RAM на воркер | Поднимите до 8 GB, воркер `-c 2` оставьте |

---

## 10. Обновление платформы

Обновление идёт аддитивно (существующие данные не трогаются):

```bash
cd /opt/gapirai
# 1. Заменить файлы кода из нового пакета
# 2. Если в пакете есть deploy/migrations/*.sql — применить к БД:
#    psql "$DATABASE_URL" -f deploy/migrations/<файл>.sql
# 3. Пересобрать фронтенд
bash deploy/build_frontend.sh
# 4. Перезапустить сервисы
sudo systemctl restart gapirai-api gapirai-worker gapirai-frontend
```

> Перед обновлением сделайте резервную копию БД:
> `sudo -u postgres pg_dump gapirai > gapirai_backup_$(date +%F).sql`
