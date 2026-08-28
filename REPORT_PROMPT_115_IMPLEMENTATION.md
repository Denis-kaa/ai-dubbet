# 📋 Отчёт: Реализация промта 115 — Multi-User Concurrency, Fairness & Dynamic Scaling

**Проект:** ai-dubber (GapirAI.uz — YouTube video dubbing platform)
**Дата:** 2026-08-28
**Промт:** `pompts_11/115.md`
**Статус:** Фазы 1–6 реализованы, 76 unit-тестов пройдены

---

## 1. Цель промта 115

Реализовать **мульти-юзерную архитектуру** с:
- Shared Worker Pool (NOT per-user)
- Per-user concurrency limits
- Fair scheduling (round-robin между пользователями)
- Separate queues (TTS vs Media)
- Sliding window для chunk processing
- Backpressure (TTS ↔ Media buffer control)
- TTFP метрики (Time To First Playable)

---

## 2. Что было до реализации (Audit)

| Компонент | Было | Проблема |
|---|---|---|
| Worker Pool | Один `worker -c 4` на всё | TTS и Media делят ресурсы |
| Queues | `video_processing`, `tts_processing`, `media_processing` | Очереди разделены, но worker один |
| Per-user limits | ❌ Не было | Pro юзер может забить очередь |
| Fair scheduling | ❌ Не было | Round-robin отсутствует |
| Sliding window | `chunked_pipeline.py` (180s chunks) | Все chunks сразу в очереди |
| Backpressure | ❌ Не было | TTS генерирует бесконтрольно |
| TTFP метрики | ❌ Не было | Нет измерения времени до первого playable |
| Cache | `tts_cache.py` | По video_id + voice |
| Idempotency | Redis NX-lock | ✅ Уже было |
| Recovery | `recover_stuck_jobs()` | ✅ Уже было |

---

## 3. Что реализовано

### Фаза 1: Разделение Workers (docker-compose.yml)

**Файл:** `docker-compose.yml` (изменён, +46 строк)

```yaml
# БЫЛО:
worker:
  command: celery -A backend.workers.celery_app worker -c 4 ...

# СТАЛО:
worker-video:
  command: celery -A backend.workers.celery_app worker -c 2 -Q video_processing ...
worker-tts:
  command: celery -A backend.workers.celery_app worker -c 4 -Q tts_processing ...
worker-media:
  command: celery -A backend.workers.celery_app worker -c 2 -Q media_processing ...
```

**Итого:** 3 отдельных worker контейнера с изолированными ресурсами.

---

### Фаза 2+3: Fair Scheduler + Per-User Limits

**Файл:** `backend/services/scheduler.py` (новый, 290 строк)

**Константы (промт 115 §4-5):**
```python
MAX_CONCURRENT_JOBS_PER_USER = 2
MAX_TTS_TASKS_PER_USER = 2
MAX_MEDIA_TASKS_PER_USER = 1
MAX_TOTAL_TTS_WORKERS = 4
MAX_TOTAL_MEDIA_WORKERS = 2
MAX_TOTAL_JOBS = 10
```

**Ключевые методы:**
| Метод | Назначение |
|---|---|
| `can_accept_job(user_id)` | Per-user + global limit check |
| `can_accept_tts(user_id)` | TTS limit check |
| `can_accept_media(user_id)` | Media limit check |
| `register_active_job(user_id, job_id)` | Зарегистрировать активную задачу |
| `release_job(user_id, job_id)` | Освободить задачу |
| `get_next_user()` | Round-robin: следующий пользователь |
| `get_stats()` | Статистика scheduler'а |

**Архитектура:**
- Redis-backed (для multi-worker) + in-memory fallback (для single process)
- Lazy Redis init (не создаёт соединение при импорте)
- Singleton через `get_scheduler()`

---

### Фаза 4: Sliding Window

**Файл:** `backend/services/sliding_window.py` (новый, 200 строк)

**Константы:**
```python
window_size = settings.MAX_PARALLEL_CHUNKS  #.typically 3
```

**Ключевые методы:**
| Метод | Назначение |
|---|---|
| `init_chunks(chunk_ids)` | Инициализация chunks |
| `get_next_window()` | Chunks в текущем окне (QUEUED/FAILED) |
| `start_chunk(chunk_id)` | → PROCESSING |
| `complete_chunk(chunk_id)` | → READY + advance window |
| `fail_chunk(chunk_id, error)` | → FAILED (retry eligible) |
| `publish_chunk(chunk_id)` | → PUBLISHED |
| `is_complete()` | Все READY/PUBLISHED? |
| `get_ready_chunks()` | Для progressive playback |
| `get_buffer_status()` | Counts by status + window position |

