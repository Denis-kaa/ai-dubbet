"""
Pipeline Profiling — har bir bosqichning vaqtini, CPU, RAM, disk I/O ni o'lchash.

Usage:
    from backend.services.profiling import PipelineProfiler

    profiler = PipelineProfiler(job_id="abc123")

    with profiler.stage("DOWNLOAD"):
        result = downloader.download_video(url, job_id)

    with profiler.stage("TRANSCRIBE"):
        result = transcriber.transcribe_audio(audio_path)

    # Natija
    print(profiler.summary())
    profiler.save("/path/to/report.json")
"""

import os
import time
import json
import psutil
import logging
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class StageTiming:
    """Bir bosqichning timing ma'lumotlari."""
    name: str
    start_time: float
    end_time: float
    duration_sec: float
    cpu_percent: float
    memory_mb: float
    memory_delta_mb: float
    disk_read_mb: float
    disk_write_mb: float
    success: bool = True
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


@dataclass
class PipelineReport:
    """To'liq pipeline hisoboti."""
    job_id: str
    start_time: str
    end_time: str
    total_duration_sec: float
    stages: list[StageTiming] = field(default_factory=list)
    video_duration_sec: float = 0
    throughput: float = 0  # video_duration / total_time
    peak_memory_mb: float = 0
    avg_cpu_percent: float = 0
    details: dict = field(default_factory=dict)


class PipelineProfiler:
    """
    Pipeline profiling — har bir bosqichning resurs ishlatishini o'lchash.

    Features:
    - Har bir bosqich uchun duration, CPU, RAM, disk I/O
    - Context manager for easy usage
    - JSON export
    - Console summary
    """

    def __init__(self, job_id: str = ""):
        self.job_id = job_id
        self.stages: list[StageTiming] = []
        self._process = psutil.Process(os.getpid())
        self._start_time = time.monotonic()
        self._start_datetime = datetime.now().isoformat()
        self._start_cpu = self._process.cpu_percent()
        self._start_memory = self._process.memory_info().rss / (1024 * 1024)
        self._start_disk = self._get_disk_io()

    def _get_disk_io(self) -> tuple[float, float]:
        """Disk I/O (read/write MB)."""
        try:
            io = self._process.io_counters()
            return io.read_bytes / (1024 * 1024), io.write_bytes / (1024 * 1024)
        except (AttributeError, psutil.Error):
            return 0, 0

    @contextmanager
    def stage(self, name: str, **details):
        """
        Bosqichni profiling qilish.

        Usage:
            with profiler.stage("DOWNLOAD", url="youtube.com/watch?v=..."):
                result = download_video(url)
        """
        # Reset CPU percent (cheklash uchun)
        self._process.cpu_percent()

        start_time = time.monotonic()
        start_memory = self._process.memory_info().rss / (1024 * 1024)
        start_disk = self._get_disk_io()
        success = True
        error = None

        try:
            yield
        except Exception as exc:
            success = False
            error = str(exc)
            raise
        finally:
            end_time = time.monotonic()
            end_memory = self._process.memory_info().rss / (1024 * 1024)
            end_disk = self._get_disk_io()

            timing = StageTiming(
                name=name,
                start_time=start_time,
                end_time=end_time,
                duration_sec=round(end_time - start_time, 2),
                cpu_percent=round(self._process.cpu_percent(), 1),
                memory_mb=round(end_memory, 1),
                memory_delta_mb=round(end_memory - start_memory, 1),
                disk_read_mb=round(end_disk[0] - start_disk[0], 2),
                disk_write_mb=round(end_disk[1] - start_disk[1], 2),
                success=success,
                error=error,
                details=details,
            )
            self.stages.append(timing)

    def summary(self) -> str:
        """Inson o'qiydigan summary."""
        total = time.monotonic() - self._start_time
        end_memory = self._process.memory_info().rss / (1024 * 1024)

        lines = [
            f"\n{'='*70}",
            f"PIPELINE PROFILING REPORT",
            f"{'='*70}",
            f"Job ID: {self.job_id}",
            f"Started: {self._start_datetime}",
            f"Total time: {total:.1f}s",
            f"Peak memory: {max(s.memory_mb for s in self.stages) if self.stages else 0:.1f} MB",
            f"{'='*70}",
            f"\n{'Stage':<20} {'Time':>10} {'CPU%':>8} {'RAM Δ':>10} {'Disk R':>10} {'Disk W':>10} {'Status':>8}",
            f"{'-'*70}",
        ]

        for s in self.stages:
            status = "✅" if s.success else "❌"
            lines.append(
                f"{s.name:<20} "
                f"{s.duration_sec:>9.1f}s "
                f"{s.cpu_percent:>7.1f}% "
                f"{s.memory_delta_mb:>+9.1f}MB "
                f"{s.disk_read_mb:>9.2f}MB "
                f"{s.disk_write_mb:>9.2f}MB "
                f"{status:>8}"
            )

        lines.append(f"{'-'*70}")
        lines.append(f"{'TOTAL':<20} {total:>9.1f}s")
        lines.append(f"{'='*70}\n")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON serializable dict."""
        total = time.monotonic() - self._start_time
        return {
            "job_id": self.job_id,
            "start_time": self._start_datetime,
            "end_time": datetime.now().isoformat(),
            "total_duration_sec": round(total, 2),
            "stages": [asdict(s) for s in self.stages],
            "peak_memory_mb": max((s.memory_mb for s in self.stages), default=0),
            "avg_cpu_percent": (
                sum(s.cpu_percent for s in self.stages) / len(self.stages)
                if self.stages else 0
            ),
        }

    def save(self, path: str):
        """Hisobotni JSON faylga saqlash."""
        report = self.to_dict()
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Profiling report saved to: {path}")


class TTFTProfiler:
    """
    Time To First Playable (TTFF) profiling.

    YouTube URL → First playable chunk vaqtini o'lchash.
    """

    def __init__(self, job_id: str = ""):
        self.job_id = job_id
        self._start_time = time.monotonic()
        self._start_datetime = datetime.now().isoformat()
        self._milestones: list[dict] = []

    def milestone(self, name: str, **details):
        """Milestone qayd etish."""
        elapsed = time.monotonic() - self._start_time
        self._milestones.append({
            "name": name,
            "elapsed_sec": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
            **details,
        })
        logger.info(f"[TTFF] {name}: {elapsed:.1f}s elapsed")

    def first_playable_time(self) -> Optional[float]:
        """First playable chunk vaqtini qaytarish."""
        for m in self._milestones:
            if m["name"] == "FIRST_PLAYABLE":
                return m["elapsed_sec"]
        return None

    def summary(self) -> str:
        """TTFF summary."""
        ttff = self.first_playable_time()
        lines = [
            f"\n{'='*50}",
            f"TIME TO FIRST PLAYABLE (TTFF)",
            f"{'='*50}",
            f"Job: {self.job_id}",
        ]

        if ttff is not None:
            lines.append(f"TTFF: {ttff:.1f}s")
        else:
            lines.append("TTFF: Not yet reached")

        lines.append(f"\nMilestones:")
        for m in self._milestones:
            lines.append(f"  {m['elapsed_sec']:>7.1f}s  {m['name']}")

        lines.append(f"{'='*50}\n")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """JSON serializable dict."""
        return {
            "job_id": self.job_id,
            "start_time": self._start_datetime,
            "ttff_sec": self.first_playable_time(),
            "milestones": self._milestones,
        }
