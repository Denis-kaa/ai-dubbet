"""
Tests for FairScheduler — Pro priority fairness (промт 115 §7).

Тестирует:
- Priority tiers (free=1, standard=5, pro=10)
- Anti-starvation: max 2 consecutive Pro before mandatory non-Pro turn
- should_preempt_for_priority()
- get_next_user() с priority-aware round-robin
"""

import pytest
from backend.services.scheduler import (
    FairScheduler,
    PRIORITY_FREE,
    PRIORITY_STANDARD,
    PRIORITY_PRO,
    MAX_CONSECUTIVE_PRO,
    DEFAULT_PRIORITY,
)


@pytest.fixture
def scheduler() -> FairScheduler:
    """Fresh scheduler with no Redis."""
    s = FairScheduler(redis_url="redis://localhost:1/never")
    s._redis = None
    return s


# ─── Priority tiers ─────────────────────────────────────────


class TestPriorityTiers:
    def test_default_priority_is_free(self, scheduler: FairScheduler):
        assert scheduler.get_user_priority("unknown_user") == PRIORITY_FREE

    def test_set_and_get_priority(self, scheduler: FairScheduler):
        scheduler.set_user_priority("user_1", PRIORITY_PRO)
        assert scheduler.get_user_priority("user_1") == PRIORITY_PRO

    def test_is_pro_user(self, scheduler: FairScheduler):
        scheduler.set_user_priority("pro_user", PRIORITY_PRO)
        scheduler.set_user_priority("free_user", PRIORITY_FREE)
        scheduler.set_user_priority("std_user", PRIORITY_STANDARD)
        assert scheduler._is_pro_user("pro_user") is True
        assert scheduler._is_pro_user("free_user") is False
        assert scheduler._is_pro_user("std_user") is False

    def test_priority_constants(self):
        assert PRIORITY_FREE < PRIORITY_STANDARD < PRIORITY_PRO


# ─── Anti-starvation ────────────────────────────────────────


class TestAntiStarvation:
    def test_pro_gets_priority_first(self, scheduler: FairScheduler):
        """Pro user should be selected before free users."""
        scheduler.register_active_job("free_1", "j1")
        scheduler.register_active_job("pro_1", "j2")
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)

        selected = [scheduler.get_next_user() for _ in range(6)]
        # Pro should appear more often in first selections
        pro_count = selected[:3].count("pro_1")
        assert pro_count >= 1  # at least 1 of first 3 is pro

    def test_max_consecutive_pro(self, scheduler: FairScheduler):
        """After MAX_CONSECUTIVE_PRO consecutive Pro, non-Pro MUST get a turn."""
        scheduler.register_active_job("free_1", "j1")
        scheduler.register_active_job("pro_1", "j2")
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)

        # Run many selections
        selected = []
        for _ in range(20):
            u = scheduler.get_next_user()
            selected.append(u)

        # Check: no more than MAX_CONSECUTIVE_PRO consecutive pro
        consecutive = 0
        max_seen = 0
        for u in selected:
            if u == "pro_1":
                consecutive += 1
                max_seen = max(max_seen, consecutive)
            else:
                consecutive = 0

        assert max_seen <= MAX_CONSECUTIVE_PRO

    def test_non_pro_always_gets_turn(self, scheduler: FairScheduler):
        """Non-Pro user must get at least one turn in every MAX_CONSECUTIVE_PRO+1 selections."""
        scheduler.register_active_job("free_1", "j1")
        scheduler.register_active_job("pro_1", "j2")
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)

        selected = []
        for _ in range(30):
            u = scheduler.get_next_user()
            selected.append(u)

        # In every window of (MAX_CONSECUTIVE_PRO+1), free_1 must appear
        window = MAX_CONSECUTIVE_PRO + 1
        for i in range(len(selected) - window + 1):
            chunk = selected[i:i + window]
            assert "free_1" in chunk, (
                f"No free_1 in window {i}..{i+window}: {chunk}"
            )

    def test_only_pro_users(self, scheduler: FairScheduler):
        """When all users are Pro, no anti-starvation needed."""
        scheduler.register_active_job("pro_1", "j1")
        scheduler.register_active_job("pro_2", "j2")
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)
        scheduler.set_user_priority("pro_2", PRIORITY_PRO)

        selected = [scheduler.get_next_user() for _ in range(6)]
        # Both Pro users should appear
        assert "pro_1" in selected
        assert "pro_2" in selected

    def test_only_free_users(self, scheduler: FairScheduler):
        """When all users are free, simple round-robin."""
        scheduler.register_active_job("free_1", "j1")
        scheduler.register_active_job("free_2", "j2")

        selected = [scheduler.get_next_user() for _ in range(6)]
        assert selected == ["free_1", "free_2", "free_1", "free_2", "free_1", "free_2"]