**Состояния chunk:**
```
QUEUED → PROCESSING → READY → PUBLISHED
                ↓
             FAILED (→ QUEUED для retry)
```

**Window advancement:**
```
Position 0: [c0, c1, c2] → c0 ready → Position 1: [c1, c2, c3]
Position 1: [c1, c2, c3] → c1, c2 ready → Position 2: [c2, c3, c4]
```

---

### Фаза 5: Backpressure

**Файл:** `backend/services/backpressure.py` (новый, 175 строк)

**Константы (промт 115 §8-9):**
```python
TTS_MAX_PENDING = 6      # максимум TTS chunks в очереди Media
MEDIA_MAX_ACTIVE = 2     # максимум параллельных Media tasks
BUFFER_HIGH_WATER = 4    # "высокий" — замедляем TTS
BUFFER_LOW_WATER = 2     # "низкий" — TTS на полной скорости
```

**Ключевые методы:**
| Метод | Назначение |
|---|---|
| `can_produce_tts(job_id)` | False если buffer满 или Media overloaded |
| `is_throttled(job_id)` | TTS замедлен? |
| `get_backoff_seconds(job_id)` | 0.0 / 0.5 / 2.0 / 5.0 |
| `register_tts_produced(job_id, chunk_id)` | tts_pending++ |
| `register_media_consumed(job_id, chunk_id)` | tts_pending-- |
| `register_media_started(job_id, chunk_id)` | media_active++ |
| `register_media_finished(job_id, chunk_id)` | media_active-- |
| `cleanup_job(job_id)` | Очистить state |
| `get_stats()` | Глобальная статистика |

**Backoff levels:**
```
tts_pending < 2:   0.0s (no delay)
tts_pending 2-3:   0.5s (minimal)
tts_pending 4-5:   2.0s (medium)
tts_pending >= 6:  5.0s (maximum)
```

---

### Фаза 6: TTFP Metrics

**Файл:** `backend/services/metrics.py` (новый, 195 строк)

**Метрики (промт 115 §12-13):**
| Метрика | Описание |
|---|---|
| TTFP | Time To First Playable (секунды) |
| Total Processing | Общее время обработки |
| Queue Wait | Время ожидания в очереди |
| TTS Latency | Latency TTS per chunk |
| Media Latency | Latency Media per chunk |

**Percentiles:** P50, P90, P95, P99, avg, min, max, count

**Ключевые методы:**
| Метод | Назначение |
|---|---|
| `start_job(user_id, job_id)` | Начать отслеживание |
| `record_ttfp(job_id, chunk_id)` | Первый READY chunk → TTFP |
| `record_tts_latency(job_id, chunk_id, sec)` | TTS latency |
| `record_media_latency(job_id, chunk_id, sec)` | Media latency |
| `record_queue_wait(job_id, sec)` | Queue wait |
| `record_chunk_completed(job_id)` | chunks_completed++ |
| `record_chunk_failed(job_id)` | chunks_failed++ |
| `set_chunks_total(job_id, total)` | chunks_total = N |
| `end_job(job_id)` | total_processing = now - start |
| `get_job_metrics(job_id)` | Метрики одного job |
| `get_report()` | Полный отчёт + per-user stats |

---

## 4. Интеграция в tasks.py

**Файл:** `backend/workers/tasks.py` (изменён, +158 строк, -21 строка)

### 6 точек интеграции:

| # | Место | Вызовы |
|---|---|---|
| 1 | После lock acquisition | `_scheduler.can_accept_job()` + `_scheduler.register_active_job()` |
| 2 | После загрузки job | `_metrics.start_job(user_id, job_id)` |
| 3 | Chunked pipeline (TTS) | `_backpressure.can_produce_tts()` → sleep(backoff) → `register_tts_produced()` |
| 4 | Chunked pipeline (Media) | `register_media_started()` → MERGE → `register_media_consumed()` + `register_media_finished()` |
| 5 | Каждый chunk | `window.start_chunk()` → TTS → Media → `window.complete_chunk()` → `_metrics.record_ttfp()` |
| 6 | COMPLETED/FAILED | `_metrics.end_job()` + `_scheduler.release_job()` + `_backpressure.cleanup_job()` |

