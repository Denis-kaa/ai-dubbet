"""
Tests for backend.services.backpressure — BackpressureController.
"""

import pytest
from backend.services.backpressure import (
    BackpressureController,
    BackpressureStats,
    TTS_MAX_PENDING,
    MEDIA_MAX_ACTIVE,
    BUFFER_HIGH_WATER,
    BUFFER_LOW_WATER,
)


@pytest.fixture
def bp() -> BackpressureController:
    """Fresh backpressure controller."""
    return BackpressureController()


# ─── can_produce_tts ────────────────────────────────────────


class TestCanProduceTTS:
    def test_empty_can_produce(self, bp: BackpressureController):
        assert bp.can_produce_tts("job_1") is True

    def test_below_limit_can_produce(self, bp: BackpressureController):
        for i in range(TTS_MAX_PENDING - 1):
            bp.register_tts_produced("job_1", f"c{i}")
        assert bp.can_produce_tts("job_1") is True

    def test_at_limit_cannot_produce(self, bp: BackpressureController):
        for i in range(TTS_MAX_PENDING):
            bp.register_tts_produced("job_1", f"c{i}")
        assert bp.can_produce_tts("job_1") is False

    def test_media_overloaded_cannot_produce(self, bp: BackpressureController):
        for i in range(MEDIA_MAX_ACTIVE):
            bp.register_media_started("job_1", f"c{i}")
        assert bp.can_produce_tts("job_1") is False

    def test_after_media_finished_can_produce_again(self, bp: BackpressureController):
        for i in range(MEDIA_MAX_ACTIVE):
            bp.register_media_started("job_1", f"c{i}")
        assert bp.can_produce_tts("job_1") is False
        bp.register_media_finished("job_1", "c0")
        assert bp.can_produce_tts("job_1") is True

    def test_independent_jobs(self, bp: BackpressureController):
        for i in range(TTS_MAX_PENDING):
            bp.register_tts_produced("job_1", f"c{i}")
        assert bp.can_produce_tts("job_1") is False
        assert bp.can_produce_tts("job_2") is True


# ─── is_throttled ───────────────────────────────────────────


class TestIsThrottled:
    def test_not_throttled_initially(self, bp: BackpressureController):
        assert bp.is_throttled("job_1") is False

    def test_throttled_at_limit(self, bp: BackpressureController):
        for i in range(TTS_MAX_PENDING):
            bp.register_tts_produced("job_1", f"c{i}")
        bp.can_produce_tts("job_1")  # triggers throttle
        assert bp.is_throttled("job_1") is True

    def test_unthrottled_after_consume(self, bp: BackpressureController):
        for i in range(TTS_MAX_PENDING):
            bp.register_tts_produced("job_1", f"c{i}")
        bp.can_produce_tts("job_1")
        assert bp.is_throttled("job_1") is True

        # Consume enough to go below LOW_WATER
        for i in range(TTS_MAX_PENDING - BUFFER_LOW_WATER + 1):
            bp.register_media_consumed("job_1", f"c{i}")
        assert bp.is_throttled("job_1") is False


# ─── get_backoff_seconds ────────────────────────────────────


class TestGetBackoff:
    def test_no_backoff_when_empty(self, bp: BackpressureController):
        assert bp.get_backoff_seconds("job_1") == 0.0

    def test_min_backoff_at_low_water(self, bp: BackpressureController):
        for i in range(BUFFER_LOW_WATER):
            bp.register_tts_produced("job_1", f"c{i}")
        assert bp.get_backoff_seconds("job_1") == 0.5

    def test_med_backoff_at_high_water(self, bp: BackpressureController):
        for i in range(BUFFER_HIGH_WATER):
            bp.register_tts_produced("job_1", f"c{i}")
        assert bp.get_backoff_seconds("job_1") == 2.0

    def test_max_backoff_at_limit(self, bp: BackpressureController):
        for i in range(TTS_MAX_PENDING):
            bp.register_tts_produced("job_1", f"c{i}")
        assert bp.get_backoff_seconds("job_1") == 5.0


