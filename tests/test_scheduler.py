"""
Tests for backend.services.scheduler — FairScheduler (local fallback).

All tests run WITHOUT Redis — using in-memory local state only.
"""

import pytest
from unittest.mock import patch, MagicMock
from backend.services.scheduler import (
    FairScheduler,
    SchedulerStats,
    MAX_CONCURRENT_JOBS_PER_USER,
    MAX_TOTAL_TTS_WORKERS,
    MAX_TOTAL_MEDIA_WORKERS,
    MAX_TOTAL_JOBS,
    MAX_TTS_TASKS_PER_USER,
    MAX_MEDIA_TASKS_PER_USER,
)


@pytest.fixture
def scheduler() -> FairScheduler:
    """Create a fresh scheduler instance (no Redis)."""
    s = FairScheduler(redis_url="redis://localhost:1/never-connect")
    # Force local-only mode by setting _redis to a broken mock
    s._redis = MagicMock()
    s._redis.ping.side_effect = ConnectionError("no redis")
    s._redis = None  # _get_redis will fail and return None
    return s


# ─── can_accept_job ──────────────────────────────────────────


class TestCanAcceptJob:
    def test_empty_user_can_accept(self, scheduler: FairScheduler):
        assert scheduler.can_accept_job("user_1") is True

    def test_user_below_limit_can_accept(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        assert scheduler.can_accept_job("user_1") is True

    def test_user_at_limit_cannot_accept(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        scheduler.register_active_job("user_1", "job_b")
        assert scheduler.can_accept_job("user_1") is False

    def test_different_users_independent(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        scheduler.register_active_job("user_1", "job_b")
        assert scheduler.can_accept_job("user_1") is False
        assert scheduler.can_accept_job("user_2") is True

    def test_global_limit(self, scheduler: FairScheduler):
        # Fill global limit with different users
        for i in range(MAX_TOTAL_JOBS):
            scheduler.register_active_job(f"user_{i}", f"job_{i}")
        assert scheduler.can_accept_job("new_user") is False

    def test_after_release_can_accept_again(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        scheduler.register_active_job("user_1", "job_b")
        assert scheduler.can_accept_job("user_1") is False
        scheduler.release_job("user_1", "job_a")
        assert scheduler.can_accept_job("user_1") is True


# ─── can_accept_tts / can_accept_media ──────────────────────


class TestCanAcceptTTS:
    def test_empty_can_accept(self, scheduler: FairScheduler):
        assert scheduler.can_accept_tts("user_1") is True

    def test_user_at_tts_limit(self, scheduler: FairScheduler):
        scheduler.register_tts_task("user_1", "job_a", "c0")
        scheduler.register_tts_task("user_1", "job_a", "c1")
        assert scheduler.can_accept_tts("user_1") is False

    def test_global_tts_limit(self, scheduler: FairScheduler):
        for i in range(MAX_TOTAL_TTS_WORKERS):
            scheduler.register_tts_task(f"user_{i}", f"job_{i}", f"c{i}")
        assert scheduler.can_accept_tts("new_user") is False


class TestCanAcceptMedia:
    def test_empty_can_accept(self, scheduler: FairScheduler):
        assert scheduler.can_accept_media("user_1") is True

    def test_user_at_media_limit(self, scheduler: FairScheduler):
        scheduler.register_media_task("user_1", "job_a", "c0")
        assert scheduler.can_accept_media("user_1") is False

    def test_global_media_limit(self, scheduler: FairScheduler):
        for i in range(MAX_TOTAL_MEDIA_WORKERS):
            scheduler.register_media_task(f"user_{i}", f"job_{i}", f"c{i}")
        assert scheduler.can_accept_media("new_user") is False


# ─── register / release ─────────────────────────────────────


class TestRegisterRelease:
    def test_register_increments_count(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        stats = scheduler.get_stats()
        assert stats.active_jobs["user_1"] == 1
        assert stats.total_active == 1

    def test_register_same_job_twice(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        scheduler.register_active_job("user_1", "job_a")  # duplicate
        stats = scheduler.get_stats()
        assert stats.active_jobs["user_1"] == 1  # set dedup
        assert stats.total_active == 1

    def test_release_removes_job(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        scheduler.register_active_job("user_1", "job_b")
        scheduler.release_job("user_1", "job_a")
        stats = scheduler.get_stats()
        assert stats.active_jobs["user_1"] == 1
        assert stats.total_active == 1

    def test_release_all_removes_user(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        scheduler.release_job("user_1", "job_a")
        stats = scheduler.get_stats()
        assert "user_1" not in stats.active_jobs
        assert stats.total_active == 0

    def test_release_nonexistent_is_safe(self, scheduler: FairScheduler):
        scheduler.release_job("user_1", "job_nonexistent")  # no crash

    def test_tts_register_release(self, scheduler: FairScheduler):
        scheduler.register_tts_task("user_1", "job_a", "c0")
        scheduler.register_tts_task("user_1", "job_a", "c1")
        stats = scheduler.get_stats()
        assert stats.active_tts["user_1"] == 2
        scheduler.release_tts_task("user_1", "job_a", "c0")
        stats = scheduler.get_stats()
        assert stats.active_tts["user_1"] == 1

    def test_media_register_release(self, scheduler: FairScheduler):
        scheduler.register_media_task("user_1", "job_a", "c0")
        stats = scheduler.get_stats()
        assert stats.active_media["user_1"] == 1
        scheduler.release_media_task("user_1", "job_a", "c0")
        stats = scheduler.get_stats()
        assert stats.active_media["user_1"] == 0


# ─── Round-robin ────────────────────────────────────────────


class TestRoundRobin:
    def test_no_users_returns_none(self, scheduler: FairScheduler):
        assert scheduler.get_next_user() is None

    def test_single_user_returns_that_user(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        assert scheduler.get_next_user() == "user_1"

    def test_round_robin_cycles(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_a", "job_1")
        scheduler.register_active_job("user_b", "job_2")
        scheduler.register_active_job("user_c", "job_3")

        results = [scheduler.get_next_user() for _ in range(6)]
        # Should cycle: a, b, c, a, b, c
        assert results == ["user_a", "user_b", "user_c", "user_a", "user_b", "user_c"]

    def test_user_removed_from_round_robin(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_a", "job_1")
        scheduler.register_active_job("user_b", "job_2")
        scheduler.release_job("user_a", "job_1")
        # Only user_b remains
        results = [scheduler.get_next_user() for _ in range(3)]
        assert all(r == "user_b" for r in results)


# ─── Stats ──────────────────────────────────────────────────


class TestStats:
    def test_empty_stats(self, scheduler: FairScheduler):
        stats = scheduler.get_stats()
        assert stats.total_active == 0
        assert stats.total_active_tts == 0
        assert stats.total_active_media == 0
        assert stats.active_jobs == {}

    def test_stats_after_operations(self, scheduler: FairScheduler):
        scheduler.register_active_job("user_1", "job_a")
        scheduler.register_active_job("user_2", "job_b")
        scheduler.register_tts_task("user_1", "job_a", "c0")
        scheduler.register_media_task("user_2", "job_b", "c0")

        stats = scheduler.get_stats()
        assert stats.total_active == 2
        assert stats.active_jobs["user_1"] == 1
        assert stats.active_jobs["user_2"] == 1
        assert stats.active_tts["user_1"] == 1
        assert stats.active_media["user_2"] == 1