### Sliding Window + Backpressure в chunked pipeline:

```python
# Инициализация
chunk_ids = [f"{job_id}_c{i}" for i in range(len(video_chunks))]
window = ChunkWindow(job_id=job_id, window_size=settings.MAX_PARALLEL_CHUNKS)
window.init_chunks(chunk_ids)
_metrics.set_chunks_total(job_id, len(video_chunks))

# Thread-safe backpressure
_bp_lock = threading.Lock()

def _process_chunk(chunk_idx):
    chunk_id = f"{job_id}_c{chunk_idx}"

    # Backpressure check
    with _bp_lock:
        while not _backpressure.can_produce_tts(job_id):
            backoff = _backpressure.get_backoff_seconds(job_id)
            time.sleep(backoff)
        _backpressure.register_tts_produced(job_id, chunk_id)

    # Window: start
    window.start_chunk(chunk_id)
    chunk_t0 = time.monotonic()

    # TTS
    chunk_audio, _, _ = synthesizer.synthesize_segments(...)
    tts_latency = time.monotonic() - chunk_t0
    _metrics.record_tts_latency(job_id, chunk_id, tts_latency)

    # Media
    with _bp_lock:
        _backpressure.register_media_started(job_id, chunk_id)

    media_t0 = time.monotonic()
    merger.merge_video_audio_chunk(...)
    media_latency = time.monotonic() - media_t0
    _metrics.record_media_latency(job_id, chunk_id, media_latency)

    # Backpressure: consumed + finished
    with _bp_lock:
        _backpressure.register_media_consumed(job_id, chunk_id)
        _backpressure.register_media_finished(job_id, chunk_id)

    # Window: complete
    window.complete_chunk(chunk_id)
    _metrics.record_chunk_completed(job_id)
    _metrics.record_ttfp(job_id, chunk_id)  # only first chunk records TTFP

# Sliding window loop
while not window.is_complete():
    next_chunks = window.get_next_window()
    for chunk_id in next_chunks:
        executor.submit(_process_chunk, chunk_idx)
    done, _ = concurrent.futures.wait(futures, timeout=1.0, return_when=FIRST_COMPLETED)
```

---

## 5. Тесты

### 5.1 Тесты scheduler (25 тестов)

```
tests/test_scheduler.py
├── TestCanAcceptJob (6 тестов)
│   ├── test_empty_user_can_accept
│   ├── test_user_below_limit_can_accept
│   ├── test_user_at_limit_cannot_accept
│   ├── test_different_users_independent
│   ├── test_global_limit
│   └── test_after_release_can_accept_again
├── TestCanAcceptTTS (3 теста)
│   ├── test_empty_can_accept
│   ├── test_user_at_tts_limit
│   └── test_global_tts_limit
├── TestCanAcceptMedia (3 теста)
│   ├── test_empty_can_accept
│   ├── test_user_at_media_limit
│   └── test_global_media_limit
├── TestRegisterRelease (7 тестов)
│   ├── test_register_increments_count
│   ├── test_register_same_job_twice
│   ├── test_release_removes_job
│   ├── test_release_all_removes_user
│   ├── test_release_nonexistent_is_safe
│   ├── test_tts_register_release
│   └── test_media_register_release
├── TestRoundRobin (4 теста)
│   ├── test_no_users_returns_none
│   ├── test_single_user_returns_that_user
│   ├── test_round_robin_cycles
│   └── test_user_removed_from_round_robin
└── TestStats (2 теста)
    ├── test_empty_stats
    └── test_stats_after_operations
```

### 5.2 Тесты sliding_window (25 тестов)