# ─── register lifecycle ─────────────────────────────────────


class TestRegisterLifecycle:
    def test_tts_produced_increments_pending(self, bp: BackpressureController):
        bp.register_tts_produced("job_1", "c0")
        stats = bp.get_stats()
        assert stats.global_tts_pending == 1

    def test_media_consumed_decrements_pending(self, bp: BackpressureController):
        bp.register_tts_produced("job_1", "c0")
        bp.register_tts_produced("job_1", "c1")
        bp.register_media_consumed("job_1", "c0")
        stats = bp.get_stats()
        assert stats.global_tts_pending == 1

    def test_media_started_increments_active(self, bp: BackpressureController):
        bp.register_media_started("job_1", "c0")
        stats = bp.get_stats()
        assert stats.global_media_active == 1

    def test_media_finished_decrements_active(self, bp: BackpressureController):
        bp.register_media_started("job_1", "c0")
        bp.register_media_started("job_1", "c1")
        bp.register_media_finished("job_1", "c0")
        stats = bp.get_stats()
        assert stats.global_media_active == 1

    def test_full_lifecycle(self, bp: BackpressureController):
        """TTS produced → Media started → Media consumed → Media finished."""
        bp.register_tts_produced("job_1", "c0")
        assert bp.can_produce_tts("job_1") is True

        bp.register_media_started("job_1", "c0")
        bp.register_media_consumed("job_1", "c0")
        bp.register_media_finished("job_1", "c0")

        stats = bp.get_stats()
        assert stats.global_tts_pending == 0
        assert stats.global_media_active == 0

    def test_pending_never_negative(self, bp: BackpressureController):
        bp.register_media_consumed("job_1", "c0")  # consume without produce
        stats = bp.get_stats()
        assert stats.global_tts_pending == 0

    def test_media_active_never_negative(self, bp: BackpressureController):
        bp.register_media_finished("job_1", "c0")  # finish without start
        stats = bp.get_stats()
        assert stats.global_media_active == 0


# ─── get_stats ──────────────────────────────────────────────


class TestStats:
    def test_empty_stats(self, bp: BackpressureController):
        stats = bp.get_stats()
        assert stats.global_tts_pending == 0
        assert stats.global_media_active == 0
        assert stats.jobs_throttled == 0
        assert stats.per_job == {}

    def test_stats_per_job(self, bp: BackpressureController):
        bp.register_tts_produced("job_1", "c0")
        bp.register_media_started("job_1", "c0")
        bp.register_tts_produced("job_2", "c0")

        stats = bp.get_stats()
        assert stats.global_tts_pending == 2
        assert stats.global_media_active == 1
        assert "job_1" in stats.per_job
        assert "job_2" in stats.per_job

    def test_throttled_jobs_counted(self, bp: BackpressureController):
        for i in range(TTS_MAX_PENDING):
            bp.register_tts_produced("job_1", f"c{i}")
        bp.can_produce_tts("job_1")  # triggers throttle

        stats = bp.get_stats()
        assert stats.jobs_throttled == 1


# ─── cleanup_job ────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_removes_job_state(self, bp: BackpressureController):
        bp.register_tts_produced("job_1", "c0")
        bp.register_media_started("job_1", "c0")
        bp.cleanup_job("job_1")
        stats = bp.get_stats()
        assert "job_1" not in stats.per_job
        assert stats.global_tts_pending == 0
        assert stats.global_media_active == 0

    def test_cleanup_nonexistent_is_safe(self, bp: BackpressureController):
        bp.cleanup_job("nonexistent")  # no exception

    def test_cleanup_does_not_affect_other_jobs(self, bp: BackpressureController):
        bp.register_tts_produced("job_1", "c0")
        bp.register_tts_produced("job_2", "c0")
        bp.cleanup_job("job_1")
        stats = bp.get_stats()
        assert "job_2" in stats.per_job
        assert stats.global_tts_pending == 1
