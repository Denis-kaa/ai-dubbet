import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.services import audio_qa


class _FakeAudio:
    max_dBFS = -10.0

    def __len__(self):
        return 10000

    def __getitem__(self, item):
        window = _FakeAudioWindow()
        if isinstance(item, slice) and item.start == 1000:
            window.dBFS = -60.0
        return window


class _FakeAudioWindow:
    dBFS = -20.0

    def __len__(self):
        return 1000


class TestFinalAudioQA(unittest.TestCase):
    def _run(self, mode):
        settings = SimpleNamespace(AUDIO_MIX_MODE=mode)
        timings = [{"start": 0.0, "end": 1.0}, {"start": 3.0, "end": 4.0}]
        with (
            patch.object(audio_qa.AudioSegment, "from_file", return_value=_FakeAudio()),
            patch.object(audio_qa, "_measure_loudness_range", return_value=5.0),
            patch.object(audio_qa, "get_settings", return_value=settings),
        ):
            return audio_qa.check_final_mix_quality("fixture.mp4", timings)

    def test_dubbed_only_does_not_require_original_background(self):
        result = self._run("dubbed_only")

        self.assertNotIn("background_missing", result["flags"])
        self.assertIsNone(result["background_rms_dbfs"])

    def test_ducked_mix_keeps_background_check(self):
        result = self._run("ducked_mix")

        self.assertIn("background_missing", result["flags"])
        self.assertEqual(result["background_rms_dbfs"], -60.0)


if __name__ == "__main__":
    unittest.main()