```
tests/test_sliding_window.py
├── TestInitChunks (2 теста)
│   ├── test_initial_status_queued
│   └── test_initial_position_zero
├── TestGetNextWindow (4 теста)
│   ├── test_first_window_returns_first_n_chunks
│   ├── test_smaller_window
│   ├── test_after_starting_chunks_not_returned_again
│   └── test_empty_after_all_processing
├── TestChunkTransitions (4 теста)
│   ├── test_start_sets_processing
│   ├── test_complete_sets_ready
│   ├── test_complete_unknown_chunk_no_crash
│   └── test_start_unknown_chunk_no_crash
├── TestWindowAdvancement (3 теста)
│   ├── test_window_advances_after_first_chunk_ready
│   ├── test_window_advances_multiple
│   └── test_window_does_not_advance_if_middle_not_ready
├── TestFailChunk (2 теста)
│   ├── test_fail_sets_status
│   └── test_failed_chunk_returned_in_next_window
├── TestPublishChunk (2 теста)
│   ├── test_publish_sets_status
│   └── test_published_chunk_advances_window
├── TestIsComplete (4 теста)
│   ├── test_not_complete_initially
│   ├── test_complete_after_all_ready
│   ├── test_complete_after_all_published
│   └── test_not_complete_with_failed
├── TestGetReadyChunks (2 теста)
│   ├── test_empty_initially
│   └── test_returns_ready_in_order
└── TestBufferStatus (2 теста)
    ├── test_all_fields_present
    └── test_counts_consistent
```

### 5.3 Тесты backpressure (26 тестов)

```
tests/test_backpressure.py
├── TestCanProduceTTS (6 тестов)
│   ├── test_empty_can_produce
│   ├── test_below_limit_can_produce
│   ├── test_at_limit_cannot_produce
│   ├── test_media_overloaded_cannot_produce
│   ├── test_after_media_finished_can_produce_again
│   └── test_independent_jobs
├── TestIsThrottled (3 теста)
│   ├── test_not_throttled_initially
│   ├── test_throttled_at_limit
│   └── test_unthrottled_after_consume
├── TestGetBackoff (4 теста)
│   ├── test_no_backoff_when_empty
│   ├── test_min_backoff_at_low_water
│   ├── test_med_backoff_at_high_water
│   └── test_max_backoff_at_limit
├── TestRegisterLifecycle (7 тестов)
│   ├── test_tts_produced_increments_pending
│   ├── test_media_consumed_decrements_pending
│   ├── test_media_started_increments_active
│   ├── test_media_finished_decrements_active
│   ├── test_full_lifecycle
│   ├── test_pending_never_negative
│   └── test_media_active_never_negative
├── TestStats (3 теста)
│   ├── test_empty_stats
│   ├── test_stats_per_job
│   └── test_throttled_jobs_counted
└── TestCleanup (3 теста)
    ├── test_cleanup_removes_job_state
    ├── test_cleanup_nonexistent_is_safe
    └── test_cleanup_does_not_affect_other_jobs
```

### Результаты тестов

```
76 passed in 0.41s
warnings: 1 (pydantic deprecation — не связано с изменениями)
```

---

## 6. Сводная таблица изменений

### Новые файлы (8)

| Файл | Строки | Описание |
|---|---|---|
| `backend/services/scheduler.py` | 290 | Fair Scheduler + per-user limits |
| `backend/services/sliding_window.py` | 200 | Sliding window для chunks |
| `backend/services/backpressure.py` | 175 | TTS ↔ Media buffer control |
| `backend/services/metrics.py` | 195 | TTFP + latency metrics |
| `tests/__init__.py` | 0 | Test package |
| `tests/test_scheduler.py` | 220 | 25 unit-тестов |
| `tests/test_sliding_window.py` | 210 | 25 unit-тестов |
| `tests/test_backpressure.py` | 230 | 26 unit-тестов |

**Итого новых:** ~1,520 строк

### Изменённые файлы (2)

| Файл | + / - | Описание |
|---|---|---|
| `docker-compose.yml` | +46 / -21 | 3 worker контейнера вместо 1 |
| `backend/workers/tasks.py` | +158 / -21 | Интеграция 4 сервисов |

**Итого изменений:** +225 / -42 = net +183 строки

### Общая статистика

| Метрика | Значение |
|---|---|
| **Новых файлов** | 8 |
| **Изменённых файлов** | 2 |
| **Всего строк (новые)** | ~1,520 |
| **Всего строк (изменения)** | ~225 |
| **Unit-тестов** | 76 |
| **Тесты пройдены** | 76/76 ✅ |
| **Время тестов** | 0.41s |

---

## 7. Архитектура после изменений

