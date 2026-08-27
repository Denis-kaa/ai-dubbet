"""
Tests for NVENC GPU encoding detection and fallback.

Tests the NVENC auto-detection and codec selection logic.

Run with: python -m pytest backend/tests/test_nvenc.py -v
"""

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from backend.services.merger import _has_nvenc, _get_video_codec, _get_video_codec_for_chunk


class TestHasNvenc:
    """Test NVENC detection logic."""

    def test_returns_bool(self):
        """Should return a boolean value."""
        result = _has_nvenc()
        assert isinstance(result, bool)

    @patch("backend.services.merger.settings")
    def test_returns_false_when_disabled(self, mock_settings):
        """Should return False when ENABLE_NVENC=False."""
        mock_settings.ENABLE_NVENC = False
        # Clear cache
        _has_nvenc.cache_clear()
        result = _has_nvenc()
        assert result is False

    @patch("backend.services.merger.subprocess.run")
    @patch("backend.services.merger.settings")
    def test_returns_true_when_nvenc_available(self, mock_settings, mock_run):
        """Should return True when NVENC is found in FFmpeg encoders."""
        mock_settings.ENABLE_NVENC = True
        mock_run.return_value = MagicMock(
            stdout=" V..... h264_nvenc      NVIDIA NVENC H.264 Encoder",
            returncode=0,
        )
        _has_nvenc.cache_clear()
        result = _has_nvenc()
        assert result is True

    @patch("backend.services.merger.subprocess.run")
    @patch("backend.services.merger.settings")
    def test_returns_false_when_nvenc_not_found(self, mock_settings, mock_run):
        """Should return False when NVENC is not found."""
        mock_settings.ENABLE_NVENC = True
        mock_run.return_value = MagicMock(
            stdout=" V..... libx264      libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
            returncode=0,
        )
        _has_nvenc.cache_clear()
        result = _has_nvenc()
        assert result is False

    @patch("backend.services.merger.subprocess.run")
    @patch("backend.services.merger.settings")
    def test_returns_false_on_error(self, mock_settings, mock_run):
        """Should return False when FFmpeg command fails."""
        mock_settings.ENABLE_NVENC = True
        mock_run.side_effect = Exception("FFmpeg not found")
        _has_nvenc.cache_clear()
        result = _has_nvenc()
        assert result is False


class TestGetVideoCodec:
    """Test codec selection logic."""

    @patch("backend.services.merger._has_nvenc")
    def test_returns_nvenc_when_available(self, mock_nvenc):
        """Should return NVENC codec when available."""
        mock_nvenc.return_value = True
        codec, args = _get_video_codec()
        assert codec == "h264_nvenc"
        assert "-preset" in args
        assert "-tune" in args
        assert "-rc" in args
        assert "-cq" in args

    @patch("backend.services.merger._has_nvenc")
    def test_returns_libx264_when_not_available(self, mock_nvenc):
        """Should return libx264 when NVENC is not available."""
        mock_nvenc.return_value = False
        codec, args = _get_video_codec()
        assert codec == "libx264"
        assert "-preset" in args
        assert "-crf" in args
        assert "-threads" in args

    @patch("backend.services.merger._has_nvenc")
    def test_nvenc_args_match_config(self, mock_nvenc):
        """Should use config values for NVENC args."""
        mock_nvenc.return_value = True
        codec, args = _get_video_codec()
        # Check that preset is in args
        assert "p1" in args  # Default NVENC_PRESET

    @patch("backend.services.merger._has_nvenc")
    def test_libx264_uses_ultrafast(self, mock_nvenc):
        """Should use ultrafast preset for libx264."""
        mock_nvenc.return_value = False
        codec, args = _get_video_codec()
        assert "ultrafast" in args


class TestGetVideoCodecForChunk:
    """Test chunk-specific codec selection."""

    @patch("backend.services.merger._has_nvenc")
    def test_returns_same_as_main(self, mock_nvenc):
        """Should return same codec as main function."""
        mock_nvenc.return_value = True
        codec1, args1 = _get_video_codec()
        codec2, args2 = _get_video_codec_for_chunk(0)
        assert codec1 == codec2
        assert args1 == args2


class TestNvencIntegration:
    """Integration tests for NVENC in merge functions."""

    def test_has_nvenc_is_cached(self):
        """Should cache NVENC detection result."""
        # First call
        result1 = _has_nvenc()
        # Second call should use cache
        result2 = _has_nvenc()
        assert result1 == result2

    @patch("backend.services.merger._has_nvenc")
    def test_codec_selection_integration(self, mock_nvenc):
        """Test complete codec selection flow."""
        # Test with NVENC
        mock_nvenc.return_value = True
        codec, args = _get_video_codec()
        assert codec == "h264_nvenc"
        assert len(args) > 0

        # Test without NVENC
        mock_nvenc.return_value = False
        codec, args = _get_video_codec()
        assert codec == "libx264"
        assert len(args) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
