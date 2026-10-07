import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from story_builder.services import audio_catalog
from story_builder.services.workflow_catalog import load_workflow_catalog


class AudioCatalogTests(unittest.TestCase):
    def test_workflow_catalog_handles_ui_and_api_exports(self) -> None:
        catalog = load_workflow_catalog()
        self.assertTrue(catalog)
        api = next(item for item in catalog if item["id"] == "api/audio/ace_step_music_api.json")
        self.assertTrue(api["supports_api_submission"])
        self.assertEqual(api["format"], "api")
        ui = next(item for item in catalog if item["id"] == "audio/TTS_audio_multichar_timed_wf.json")
        self.assertFalse(ui["supports_api_submission"])
        self.assertEqual(ui["format"], "ui")

    def test_discover_voices_requires_companion_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            comfy_root = Path(temp_dir) / "ComfyUI"
            voice_root = comfy_root / "models" / "voices"
            voice_root.mkdir(parents=True)
            (voice_root / "ready.wav").write_bytes(b"not-real-audio")
            (voice_root / "ready.reference.txt").write_text("Exact spoken words.", encoding="utf-8")
            (voice_root / "missing.wav").write_bytes(b"not-real-audio")

            with patch.dict(os.environ, {"COMFYUI_ROOT": str(comfy_root)}):
                voices = {voice["name"]: voice for voice in audio_catalog.discover_voices()}

            self.assertTrue(voices["ready"]["discoverable"])
            self.assertEqual(voices["ready"]["source"], "user")
            self.assertFalse(voices["missing"]["discoverable"])

    def test_audio_block_rollout_exposes_available_and_future_blocks(self) -> None:
        blocks = {block["id"]: block for block in audio_catalog.audio_blocks()}

        self.assertEqual(blocks["voice_library"]["status"], "available")
        self.assertEqual(blocks["tts_multichar_timed"]["status"], "available")
        self.assertEqual(blocks["voice_discovery_live"]["status"], "available")
        self.assertEqual(blocks["finetune"]["status"], "available")

    def test_install_reference_voice_writes_audio_and_exact_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            comfy_root = Path(temp_dir) / "ComfyUI"
            with patch.dict(os.environ, {"COMFYUI_ROOT": str(comfy_root)}):
                result = audio_catalog.install_reference_voice(
                    name="Alice warm",
                    filename="sample.wav",
                    audio=b"audio-bytes",
                    transcript="These are the exact words.",
                )
                voices = audio_catalog.discover_voices()

            self.assertEqual(Path(result["audio_path"]).read_bytes(), b"audio-bytes")
            self.assertEqual(Path(result["transcript_path"]).read_text(encoding="utf-8"), "These are the exact words.\n")
            self.assertTrue(any(voice["name"] == "Alice warm" and voice["discoverable"] for voice in voices))

    def test_install_reference_voice_rejects_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            comfy_root = Path(temp_dir) / "ComfyUI"
            with patch.dict(os.environ, {"COMFYUI_ROOT": str(comfy_root)}):
                audio_catalog.install_reference_voice(name="Alice", filename="a.wav", audio=b"one", transcript="One")
                with self.assertRaises(FileExistsError):
                    audio_catalog.install_reference_voice(name="Alice", filename="b.wav", audio=b"two", transcript="Two")

    def test_architecture_report_has_required_fields(self) -> None:
        report = audio_catalog.system_architecture()

        self.assertTrue(report["machine"])
        self.assertIsInstance(report["is_aarch64"], bool)


if __name__ == "__main__":
    unittest.main()
