import tempfile
import unittest
from pathlib import Path

from story_builder.services import audio_reconstruct


class AudioReconstructTests(unittest.TestCase):
    def test_calibration_parts_takes_and_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            audio_reconstruct.calibrate(project, "Alice", "A common sentence", {"overlay": 0.7})
            audio_reconstruct.add_part(project, "scene_001_line_001", "Alice", 1, "Hello there")
            take = audio_reconstruct.add_take(project, "scene_001_line_001", "mic.wav", b"wav", "Hello there")
            result = audio_reconstruct.accept_take(project, "scene_001_line_001", take["take_id"])
            self.assertEqual(result["take"]["status"], "accepted")
            self.assertEqual(result["part"]["accepted_take_id"], take["take_id"])
            self.assertTrue((project / result["part"]["accepted_path"]).exists())

    def test_uncalibrated_character_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(audio_reconstruct.ReconstructionError):
                audio_reconstruct.add_part(Path(temp), "part", "Alice", 1, "Hello")


if __name__ == "__main__":
    unittest.main()
