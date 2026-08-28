"""
Metrics — Time To First Playable (TTFP) и latency distribution.

Архитектура (промт 115 §12-13):
  Измеряем для каждого user/job:
  - Time To First Playable (TTFP)
  - Total Processing Time
  - Queue Wait Time
  - TTS Latency
  - Media Latency

  Также P50/P90/P95/P99 для каждого показателя.

Использование:
    from backend.services.metrics import MetricsCollector
    m = MetricsCollector()
    m.start_job(user_id, job_id)
    m.record_ttfp(job_id, chunk_id)  # первый готовый chunk
    m.end_job(job_id)
    report = m.get_report()
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class JobMetrics:
    """Метрики одного job."""
    user_id: str
    job_id: str
    started_at: float = 0.0
    ended_at: float = 0.0
    ttfp: float = 0.0  # Time To First Playable (секунды)
    total_processing: float = 0.0
    queue_wait: float = 0.0
    tts_latencies: List[float] = field(default_factory=list)
    media_latencies: List[float] = field(default_factory=list)
    chunks_total: int = 0
    chunks_completed: int = 0
    chunks_failed: int = 0
    first_chunk_id: Optional[str] = None


@dataclass
class PercentileReport:
    """Отчёт по процентилям."""
    p50: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    avg: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    count: int = 0


class MetricsCollector:
    """Сборщик метрик TTFP и latency."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobMetrics] = {}
        self._ttfp_values: List[float] = []
        self._total_times: List[float] = []
        self._tts_latencies: List[float] = []
        self._media_latencies: List[float] = []
        self._queue_waits: List[float] = []

    def start_job(self, user_id: str, job_id: str) -> None:
        """Начать отслеживание job."""
        self._jobs[job_id] = JobMetrics(
            user_id=user_id,
            job_id=job_id,
            started_at=time.time(),
        )

    def record_ttfp(self, job_id: str, chunk_id: str) -> None:
        """Записать Time To First Playable.

        Вызывается когда ПЕРВЫЙ chunk становится READY.
        """
        if job_id not in self._jobs:
            return
        job = self._jobs[job_id]
        if job.ttfp == 0.0:  # только первый chunk
            job.ttfp = time.time() - job.started_at
            job.first_chunk_id = chunk_id
            self._ttfp_values.append(job.ttfp)

    def record_tts_latency(self, job_id: str, chunk_id: str, latency_sec: float) -> None:
        """Записать latency TTS для chunk."""
        if job_id in self._jobs:
            self._jobs[job_id].tts_latencies.append(latency_sec)
            self._tts_latencies.append(latency_sec)

    def record_media_latency(self, job_id: str, chunk_id: str, latency_sec: float) -> None:
        """Записать latency Media для chunk."""
        if job_id in self._jobs:
            self._jobs[job_id].media_latencies.append(latency_sec)
            self._media_latencies.append(latency_sec)

    def record_queue_wait(self, job_id: str, wait_sec: float) -> None:
        """Записать время ожидания в очереди."""
        if job_id in self._jobs:
            self._jobs[job_id].queue_wait = wait_sec
            self._queue_waits.append(wait_sec)

    def record_chunk_completed(self, job_id: str) -> None:
        """Записать завершение chunk."""
        if job_id in self._jobs:
            self._jobs[job_id].chunks_completed += 1

    def record_chunk_failed(self, job_id: str) -> None:
        """Записать ошибку chunk."""
        if job_id in self._jobs:
            self._jobs[job_id].chunks_failed += 1

    def set_chunks_total(self, job_id: str, total: int) -> None:
        """Установить общее количество chunks."""
        if job_id in self._jobs:
            self._jobs[job_id].chunks_total = total

    def end_job(self, job_id: str) -> None:
        """Завершить отслеживание job."""
        if job_id not in self._jobs:
            return
        job = self._jobs[job_id]
        job.ended_at = time.time()
        job.total_processing = job.ended_at - job.started_at
        self._total_times.append(job.total_processing)

    def get_job_metrics(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Получить метрики конкретного job."""
        if job_id not in self._jobs:
            return None
        job = self._jobs[job_id]
        return {
            "user_id": job.user_id,
            "job_id": job.job_id,
            "ttfp": round(job.ttfp, 2),
            "total_processing": round(job.total_processing, 2),
            "queue_wait": round(job.queue_wait, 2),
            "chunks_total": job.chunks_total,
            "chunks_completed": job.chunks_completed,
            "chunks_failed": job.chunks_failed,
            "first_chunk_id": job.first_chunk_id,
            "avg_tts_latency": round(
                sum(job.tts_latencies) / len(job.tts_latencies), 3
            ) if job.tts_latencies else 0.0,
            "avg_media_latency": round(
                sum(job.media_latencies) / len(job.media_latencies), 3
            ) if job.media_latencies else 0.0,
        }

    def get_report(self) -> Dict[str, Any]:
        """Полный отчёт по метрикам."""
        return {
            "summary": {
                "total_jobs": len(self._jobs),
                "ttfp": self._percentile_report(self._ttfp_values),
                "total_processing": self._percentile_report(self._total_times),
                "queue_wait": self._percentile_report(self._queue_waits),
                "tts_latency": self._percentile_report(self._tts_latencies),
                "media_latency": self._percentile_report(self._media_latencies),
            },
            "per_user": self._per_user_stats(),
            "active_jobs": [
                self.get_job_metrics(jid)
                for jid, job in self._jobs.items()
                if job.ended_at == 0.0
            ],
        }

    # ─── Private ──────────────────────────────────────────────

    def _percentile_report(self, values: List[float]) -> Dict[str, Any]:
        """Рассчитать процентили для списка значений."""
        if not values:
            return {"p50": 0, "p90": 0, "p95": 0, "p99": 0, "avg": 0, "min": 0, "max": 0, "count": 0}

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        return {
            "p50": round(self._percentile(sorted_vals, 50), 2),
            "p90": round(self._percentile(sorted_vals, 90), 2),
            "p95": round(self._percentile(sorted_vals, 95), 2),
            "p99": round(self._percentile(sorted_vals, 99), 2),
            "avg": round(sum(sorted_vals) / n, 2),
            "min": round(sorted_vals[0], 2),
            "max": round(sorted_vals[-1], 2),
            "count": n,
        }

    @staticmethod
    def _percentile(sorted_vals: List[float], percentile: int) -> float:
        """Рассчитать percentile."""
        if not sorted_vals:
            return 0.0
        k = (len(sorted_vals) - 1) * (percentile / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        d = k - f
        return sorted_vals[f] + d * (sorted_vals[c] - sorted_vals[f])

    def _per_user_stats(self) -> Dict[str, Dict[str, Any]]:
        """Статистика по пользователям."""
        user_jobs: Dict[str, List[JobMetrics]] = defaultdict(list)
        for job in self._jobs.values():
            user_jobs[job.user_id].append(job)

        result = {}
        for user_id, jobs in user_jobs.items():
            completed = [j for j in jobs if j.ended_at > 0]
            ttfps = [j.ttfp for j in completed if j.ttfp > 0]
            result[user_id] = {
                "total_jobs": len(jobs),
                "completed_jobs": len(completed),
                "avg_ttfp": round(sum(ttfps) / len(ttfps), 2) if ttfps else 0,
                "avg_total": round(
                    sum(j.total_processing for j in completed) / len(completed), 2
                ) if completed else 0,
            }
        return result


# ─── Singleton ────────────────────────────────────────────────

_metrics_instance: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Возвращает singleton MetricsCollector."""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance
