import wave
from pathlib import Path
import tempfile
import unittest

from story_builder.services.audio_utilities import AudioUtilityError, import_library_asset, library_assets, safe_name, stage_inputs


def wav_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "fixture.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000); handle.writeframes(b"\0\0" * 1600)
    return path.read_bytes()


class AudioUtilityTests(unittest.TestCase):
    def test_library_deduplicates_by_content(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory); content = wav_bytes(tmp_path); root = tmp_path / "library"
            first = import_library_asset(root, filename="one.wav", content=content)
            second = import_library_asset(root, filename="two.wav", content=content)
            self.assertTrue(second["duplicate"])
            self.assertEqual(second["asset_id"], first["asset_id"])
            self.assertEqual(len(library_assets(root)), 1)

    def test_stage_inputs_preserves_safe_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            staged = stage_inputs(tmp_path, "job", [("a.wav", "folder/a.wav", wav_bytes(tmp_path))], "noise_cleanup")
            self.assertEqual(staged[0]["source_relative_path"], "folder/a.wav")
            self.assertTrue((tmp_path / staged[0]["relative_path"]).is_file())

    def test_stage_inputs_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            with self.assertRaisesRegex(AudioUtilityError, "unsafe"):
                stage_inputs(tmp_path, "job", [("a.wav", "../a.wav", wav_bytes(tmp_path))], "noise_cleanup")

    def test_collection_slug(self):
        self.assertEqual(safe_name(" My Output / 1 "), "my-output-1")
