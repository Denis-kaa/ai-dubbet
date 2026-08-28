"""
Fair Scheduler — Per-user concurrency limits + Round-robin fairness.

Архитектура (промт 115 §4-6):
  Users → Jobs → Chunks → Scheduler → Queues

Scheduler соблюдает:
  - Per-user limits (MAX_CONCURRENT_JOBS_PER_USER)
  - Global limits (MAX_TOTAL_TTS_WORKERS, MAX_TOTAL_MEDIA_WORKERS)
  - Fair scheduling (round-robin между пользователями)
  - Priority (Pro users) с сохранением fairness

Использование:
    from backend.services.scheduler import FairScheduler
    scheduler = FairScheduler()
    can_enqueue = scheduler.can_accept_job(user_id="user_123")
    scheduler.register_active_job(user_id="user_123", job_id="job_456")
    scheduler.release_job(user_id="user_123", job_id="job_456")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from backend.config import get_settings

settings = get_settings()

# ─── Per-user limits (промт 115 §4) ─────────────────────────
MAX_CONCURRENT_JOBS_PER_USER = 2
MAX_TTS_TASKS_PER_USER = 2
MAX_MEDIA_TASKS_PER_USER = 1

# ─── Global limits (промт 115 §5) ───────────────────────────
MAX_TOTAL_TTS_WORKERS = 4
MAX_TOTAL_MEDIA_WORKERS = 2
MAX_TOTAL_JOBS = 10

# ─── Resource budgets (промт 115 §9) ────────────────────────
TTS_CONCURRENCY = 4
MEDIA_CONCURRENCY = 2

# ─── Priority tiers (промт 115 §7) ─────────────────────────
# Pro users получают приоритет, НО fairness сохраняется:
# - Pro идут первыми, но не более 2 подряд
# - После 2 Pro подряд — mandatory turn для non-Pro
# - Историка выбора хранится для anti-starvation проверки
PRIORITY_FREE = 1
PRIORITY_STANDARD = 5
PRIORITY_PRO = 10

# Anti-starvation: максимум подряд Pro перед mandatory non-Pro turn
MAX_CONSECUTIVE_PRO = 2

# Default priority для неизвестных пользователей
DEFAULT_PRIORITY = PRIORITY_FREE

# ─── Redis keys ──────────────────────────────────────────────
_ACTIVE_JOBS_KEY = "scheduler:active_jobs:{user_id}"
_ACTIVE_TTS_KEY = "scheduler:active_tts:{user_id}"
_ACTIVE_MEDIA_KEY = "scheduler:active_media:{user_id}"
_GLOBAL_ACTIVE_KEY = "scheduler:global_active"
_ROUND_ROBIN_KEY = "scheduler:round_robin_pointer"
_QUEUE_DEPTH_KEY = "scheduler:queue_depth:{queue}"
PRIORITY_KEY = "scheduler:priority:{user_id}"


@dataclass
class SchedulerStats:
    """Статистика scheduler'а."""
    active_jobs: Dict[str, int] = field(default_factory=dict)  # user_id → count
    active_tts: Dict[str, int] = field(default_factory=dict)
    active_media: Dict[str, int] = field(default_factory=dict)
    user_priorities: Dict[str, int] = field(default_factory=dict)  # user_id → priority
    total_active: int = 0
    total_active_tts: int = 0
    total_active_media: int = 0
    queue_depths: Dict[str, int] = field(default_factory=dict)
    round_robin_pointer: int = 0
    consecutive_pro_count: int = 0  # сколько Pro подряд выбрано


