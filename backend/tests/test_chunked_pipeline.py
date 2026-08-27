"""
Integration tests for chunked pipeline.

Tests the chunked pipeline functionality including:
- Video splitting
- Segment splitting
- Chunk processing
- Concatenation

Note: These tests require a video file for full integration testing.
Run with: python -m pytest backend/tests/test_chunked_pipeline.py -v
"""

import os
import json
import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.services.chunked_pipeline import (
    split_video_into_chunks,
    split_segments_into_chunks,
    concat_video_chunks,
    get_video_duration,
    VideoChunk,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_video():
    """Create a sample video for testing."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    # Create a 30-second test video with ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=30:size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        video_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    yield video_path

    # Cleanup
    os.unlink(video_path)


@pytest.fixture
def sample_segments():
    """Create sample segments for testing."""
    return [
        {"id": 1, "start": 0.0, "end": 5.0, "text": "Segment 1"},
        {"id": 2, "start": 5.0, "end": 10.0, "text": "Segment 2"},
        {"id": 3, "start": 10.0, "end": 15.0, "text": "Segment 3"},
        {"id": 4, "start": 15.0, "end": 20.0, "text": "Segment 4"},
        {"id": 5, "start": 20.0, "end": 25.0, "text": "Segment 5"},
        {"id": 6, "start": 25.0, "end": 30.0, "text": "Segment 6"},
    ]


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


# ============================================================================
# Tests: get_video_duration
# ============================================================================

class TestGetVideoDuration:
    """Test get_video_duration function."""

    def test_returns_positive_duration(self, sample_video):
        """Should return positive duration for valid video."""
        duration = get_video_duration(sample_video)
        assert duration > 0
        assert duration == pytest.approx(30.0, abs=1.0)

    def test_returns_zero_for_invalid(self):
        """Should return 0 for invalid video path."""
        duration = get_video_duration("/nonexistent/video.mp4")
        assert duration == 0


# ============================================================================
# Tests: split_video_into_chunks
# ============================================================================

class TestSplitVideoIntoChunks:
    """Test split_video_into_chunks function."""

    def test_creates_chunks(self, sample_video, temp_dir):
        """Should create video chunks."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )
        assert len(chunks) == 3  # 30s / 10s = 3 chunks

    def test_chunk_files_exist(self, sample_video, temp_dir):
        """Should create actual video files."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )
        for chunk in chunks:
            assert os.path.exists(chunk.video_path)
            assert os.path.getsize(chunk.video_path) > 0

    def test_chunk_timing(self, sample_video, temp_dir):
        """Should have correct start/end times."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )
        assert chunks[0].start_sec == 0
        assert chunks[0].end_sec == 10
        assert chunks[1].start_sec == 10
        assert chunks[1].end_sec == 20
        assert chunks[2].start_sec == 20
        assert chunks[2].end_sec == 30

    def test_overlap(self, sample_video, temp_dir):
        """Should handle overlap between chunks."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=2,
        )
        # With overlap, next chunk starts 2s before previous ends
        # Chunk 0: 0-10s, Chunk 1: 8-18s (overlap at 8-10s), Chunk 2: 16-26s
        assert chunks[0].start_sec == 0
        assert chunks[0].end_sec == 10
        assert chunks[1].start_sec == 8  # 10 - 2 overlap
        assert chunks[1].end_sec == 18  # 8 + 10 duration


# ============================================================================
# Tests: split_segments_into_chunks
# ============================================================================

class TestSplitSegmentsIntoChunks:
    """Test split_segments_into_chunks function."""

    def test_distributes_segments(self, sample_segments, sample_video, temp_dir):
        """Should distribute segments to appropriate chunks."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )
        segment_chunks = split_segments_into_chunks(sample_segments, chunks)

        # Each chunk should have 2 segments (6 segments / 3 chunks)
        assert len(segment_chunks) == 3
        assert len(segment_chunks[0]) == 2  # Segments 1-2
        assert len(segment_chunks[1]) == 2  # Segments 3-4
        assert len(segment_chunks[2]) == 2  # Segments 5-6

    def test_handles_empty_segments(self, sample_video, temp_dir):
        """Should handle empty segments list."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )
        segment_chunks = split_segments_into_chunks([], chunks)
        assert len(segment_chunks) == 3
        assert all(len(s) == 0 for s in segment_chunks)


# ============================================================================
# Tests: concat_video_chunks
# ============================================================================

class TestConcatVideoChunks:
    """Test concat_video_chunks function."""

    def test_concatenates_chunks(self, sample_video, temp_dir):
        """Should concatenate multiple chunks into one video."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )

        output_path = os.path.join(temp_dir, "concatenated.mp4")
        result = concat_video_chunks(
            [c.video_path for c in chunks],
            output_path,
        )

        assert os.path.exists(result)
        assert os.path.getsize(result) > 0

    def test_single_chunk_copy(self, sample_video, temp_dir):
        """Should copy single chunk without concatenation."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )

        output_path = os.path.join(temp_dir, "single.mp4")
        result = concat_video_chunks(
            [chunks[0].video_path],
            output_path,
        )

        assert os.path.exists(result)
        # Should be a copy, same size
        assert os.path.getsize(result) == os.path.getsize(chunks[0].video_path)

    def test_concat_duration(self, sample_video, temp_dir):
        """Should produce video with correct total duration."""
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )

        output_path = os.path.join(temp_dir, "concatenated.mp4")
        concat_video_chunks(
            [c.video_path for c in chunks],
            output_path,
        )

        # Check duration (should be ~30s)
        duration = get_video_duration(output_path)
        assert duration == pytest.approx(30.0, abs=2.0)


# ============================================================================
# Tests: Integration
# ============================================================================

class TestIntegration:
    """Integration tests for the full chunked pipeline."""

    def test_full_pipeline(self, sample_video, sample_segments, temp_dir):
        """Test the complete chunked pipeline flow."""
        # 1. Split video
        chunks = split_video_into_chunks(
            sample_video, temp_dir,
            chunk_duration_sec=10,
            overlap_sec=0,
        )
        assert len(chunks) == 3

        # 2. Split segments
        segment_chunks = split_segments_into_chunks(sample_segments, chunks)
        assert len(segment_chunks) == 3

        # 3. Verify each chunk has segments
        for i, (chunk, segs) in enumerate(zip(chunks, segment_chunks)):
            assert len(segs) > 0, f"Chunk {i} has no segments"
            assert os.path.exists(chunk.video_path)

        # 4. Concat (simulating merge results)
        # In real pipeline, each chunk would be merged with its audio
        output_path = os.path.join(temp_dir, "final.mp4")
        result = concat_video_chunks(
            [c.video_path for c in chunks],
            output_path,
        )

        assert os.path.exists(result)
        duration = get_video_duration(result)
        assert duration == pytest.approx(30.0, abs=2.0)


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
