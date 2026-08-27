import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.api.routes import _normalize_audio_mix_mode, _job_to_response
from backend.services import merger


class TestAudioModeContract(unittest.TestCase):
    def test_only_supported_modes_are_accepted(self):
        self.assertEqual(_normalize_audio_mix_mode("dubbed_only"), "dubbed_only")
        self.assertEqual(_normalize_audio_mix_mode("ducked_mix"), "ducked_mix")
        self.assertEqual(_normalize_audio_mix_mode("mix_original"), "dubbed_only")
        self.assertEqual(_normalize_audio_mix_mode(None), "dubbed_only")

    def test_job_mode_overrides_global_default(self):
        job = SimpleNamespace(
            id="job-1",
            status="COMPLETED",
            progress=100.0,
            status_message="Done",
            youtube_url="https://youtu.be/abc12345678",
            video_title="Test",
            video_duration=10.0,
            video_thumbnail=None,
            output_video_url="/api/outputs/job-1/video",
            transcript_text=None,
            translated_text=None,
            error_message=None,
            error_code=None,
            created_at=None,
            updated_at=None,
            speaker_gender=None,
            voice_gender_setting="auto",
            audio_mix_mode="ducked_mix",
            uzbek_srt_content=None,
            rating=None,
            feedback_comment=None,
            feedback_voice_ok=None,
            feedback_translation_ok=None,
            feedback_speed_ok=None,
            content_flagged=False,
            original_video_path="video.mp4",
        )
        with patch("backend.api.routes.settings", SimpleNamespace(AUDIO_MIX_MODE="dubbed_only")):
            response = _job_to_response(job)
        self.assertEqual(response.audio_mix_mode, "ducked_mix")

    def test_explicit_dubbed_only_mode_uses_tts_input(self):
        settings = SimpleNamespace(
            AUDIO_MIX_MODE="dubbed_only",
            VOICE_HIGHPASS_HZ=80,
            VOICE_EQ_FREQ_HZ=3000,
            VOICE_EQ_GAIN_DB=2.5,
            VOICE_COMPRESSOR_RATIO=3.0,
            VOICE_GAIN_BOOST_DB=5.0,
            VOICE_LIMITER_LIMIT=0.95,
            FINAL_LOUDNORM_I=-16.0,
            FINAL_LOUDNORM_TP=-1.5,
            FINAL_LOUDNORM_LRA=11.0,
        )
        with patch.object(merger, "settings", settings):
            graph = merger._build_audio_filtergraph("dubbed_only")

        self.assertIn("[1:a]", graph)
        self.assertNotIn("[0:a]", graph)
