"""
Tests for backend.services.sliding_window — ChunkWindow.
"""

import pytest
from backend.services.sliding_window import ChunkWindow, ChunkStatus


@pytest.fixture
def window_3() -> ChunkWindow:
    """Window with size=3 and 6 chunks."""
    w = ChunkWindow(job_id="job_test", window_size=3)
    w.init_chunks(["c0", "c1", "c2", "c3", "c4", "c5"])
    return w


@pytest.fixture
def window_2() -> ChunkWindow:
    """Window with size=2 and 4 chunks."""
    w = ChunkWindow(job_id="job_test2", window_size=2)
    w.init_chunks(["c0", "c1", "c2", "c3"])
    return w


# ─── init_chunks ────────────────────────────────────────────


class TestInitChunks:
    def test_initial_status_queued(self, window_3: ChunkWindow):
        status = window_3.get_buffer_status()
        assert status["queued"] == 6
        assert status["processing"] == 0
        assert status["ready"] == 0
        assert status["total"] == 6

    def test_initial_position_zero(self, window_3: ChunkWindow):
        status = window_3.get_buffer_status()
        assert status["window_position"] == 0


# ─── get_next_window ────────────────────────────────────────


class TestGetNextWindow:
    def test_first_window_returns_first_n_chunks(self, window_3: ChunkWindow):
        next_chunks = window_3.get_next_window()
        assert len(next_chunks) == 3
        assert set(next_chunks) == {"c0", "c1", "c2"}

    def test_smaller_window(self, window_2: ChunkWindow):
        next_chunks = window_2.get_next_window()
        assert len(next_chunks) == 2
        assert set(next_chunks) == {"c0", "c1"}

    def test_after_starting_chunks_not_returned_again(self, window_3: ChunkWindow):
        window_3.start_chunk("c0")
        window_3.start_chunk("c1")
        next_chunks = window_3.get_next_window()
        assert "c0" not in next_chunks
        assert "c1" not in next_chunks
        assert "c2" in next_chunks

    def test_empty_after_all_processing(self, window_3: ChunkWindow):
        for cid in ["c0", "c1", "c2"]:
            window_3.start_chunk(cid)
        next_chunks = window_3.get_next_window()
        assert len(next_chunks) == 0


# ─── start_chunk / complete_chunk ───────────────────────────


class TestChunkTransitions:
    def test_start_sets_processing(self, window_3: ChunkWindow):
        window_3.start_chunk("c0")
        status = window_3.get_buffer_status()
        assert status["processing"] == 1
        assert status["queued"] == 5

    def test_complete_sets_ready(self, window_3: ChunkWindow):
        window_3.start_chunk("c0")
        window_3.complete_chunk("c0")
        status = window_3.get_buffer_status()
        assert status["ready"] == 1
        assert status["processing"] == 0

    def test_complete_unknown_chunk_no_crash(self, window_3: ChunkWindow):
        window_3.complete_chunk("nonexistent")  # no exception

    def test_start_unknown_chunk_no_crash(self, window_3: ChunkWindow):
        window_3.start_chunk("nonexistent")  # no exception


# ─── Window advancement ─────────────────────────────────────


class TestWindowAdvancement:
    def test_window_advances_after_first_chunk_ready(self, window_3: ChunkWindow):
        # Process chunk 0
        window_3.start_chunk("c0")
        window_3.complete_chunk("c0")

        # Window should have advanced past c0
        status = window_3.get_buffer_status()
        assert status["window_position"] == 1

        # New window should include c3
        next_chunks = window_3.get_next_window()
        assert "c3" in next_chunks

    def test_window_advances_multiple(self, window_3: ChunkWindow):
        # Complete c0, c1, c2 in order
        for cid in ["c0", "c1", "c2"]:
            window_3.start_chunk(cid)
            window_3.complete_chunk(cid)

        status = window_3.get_buffer_status()
        assert status["window_position"] == 3

        # Window now covers c3, c4, c5
        next_chunks = window_3.get_next_window()
        assert set(next_chunks) == {"c3", "c4", "c5"}

    def test_window_does_not_advance_if_middle_not_ready(self, window_3: ChunkWindow):
        # Complete c0 but not c1
        window_3.start_chunk("c0")
        window_3.complete_chunk("c0")

        # c1 is still processing, window stays at 1
        window_3.start_chunk("c1")  # c1 starts but not complete
        status = window_3.get_buffer_status()
        assert status["window_position"] == 1  # c0 ready, c1 not → position=1


