"""
Sliding Window — управление окном обработки chunks.

Архитектура (промт 115 §2):
  Все chunks → Sliding Window → Processing → Ready

Окно определяет сколько chunks обрабатываются параллельно.
После завершения окно сдвигается вперёд.

Пример:
  CURRENT WINDOW (size=3):
  ┌─────────────────────┐
  │ Chunk 1 → READY     │
  │ Chunk 2 → PROCESSING│
  │ Chunk 3 → PROCESSING│
  └─────────────────────┘
            ↓
  После продвижения:
  ┌─────────────────────┐
  │ Chunk 2 → READY     │
  │ Chunk 3 → READY     │
  │ Chunk 4 → PROCESSING│
  └─────────────────────┘

Использование:
    from backend.services.sliding_window import ChunkWindow
    window = ChunkWindow(job_id="job_123", window_size=3)
    chunks_to_process = window.get_next_window(chunks)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class ChunkStatus(str, Enum):
    """Статус обработки chunk."""
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class ChunkInfo:
    """Информация о chunk."""
    chunk_id: str
    index: int
    status: ChunkStatus = ChunkStatus.QUEUED
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None


@dataclass
class WindowState:
    """Состояние sliding window."""
    job_id: str
    window_size: int = 3
    chunks: Dict[str, ChunkInfo] = field(default_factory=dict)
    current_position: int = 0  # индекс первого chunk в окне

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def ready_count(self) -> int:
        return sum(1 for c in self.chunks.values() if c.status == ChunkStatus.READY)

    @property
    def processing_count(self) -> int:
        return sum(1 for c in self.chunks.values() if c.status == ChunkStatus.PROCESSING)

    @property
    def window_end(self) -> int:
        return min(self.current_position + self.window_size, self.total_chunks)


class ChunkWindow:
    """Управление sliding window для chunks.

    Гарантирует:
    - Не более window_size chunks обрабатываются параллельно
    - Порядок chunks сохраняется
    - Progressive playback (первый chunk готов раньше остальных)
    """

    def __init__(self, job_id: str, window_size: int = 3) -> None:
        self._job_id = job_id
        self._window_size = window_size
        self._state = WindowState(job_id=job_id, window_size=window_size)

    def init_chunks(self, chunk_ids: List[str]) -> None:
        """Инициализировать chunks для job."""
        for i, chunk_id in enumerate(chunk_ids):
            self._state.chunks[chunk_id] = ChunkInfo(
                chunk_id=chunk_id,
                index=i,
            )

    def get_next_window(self) -> List[str]:
        """Вернуть IDs chunks которые должны обрабатываться сейчас.

        Возвращает chunks в текущем окне со статусом QUEUED.
        """
        result = []
        for chunk_id, info in sorted(
            self._state.chunks.items(), key=lambda x: x[1].index
        ):
            if info.index < self._state.current_position:
                continue
            if info.index >= self._state.window_end:
                break
            if info.status in (ChunkStatus.QUEUED, ChunkStatus.FAILED):
                result.append(chunk_id)
        return result

    def start_chunk(self, chunk_id: str) -> None:
        """Пометить chunk как обрабатываемый."""
        if chunk_id in self._state.chunks:
            self._state.chunks[chunk_id].status = ChunkStatus.PROCESSING
            self._state.chunks[chunk_id].started_at = __import__("time").time()

    def complete_chunk(self, chunk_id: str) -> None:
        """Пометить chunk как готовый и сдвинуть окно."""
        if chunk_id in self._state.chunks:
            self._state.chunks[chunk_id].status = ChunkStatus.READY
            self._state.chunks[chunk_id].completed_at = __import__("time").time()

        # Сдвигаем окно если первый chunk в окне готов
        self._advance_window()

    def fail_chunk(self, chunk_id: str, error: str = "") -> None:
        """Пометить chunk как_failed."""
        if chunk_id in self._state.chunks:
            self._state.chunks[chunk_id].status = ChunkStatus.FAILED
            self._state.chunks[chunk_id].error = error

    def publish_chunk(self, chunk_id: str) -> None:
        """Пометить chunk как опубликованный."""
        if chunk_id in self._state.chunks:
            self._state.chunks[chunk_id].status = ChunkStatus.PUBLISHED

    def get_buffer_status(self) -> Dict[str, int]:
        """Статус буфера: сколько chunks в каждом статусе."""
        return {
            "queued": sum(1 for c in self._state.chunks.values() if c.status == ChunkStatus.QUEUED),
            "processing": sum(1 for c in self._state.chunks.values() if c.status == ChunkStatus.PROCESSING),
            "ready": sum(1 for c in self._state.chunks.values() if c.status == ChunkStatus.READY),
            "published": sum(1 for c in self._state.chunks.values() if c.status == ChunkStatus.PUBLISHED),
            "failed": sum(1 for c in self._state.chunks.values() if c.status == ChunkStatus.FAILED),
            "total": self._state.total_chunks,
            "window_position": self._state.current_position,
            "window_size": self._state.window_size,
        }

    def get_ready_chunks(self) -> List[str]:
        """Вернуть IDs готовых chunks (для progressive playback)."""
        return [
            chunk_id
            for chunk_id, info in sorted(
                self._state.chunks.items(), key=lambda x: x[1].index
            )
            if info.status == ChunkStatus.READY
        ]

    def is_complete(self) -> bool:
        """Проверить, завершена ли обработка всех chunks."""
        return all(
            c.status in (ChunkStatus.READY, ChunkStatus.PUBLISHED)
            for c in self._state.chunks.values()
        )

    # ─── Private ──────────────────────────────────────────────

    def _advance_window(self) -> None:
        """Сдвинуть окно вперёд если первый chunk готов."""
        while (
            self._state.current_position < self._state.total_chunks
            and self._state.chunks.get(self._chunk_at_position(self._state.current_position))
            and self._state.chunks[self._chunk_at_position(self._state.current_position)].status
            in (ChunkStatus.READY, ChunkStatus.PUBLISHED)
        ):
            self._state.current_position += 1

    def _chunk_at_position(self, position: int) -> Optional[str]:
        """Найти chunk_id по позиции."""
        for chunk_id, info in self._state.chunks.items():
            if info.index == position:
                return chunk_id
        return None
