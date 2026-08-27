import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.services import merger


_SETTINGS = {
    "AUDIO_MIX_MODE": "dubbed_only",
    "DUCKING_THRESHOLD": 0.012,
    "DUCKING_RATIO": 20.0,
    "DUCKING_ATTACK_MS": 5,
    "DUCKING_RELEASE_MS": 400,
    "VOICE_HIGHPASS_HZ": 80,
    "VOICE_EQ_FREQ_HZ": 3000,
    "VOICE_EQ_GAIN_DB": 2.5,
    "VOICE_COMPRESSOR_RATIO": 3.0,
    "VOICE_GAIN_BOOST_DB": 5.0,
    "VOICE_LIMITER_LIMIT": 0.95,
    "FINAL_LOUDNORM_I": -16.0,
    "FINAL_LOUDNORM_TP": -1.5,
    "FINAL_LOUDNORM_LRA": 11.0,
}


def _settings_with_mode(mode: str) -> SimpleNamespace:
    values = dict(_SETTINGS)
    values["AUDIO_MIX_MODE"] = mode
    return SimpleNamespace(**values)


class TestAudioMixModes(unittest.TestCase):
    def test_dubbed_only_uses_tts_input_only(self):
        settings = _settings_with_mode("dubbed_only")
        with patch.object(merger, "settings", settings):
            graph = merger._build_audio_filtergraph()

        self.assertIn("[1:a]", graph)
        self.assertNotIn("[0:a]", graph)
        self.assertNotIn("amix=inputs=2", graph)
        self.assertIn("[final]", graph)

    def test_ducked_mix_keeps_legacy_original_audio_path(self):
        settings = _settings_with_mode("ducked_mix")
        with patch.object(merger, "settings", settings):
            graph = merger._build_audio_filtergraph()

        self.assertIn("[0:a]", graph)
        self.assertIn("[1:a]", graph)
        self.assertIn("amix=inputs=2", graph)

    def test_unknown_mode_falls_back_to_dubbed_only(self):
        settings = _settings_with_mode("unexpected")
        with patch.object(merger, "settings", settings):
            graph = merger._build_audio_filtergraph()

        self.assertIn("[1:a]", graph)
        self.assertNotIn("[0:a]", graph)
        self.assertNotIn("amix=inputs=2", graph)

    def test_explicit_job_mode_overrides_global_default(self):
        settings = _settings_with_mode("dubbed_only")
        with patch.object(merger, "settings", settings):
            graph = merger._build_audio_filtergraph("ducked_mix")

        self.assertIn("[0:a]", graph)
        self.assertIn("amix=inputs=2", graph)


if __name__ == "__main__":
    unittest.main()
