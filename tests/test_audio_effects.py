from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from story_builder.services import audio_effects


class AudioEffectsTests(unittest.TestCase):
    def test_operation_workflows_are_fixed_and_present(self) -> None:
        self.assertEqual(set(audio_effects.OPERATION_WORKFLOWS), {"noise_cleanup", "voice_repair", "voice_changer", "rvc", "emotion", "style"})
        self.assertTrue(all(path.is_file() for path in audio_effects.OPERATION_WORKFLOWS.values()))

    def test_cleanup_uses_remaining_stem(self) -> None:
        workflow = audio_effects.build_workflow(operation="noise_cleanup", settings={}, comfy_input_name="test.wav", filename_prefix="test/out")
        self.assertEqual(workflow["3"]["inputs"]["audio"], ["2", 1])
        self.assertEqual(workflow["3"]["inputs"]["format"], "flac")

    def test_step_edits_require_transcript_and_validate_choice(self) -> None:
        with self.assertRaisesRegex(audio_effects.AudioEffectError, "transcript"):
            audio_effects.build_workflow(operation="emotion", settings={}, comfy_input_name="test.wav", filename_prefix="test/out")
        workflow = audio_effects.build_workflow(operation="style", settings={"transcript": "Exact words.", "style": "whisper"}, comfy_input_name="test.wav", filename_prefix="test/out")
        self.assertEqual(workflow["3"]["inputs"]["edit_type"], "style")
        self.assertEqual(workflow["3"]["inputs"]["style"], "whisper")

    def test_rvc_uses_only_discovered_local_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "RVC"; (root / ".index").mkdir(parents=True)
            (root / "Test.pth").write_bytes(b"model")
            (root / ".index" / "Test.index").write_bytes(b"index")
            with patch.object(audio_effects, "RVC_ROOT", root):
                workflow = audio_effects.build_workflow(operation="rvc", settings={"model": "Test.pth", "index_file": "Test.index", "pitch": 4}, comfy_input_name="test.wav", filename_prefix="test/out")
            self.assertEqual(workflow["3"]["inputs"]["pitch"], 4)
            self.assertFalse(workflow["4"]["inputs"]["auto_download"])

    def test_project_source_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(audio_effects.AudioEffectError, "escapes"):
                audio_effects.safe_project_source(Path(temp_dir) / "project", "../outside.wav")


if __name__ == "__main__":
    unittest.main()