# ─── Mixed tiers ────────────────────────────────────────────


class TestMixedTiers:
    def test_three_tiers(self, scheduler: FairScheduler):
        """free + standard + pro: pro gets priority but all get turns."""
        scheduler.register_active_job("free_1", "j1")
        scheduler.register_active_job("std_1", "j2")
        scheduler.register_active_job("pro_1", "j3")
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)
        scheduler.set_user_priority("std_1", PRIORITY_STANDARD)

        selected = []
        for _ in range(30):
            u = scheduler.get_next_user()
            selected.append(u)

        # All three should appear
        assert "free_1" in selected
        assert "std_1" in selected
        assert "pro_1" in selected

        # Anti-starvation: at least one non-Pro in every window of MAX_CONSECUTIVE_PRO+1
        window = MAX_CONSECUTIVE_PRO + 1
        non_pro_users = {"free_1", "std_1"}
        for i in range(len(selected) - window + 1):
            chunk = selected[i:i + window]
            assert any(u in non_pro_users for u in chunk), f"No non-Pro at position {i}: {chunk}"

    def pro_appears_more_often(self, scheduler: FairScheduler):
        """Pro user should appear more often than free in first N selections."""
        scheduler.register_active_job("free_1", "j1")
        scheduler.register_active_job("pro_1", "j2")
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)

        selected = [scheduler.get_next_user() for _ in range(10)]
        pro_count = selected.count("pro_1")
        free_count = selected.count("free_1")
        # Pro should appear at least as often as free
        assert pro_count >= free_count


# ─── should_preempt_for_priority ────────────────────────────


class TestShouldPreempt:
    def test_non_pro_never_preempts(self, scheduler: FairScheduler):
        scheduler.set_user_priority("free_1", PRIORITY_FREE)
        assert scheduler.should_preempt_for_priority("free_1") is False

    def test_standard_never_preempts(self, scheduler: FairScheduler):
        scheduler.set_user_priority("std_1", PRIORITY_STANDARD)
        assert scheduler.should_preempt_for_priority("std_1") is False

    def test_pro_preempts_when_under_limit(self, scheduler: FairScheduler):
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)
        scheduler.register_active_job("free_1", "j1")
        # consecutive_pro_count = 0 < MAX_CONSECUTIVE_PRO
        assert scheduler.should_preempt_for_priority("pro_1") is True

    def test_pro_no_preempt_at_limit(self, scheduler: FairScheduler):
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)
        scheduler._consecutive_pro_count = MAX_CONSECUTIVE_PRO
        scheduler.register_active_job("free_1", "j1")
        # At limit, non-Pro exists → no preempt
        assert scheduler.should_preempt_for_priority("pro_1") is False

    def test_pro_preempts_at_limit_if_all_pro(self, scheduler: FairScheduler):
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)
        scheduler.set_user_priority("pro_2", PRIORITY_PRO)
        scheduler._consecutive_pro_count = MAX_CONSECUTIVE_PRO
        scheduler.register_active_job("pro_1", "j1")
        scheduler.register_active_job("pro_2", "j2")
        # All Pro → preempt allowed even at limit
        assert scheduler.should_preempt_for_priority("pro_1") is True


# ─── Stats ──────────────────────────────────────────────────


class TestPriorityStats:
    def test_stats_include_priorities(self, scheduler: FairScheduler):
        scheduler.set_user_priority("pro_1", PRIORITY_PRO)
        scheduler.set_user_priority("free_1", PRIORITY_FREE)
        scheduler.register_active_job("pro_1", "j1")
        scheduler.register_active_job("free_1", "j2")

        stats = scheduler.get_stats()
        assert stats.user_priorities["pro_1"] == PRIORITY_PRO
        assert stats.user_priorities["free_1"] == PRIORITY_FREE

    def test_stats_include_consecutive_pro(self, scheduler: FairScheduler):
        scheduler._consecutive_pro_count = 2
        stats = scheduler.get_stats()
        assert stats.consecutive_pro_count == 2
