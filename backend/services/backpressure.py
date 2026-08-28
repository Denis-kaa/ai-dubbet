"""
Backpressure — контроль потока между TTS и Media pipeline.

Архитектура (промт 115 §8):
  TTS → small buffer → Media → Publish

Если Media не успевает:
  TTS НЕ должен бесконтрольно генерировать новые chunks.

Buffer limits:
  TTS_MAX_PENDING = 6  (максимум TTS chunks в очереди Media)
  MEDIA_MAX_ACTIVE = 2 (максимум параллельных Media tasks)

Использование:
    from backend.services.backpressure import BackpressureController
    bp = BackpressureController()
    if bp.can_produce_tts(job_id):
        # запускаем TTS
        bp.register_tts_produced(job_id, chunk_id)
    # Media завершил
    bp.register_media_consumed(job_id, chunk_id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─── Buffer limits (промт 115 §8-9) ─────────────────────────
TTS_MAX_PENDING = 6      # максимум TTS chunks в очереди Media
MEDIA_MAX_ACTIVE = 2     # максимум параллельных Media tasks
BUFFER_HIGH_WATER = 4    # уровень "высокий" — начинаем замедлять TTS
BUFFER_LOW_WATER = 2     # уровень "низкий" — TTS снова на полной скорости


@dataclass
class BackpressureState:
    """Состояние backpressure для одного job."""
    tts_pending: int = 0      # TTS chunks в очереди Media
    media_active: int = 0     # активные Media tasks
    tts_total_produced: int = 0
    media_total_consumed: int = 0
    throttled: bool = False   # TTS замедлен из-за backpressure


@dataclass
class BackpressureStats:
    """Глобальная статистика backpressure."""
    per_job: Dict[str, BackpressureState] = field(default_factory=dict)
    global_tts_pending: int = 0
    global_media_active: int = 0
    jobs_throttled: int = 0


class BackpressureController:
    """Контроллер backpressure между TTS и Media."""

    def __init__(self) -> None:
        self._states: Dict[str, BackpressureState] = {}

    def can_produce_tts(self, job_id: str) -> bool:
        """Проверяет, может ли TTS производить новые chunks.

        Возвращает False если:
        - Media buffer заполнен (tts_pending >= TTS_MAX_PENDING)
        - Media перегружен (media_active >= MEDIA_MAX_ACTIVE)
        """
        state = self._get_state(job_id)

        # Проверяем buffer
        if state.tts_pending >= TTS_MAX_PENDING:
            state.throttled = True
            return False

        # Проверяем Media capacity
        if state.media_active >= MEDIA_MAX_ACTIVE:
            state.throttled = True
            return False

        state.throttled = False
        return True

    def is_throttled(self, job_id: str) -> bool:
        """Проверяет, замедлен ли TTS для job."""
        state = self._get_state(job_id)
        return state.throttled

    def get_backoff_seconds(self, job_id: str) -> float:
        """Возвращает время ожидания перед следующим TTS chunk.

        Чем ближе к лимиту — тем дольше ожидание.
        """
        state = self._get_state(job_id)
        if state.tts_pending >= TTS_MAX_PENDING:
            return 5.0  # максимальный backoff
        elif state.tts_pending >= BUFFER_HIGH_WATER:
            return 2.0  # средний backoff
        elif state.tts_pending >= BUFFER_LOW_WATER:
            return 0.5  # минимальный backoff
        return 0.0  # нет backoff

    def register_tts_produced(self, job_id: str, chunk_id: str) -> None:
        """Зарегистрировать произведённый TTS chunk."""
        state = self._get_state(job_id)
        state.tts_pending += 1
        state.tts_total_produced += 1

    def register_media_consumed(self, job_id: str, chunk_id: str) -> None:
        """Зарегистрировать обработанный Media chunk."""
        state = self._get_state(job_id)
        state.tts_pending = max(0, state.tts_pending - 1)
        state.media_total_consumed += 1

        # Снимаем throttle если buffer пустеет
        if state.tts_pending <= BUFFER_LOW_WATER:
            state.throttled = False

    def register_media_started(self, job_id: str, chunk_id: str) -> None:
        """Зарегистрировать начало Media обработки."""
        state = self._get_state(job_id)
        state.media_active += 1

    def register_media_finished(self, job_id: str, chunk_id: str) -> None:
        """Зарегистрировать завершение Media обработки."""
        state = self._get_state(job_id)
        state.media_active = max(0, state.media_active - 1)

        # Снимаем throttle если Media освободился
        if state.media_active < MEDIA_MAX_ACTIVE:
            state.throttled = False

    def get_stats(self) -> BackpressureStats:
        """Статистика backpressure."""
        stats = BackpressureStats()
        for job_id, state in self._states.items():
            stats.per_job[job_id] = state
            stats.global_tts_pending += state.tts_pending
            stats.global_media_active += state.media_active
            if state.throttled:
                stats.jobs_throttled += 1
        return stats

    def cleanup_job(self, job_id: str) -> None:
        """Очистить state завершённого job."""
        self._states.pop(job_id, None)

    # ─── Private ──────────────────────────────────────────────

    def _get_state(self, job_id: str) -> BackpressureState:
        """Получить или создать state для job."""
        if job_id not in self._states:
            self._states[job_id] = BackpressureState()
        return self._states[job_id]


# ─── Singleton ────────────────────────────────────────────────

_backpressure_instance: Optional[BackpressureController] = None


def get_backpressure() -> BackpressureController:
    """Возвращает singleton BackpressureController."""
    global _backpressure_instance
    if _backpressure_instance is None:
        _backpressure_instance = BackpressureController()
    return _backpressure_instance