```
┌─────────────────────────────────────────────────────────────────┐
│                        USERS (N)                                │
│  user_1 (free)    user_2 (standard)    user_3 (pro)            │
└─────────┬─────────────────┬───────────────────┬─────────────────┘
          │                 │                   │
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FAIR SCHEDULER                                │
│  Per-user limit: 2 jobs    Global limit: 10 jobs               │
│  Round-robin fairness       Pro priority (TODO)                │
└─────────┬─────────────────┬───────────────────┬─────────────────┘
          │                 │                   │
          ▼                 ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ video_processing │ │ tts_processing   │ │ media_processing │
│    (Queue)       │ │    (Queue)       │ │    (Queue)       │
└────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
         │                    │                     │
         ▼                    ▼                     ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  worker-video    │ │   worker-tts     │ │  worker-media    │
│    (-c 2)        │ │    (-c 4)        │ │    (-c 2)        │
└──────────────────┘ └────────┬─────────┘ └────────┬─────────┘
                              │                     │
                              ▼                     ▼
                    ┌──────────────────────────────────────┐
                    │          BACKPRESSURE                 │
                    │  TTS_MAX_PENDING = 6                  │
                    │  MEDIA_MAX_ACTIVE = 2                 │
                    │  Buffer: 0/0.5/2.0/5.0s backoff      │
                    └──────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────────────────────────┐
                    │        SLIDING WINDOW                 │
                    │  Window size = MAX_PARALLEL_CHUNKS    │
                    │  Progressive: c0 → c1 → c2 → ...     │
                    └──────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────────────────────────┐
                    │          METRICS                      │
                    │  TTFP, TTS latency, Media latency    │
                    │  P50/P90/P95/P99 per user            │
                    └──────────────────────────────────────┘
```

---

## 8. Что НЕ реализовано (из промта 115)

| # | Требование | Статус | Причина |
|---|---|---|---|
| 7 | Cache deduplication по video_id + voice | ⚠️ Было частично | `tts_cache.py` существует, нужна интеграция |
| 8 | Adaptive resource scheduler (load-based) | ❌ Не реализовано | Фаза 8, effort 4-6 часов |
| 9 | Pro priority с fairness preservation | ❌ Not implemented | `should_preempt_for_priority()` = stub |
| 10 | Modal integration | ❌ Не исследовано | Promt 115 §15: "исследовать" |
| 11 | Progressive playback (frontend) | ❌ Backend-only | Frontend не тронут |
| 12 | Idempotency key versioning | ⚠️ Было | Redis NX-lock уже работает |
| 13 | Recovery enhanced | ⚠️ Было | `recover_stuck_jobs()` уже работает |

---

## 9. Рекомендации для следующего агента

### Приоритет 1 (важно для production)
1. **Pro priority fairness** — реализовать `should_preempt_for_priority()` в scheduler.py
2. **Cache deduplication** — интегрировать `tts_cache.py` с video_id + voice + settings key
3. **Load test** — сценарии из промта 115 §12 (1×1, 2×1, 5×1, 10×1, 1×10, 5×3)

### Приоритет 2 (комфорт)
4. **Adaptive scheduler** — динамическое изменение window_size и worker concurrency
5. **Metrics persistence** — сохранение метрик в Redis/DB для historical analysis
6. **Admin dashboard** — отображение scheduler stats, backpressure, TTFP

### Приоритет 3 (исследования)
7. **Modal integration** — elastic compute для TTS/Media burst
8. **Frontend progressive playback** — chunk-by-chunk streaming

### Известные ограничения
- Backpressure lock (`_bp_lock`) — `threading.Lock()`, безопасно для `ThreadPoolExecutor` но не для `multiprocessing`
- `__import__("concurrent.futures")` в sliding window loop — работает но некрасиво, можно вынести
- Scheduler singleton — в multi-process Celery каждый worker процесс имеет свой экземпляр (Redis обеспечивает консистентность)

---

## 10. Связанные файлы

| Файл | Роль |
|---|---|
| `pompts_11/115.md` | Исходный промт |
| `backend/services/scheduler.py` | Fair Scheduler |
| `backend/services/sliding_window.py` | Sliding Window |
| `backend/services/backpressure.py` | Backpressure Controller |
| `backend/services/metrics.py` | TTFP Metrics |
| `backend/workers/tasks.py` | Celery task (интеграция) |
| `backend/workers/celery_app.py` | Celery config (task_routes) |
| `docker-compose.yml` | 3 worker контейнера |
| `tests/test_scheduler.py` | 25 unit-тестов |
| `tests/test_sliding_window.py` | 25 unit-тестов |
| `tests/test_backpressure.py` | 26 unit-тестов |