# ─── fail_chunk ─────────────────────────────────────────────


class TestFailChunk:
    def test_fail_sets_status(self, window_3: ChunkWindow):
        window_3.start_chunk("c0")
        window_3.fail_chunk("c0", "TTS error")
        status = window_3.get_buffer_status()
        assert status["failed"] == 1
        assert status["processing"] == 0

    def test_failed_chunk_returned_in_next_window(self, window_3: ChunkWindow):
        window_3.start_chunk("c0")
        window_3.fail_chunk("c0", "error")
        # Failed chunks should be eligible for retry
        next_chunks = window_3.get_next_window()
        assert "c0" in next_chunks


# ─── publish_chunk ──────────────────────────────────────────


class TestPublishChunk:
    def test_publish_sets_status(self, window_3: ChunkWindow):
        window_3.start_chunk("c0")
        window_3.complete_chunk("c0")
        window_3.publish_chunk("c0")
        status = window_3.get_buffer_status()
        assert status["published"] == 1
        assert status["ready"] == 0

    def test_published_chunk_advances_window(self, window_3: ChunkWindow):
        for cid in ["c0", "c1", "c2"]:
            window_3.start_chunk(cid)
            window_3.complete_chunk(cid)
            window_3.publish_chunk(cid)
        status = window_3.get_buffer_status()
        assert status["window_position"] == 3


# ─── is_complete ────────────────────────────────────────────


class TestIsComplete:
    def test_not_complete_initially(self, window_3: ChunkWindow):
        assert window_3.is_complete() is False

    def test_complete_after_all_ready(self, window_3: ChunkWindow):
        for cid in ["c0", "c1", "c2", "c3", "c4", "c5"]:
            window_3.start_chunk(cid)
            window_3.complete_chunk(cid)
        assert window_3.is_complete() is True

    def test_complete_after_all_published(self, window_3: ChunkWindow):
        for cid in ["c0", "c1", "c2", "c3", "c4", "c5"]:
            window_3.start_chunk(cid)
            window_3.complete_chunk(cid)
            window_3.publish_chunk(cid)
        assert window_3.is_complete() is True

    def test_not_complete_with_failed(self, window_3: ChunkWindow):
        for cid in ["c0", "c1", "c2", "c3", "c4", "c5"]:
            window_3.start_chunk(cid)
            if cid == "c2":
                window_3.fail_chunk(cid, "error")
            else:
                window_3.complete_chunk(cid)
        assert window_3.is_complete() is False


# ─── get_ready_chunks ───────────────────────────────────────


class TestGetReadyChunks:
    def test_empty_initially(self, window_3: ChunkWindow):
        assert window_3.get_ready_chunks() == []

    def test_returns_ready_in_order(self, window_3: ChunkWindow):
        window_3.start_chunk("c2")
        window_3.start_chunk("c0")
        window_3.complete_chunk("c2")
        window_3.complete_chunk("c0")
        ready = window_3.get_ready_chunks()
        assert ready == ["c0", "c2"]  # sorted by index


# ─── get_buffer_status ──────────────────────────────────────


class TestBufferStatus:
    def test_all_fields_present(self, window_3: ChunkWindow):
        status = window_3.get_buffer_status()
        assert "queued" in status
        assert "processing" in status
        assert "ready" in status
        assert "published" in status
        assert "failed" in status
        assert "total" in status
        assert "window_position" in status
        assert "window_size" in status

    def test_counts_consistent(self, window_3: ChunkWindow):
        window_3.start_chunk("c0")
        window_3.start_chunk("c1")
        window_3.complete_chunk("c0")
        window_3.fail_chunk("c2", "err")
        status = window_3.get_buffer_status()
        total = status["queued"] + status["processing"] + status["ready"] + status["published"] + status["failed"]
        assert total == status["total"]