class FairScheduler:
    """Fair scheduler с per-user limits и round-robin fairness."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis: Any = None
        self._local_active_jobs: Dict[str, Set[str]] = {}  # user_id → {job_ids}
        self._local_active_tts: Dict[str, int] = {}  # user_id → count
        self._local_active_media: Dict[str, int] = {}  # user_id → count
        self._round_robin_order: List[str] = []  # порядок round-robin
        self._round_robin_idx: int = 0
        # ─── Priority (промт 115 §7) ──────────────────────
        self._user_priorities: Dict[str, int] = {}  # user_id → priority
        self._consecutive_pro_count: int = 0  # сколько Pro подряд выбрано
        self._last_selected_was_pro: bool = False

    def _get_redis(self) -> Any:
        """Lazy init Redis."""
        if self._redis is None:
            try:
                from redis import Redis
                self._redis = Redis.from_url(
                    self._redis_url, decode_responses=True
                )
                self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    # ─── Per-user checks (промт 115 §4) ──────────────────────

    def can_accept_job(self, user_id: str) -> bool:
        """Проверяет, может ли пользователь создать новую задачу.

        Проверяет:
        - Per-user job limit
        - Global job limit
        """
        # Per-user limit
        user_count = self._count_active_jobs(user_id)
        if user_count >= MAX_CONCURRENT_JOBS_PER_USER:
            return False

        # Global limit
        total = self._count_global_active()
        if total >= MAX_TOTAL_JOBS:
            return False

        return True

    def can_accept_tts(self, user_id: str) -> bool:
        """Проверяет, может ли TTS task быть запущен для пользователя."""
        user_tts = self._count_active_tts(user_id)
        if user_tts >= MAX_TTS_TASKS_PER_USER:
            return False

        total_tts = self._count_global_active_tts()
        if total_tts >= MAX_TOTAL_TTS_WORKERS:
            return False

        return True

    def can_accept_media(self, user_id: str) -> bool:
        """Проверяет, может ли Media task быть запущен для пользователя."""
        user_media = self._count_active_media(user_id)
        if user_media >= MAX_MEDIA_TASKS_PER_USER:
            return False

        total_media = self._count_global_active_media()
        if total_media >= MAX_TOTAL_MEDIA_WORKERS:
            return False

        return True

    # ─── Registration (промт 115 §10) ────────────────────────

    def register_active_job(self, user_id: str, job_id: str) -> None:
        """Зарегистрировать активную задачу."""
        r = self._get_redis()
        if r:
            try:
                r.sadd(f"scheduler:active_jobs:{user_id}", job_id)
                r.incr("scheduler:global_active")
                # Round-robin: добавляем user если новый
                if not r.sismember("scheduler:active_users", user_id):
                    r.sadd("scheduler:active_users", user_id)
            except Exception:
                pass

        # Local fallback
        if user_id not in self._local_active_jobs:
            self._local_active_jobs[user_id] = set()
        self._local_active_jobs[user_id].add(job_id)

        if user_id not in self._round_robin_order:
            self._round_robin_order.append(user_id)

    def release_job(self, user_id: str, job_id: str) -> None:
        """Освободить задачу."""
        r = self._get_redis()
        if r:
            try:
                r.srem(f"scheduler:active_jobs:{user_id}", job_id)
                r.decr("scheduler:global_active")
                # Если у юзера нет активных задач — убираем из round-robin
                if r.scard(f"scheduler:active_jobs:{user_id}") == 0:
                    r.srem("scheduler:active_users", user_id)
            except Exception:
                pass

        if user_id in self._local_active_jobs:
            self._local_active_jobs[user_id].discard(job_id)
            if not self._local_active_jobs[user_id]:
                del self._local_active_jobs[user_id]
                if user_id in self._round_robin_order:
                    self._round_robin_order.remove(user_id)

    def register_tts_task(self, user_id: str, job_id: str, chunk_id: str) -> None:
        """Зарегистрировать активную TTS задачу."""
        r = self._get_redis()
        if r:
            try:
                r.incr(f"scheduler:active_tts:{user_id}")
                r.incr("scheduler:global_active_tts")
            except Exception:
                pass
        self._local_active_tts[user_id] = self._local_active_tts.get(user_id, 0) + 1

    def release_tts_task(self, user_id: str, job_id: str, chunk_id: str) -> None:
        """Освободить TTS задачу."""
        r = self._get_redis()
        if r:
            try:
                r.decr(f"scheduler:active_tts:{user_id}")
                r.decr("scheduler:global_active_tts")
            except Exception:
                pass
        self._local_active_tts[user_id] = max(0, self._local_active_tts.get(user_id, 0) - 1)

    def register_media_task(self, user_id: str, job_id: str, chunk_id: str) -> None:
        """Зарегистрировать активную Media задачу."""
        r = self._get_redis()
        if r:
            try:
                r.incr(f"scheduler:active_media:{user_id}")
                r.incr("scheduler:global_active_media")
            except Exception:
                pass
        self._local_active_media[user_id] = self._local_active_media.get(user_id, 0) + 1

    def release_media_task(self, user_id: str, job_id: str, chunk_id: str) -> None:
        """Освободить Media задачу."""
        r = self._get_redis()
        if r:
            try:
                r.decr(f"scheduler:active_media:{user_id}")
                r.decr("scheduler:global_active_media")
            except Exception:
                pass
        self._local_active_media[user_id] = max(0, self._local_active_media.get(user_id, 0) - 1)

    # ─── Priority (промт 115 §7) ───────────────────────────

    def set_user_priority(self, user_id: str, priority: int) -> None:
        """Установить приоритет пользователя.

        Используй константы: PRIORITY_FREE=1, PRIORITY_STANDARD=5, PRIORITY_PRO=10.
        """
        self._user_priorities[user_id] = priority
        r = self._get_redis()
        if r:
            try:
                r.set(f"scheduler:priority:{user_id}", priority)
            except Exception:
                pass

    def get_user_priority(self, user_id: str) -> int:
        """Получить приоритет пользователя."""
        r = self._get_redis()
        if r:
            try:
                p = r.get(f"scheduler:priority:{user_id}")
                if p is not None:
                    return int(p)
            except Exception:
                pass
        return self._user_priorities.get(user_id, DEFAULT_PRIORITY)

    def _is_pro_user(self, user_id: str) -> bool:
        """Проверяет, является ли пользователь Pro."""
        return self.get_user_priority(user_id) >= PRIORITY_PRO

    # ─── Fair scheduling (промт 115 §6-7) ───────────────────

    def get_next_user(self) -> Optional[str]:
        """Priority-aware round-robin: вернуть следующего пользователя.

        Алгоритм (промт 115 §7):
        1. Если Pro user ожидает И не превышен лимит подряд (MAX_CONSECUTIVE_PRO):
           → выбрать Pro (приоритет)
        2. Иначе → round-robin среди ВСЕХ активных users
        3. Anti-starvation: после MAX_CONSECUTIVE_PRO подряд Pro →
           обязательный turn для non-Pro

        Гарантии:
        - Pro users получают приоритет (чаще обрабатываются первыми)
        - Non-Pro users НЕ блокируются бесконечно (fairness)
        - Максимум 2 Pro подряд, потом non-Pro
        """
        r = self._get_redis()
        active_users: List[str] = []
        if r:
            try:
                active_users = list(r.smembers("scheduler:active_users"))
            except Exception:
                pass
        else:
            active_users = list(self._round_robin_order)

        if not active_users:
            return None

        # ─── Anti-starvation check ───
        has_non_pro = any(not self._is_pro_user(u) for u in active_users)
        has_pro = any(self._is_pro_user(u) for u in active_users)

        # Если все users одного типа — простой round-robin
        if not has_non_pro or not has_pro:
            return self._plain_round_robin(active_users)

        # ─── Anti-starvation: force non-Pro после MAX_CONSECUTIVE_PRO ───
        if self._consecutive_pro_count >= MAX_CONSECUTIVE_PRO and has_non_pro:
            # ОБЯЗАТЕЛЬНЫЙ turn для non-Pro
            non_pro_users = [u for u in active_users if not self._is_pro_user(u)]
            user = self._pick_from_pool(non_pro_users)
            self._consecutive_pro_count = 0
            self._last_selected_was_pro = False
            return user

        # ─── Priority: Pro first (если есть Pro и лимит не превышен) ───
        if has_pro and self._consecutive_pro_count < MAX_CONSECUTIVE_PRO:
            pro_users = [u for u in active_users if self._is_pro_user(u)]
            user = self._pick_from_pool(pro_users)
            self._consecutive_pro_count += 1
            self._last_selected_was_pro = True
            return user

        # ─── Fallback: round-robin среди всех ───
        user = self._plain_round_robin(active_users)
        if user and self._is_pro_user(user):
            self._consecutive_pro_count += 1
            self._last_selected_was_pro = True
        else:
            self._consecutive_pro_count = 0
            self._last_selected_was_pro = False
        return user

    def _plain_round_robin(self, users: List[str]) -> Optional[str]:
        """Обычный round-robin среди списка users."""
        if not users:
            return None
        user = users[self._round_robin_idx % len(users)]
        self._round_robin_idx += 1
        return user

    def _pick_from_pool(self, pool: List[str]) -> Optional[str]:
        """Выбрать следующего user из пула (round-robin)."""
        if not pool:
            return None
        # Используем отдельный индекс для внутри-пулового round-robin
        user = pool[self._round_robin_idx % len(pool)]
        self._round_robin_idx += 1
        return user

    def should_preempt_for_priority(self, user_id: str) -> bool:
        """Определяет, стоит ли дать приоритет Pro пользователю.

        Pro users получают приоритет, НО:
        - Не более MAX_CONSECUTIVE_PRO подряд
        - Non-Pro users гарантированно получают turn
        """
        priority = self.get_user_priority(user_id)

        # Non-Pro никогда не preempt'ит
        if priority < PRIORITY_PRO:
            return False

        # Pro может preempt если:
        # 1. Не превышен лимит подряд ИЛИ
        # 2. Нет non-Pro в очереди (все Pro)
        if self._consecutive_pro_count < MAX_CONSECUTIVE_PRO:
            return True

        # Лимит превышен — только если нет non-Pro (all-Pro очередь)
        return not any(
            not self._is_pro_user(u)
            for u in self._local_active_jobs.keys()
        )

    # ─── Stats (промт 115 §14) ───────────────────────────────

    def get_stats(self) -> SchedulerStats:
        """Статистика scheduler'а."""
        r = self._get_redis()
        stats = SchedulerStats()

        if r:
            try:
                # Per-user counts
                users = list(r.smembers("scheduler:active_users"))
                for user in users:
                    stats.active_jobs[user] = r.scard(f"scheduler:active_jobs:{user}") or 0
                    stats.active_tts[user] = int(r.get(f"scheduler:active_tts:{user}") or 0)
                    stats.active_media[user] = int(r.get(f"scheduler:active_media:{user}") or 0)

                stats.total_active = int(r.get("scheduler:global_active") or 0)
                stats.total_active_tts = int(r.get("scheduler:global_active_tts") or 0)
                stats.total_active_media = int(r.get("scheduler:global_active_media") or 0)
                stats.round_robin_pointer = int(r.get("scheduler:round_robin_pointer") or 0)
            except Exception:
                pass

        # Local fallback
        if not stats.active_jobs:
            for uid, jobs in self._local_active_jobs.items():
                stats.active_jobs[uid] = len(jobs)
            stats.total_active = sum(stats.active_jobs.values())
            stats.active_tts = dict(self._local_active_tts)
            stats.active_media = dict(self._local_active_media)
            stats.total_active_tts = sum(stats.active_tts.values())
            stats.total_active_media = sum(stats.active_media.values())

        # Priority info
        stats.user_priorities = dict(self._user_priorities)
        stats.consecutive_pro_count = self._consecutive_pro_count

        return stats

    # ─── Private ──────────────────────────────────────────────

    def _count_active_jobs(self, user_id: str) -> int:
        """Считает активные задачи пользователя."""
        r = self._get_redis()
        if r:
            try:
                return r.scard(f"scheduler:active_jobs:{user_id}") or 0
            except Exception:
                pass
        return len(self._local_active_jobs.get(user_id, set()))

    def _count_global_active(self) -> int:
        """Считает глобально активные задачи."""
        r = self._get_redis()
        if r:
            try:
                return int(r.get("scheduler:global_active") or 0)
            except Exception:
                pass
        return sum(len(jobs) for jobs in self._local_active_jobs.values())

    def _count_active_tts(self, user_id: str) -> int:
        """Считает активные TTS задачи пользователя."""
        r = self._get_redis()
        if r:
            try:
                return int(r.get(f"scheduler:active_tts:{user_id}") or 0)
            except Exception:
                pass
        return self._local_active_tts.get(user_id, 0)

    def _count_global_active_tts(self) -> int:
        """Считает глобально активные TTS задачи."""
        r = self._get_redis()
        if r:
            try:
                return int(r.get("scheduler:global_active_tts") or 0)
            except Exception:
                pass
        return sum(self._local_active_tts.values())

    def _count_active_media(self, user_id: str) -> int:
        """Считает активные Media задачи пользователя."""
        r = self._get_redis()
        if r:
            try:
                return int(r.get(f"scheduler:active_media:{user_id}") or 0)
            except Exception:
                pass
        return self._local_active_media.get(user_id, 0)

    def _count_global_active_media(self) -> int:
        """Считает глобально активные Media задачи."""
        r = self._get_redis()
        if r:
            try:
                return int(r.get("scheduler:global_active_media") or 0)
            except Exception:
                pass
        return sum(self._local_active_media.values())


# ─── Singleton ────────────────────────────────────────────────

_scheduler_instance: Optional[FairScheduler] = None


def get_scheduler() -> FairScheduler:
    """Возвращает singleton FairScheduler."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = FairScheduler()
    return _scheduler_instance
