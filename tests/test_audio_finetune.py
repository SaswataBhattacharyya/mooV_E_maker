from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from story_builder.services import audio_finetune


class F5DatasetTests(unittest.TestCase):
    def _roots(self, temp_dir: str) -> tuple[Path, Path]:
        comfy = Path(temp_dir) / "ComfyUI"
        suite = comfy / "custom_nodes" / "TTS-Audio-Suite"
        for model, checkpoint in audio_finetune.SUPPORTED_MODELS.items():
            model_dir = comfy / "models" / "TTS" / "F5-TTS" / model
            model_dir.mkdir(parents=True)
            (model_dir / checkpoint).write_bytes(b"checkpoint")
            (model_dir / "vocab.txt").write_text(" \na\nb\n", encoding="utf-8")
        utils = suite / "engines" / "f5_tts" / "model" / "utils.py"
        utils.parent.mkdir(parents=True)
        utils.write_text("def convert_char_to_pinyin(texts, polyphone=True):\n    return texts\n", encoding="utf-8")
        return comfy, suite

    def _wav(self, path: Path) -> bytes:
        sf.write(path, np.sin(np.linspace(0, 20, 2400)).astype("float32"), 24000)
        return path.read_bytes()

    def test_metadata_requires_expected_header(self) -> None:
        with self.assertRaisesRegex(audio_finetune.F5DatasetError, "header"):
            audio_finetune.read_metadata(b"file,text\na.wav,hello\n")

    def test_stage_and_prepare_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            comfy, suite = self._roots(temp_dir)
            sample = Path(temp_dir) / "sample.wav"
            audio = self._wav(sample)
            project = Path(temp_dir) / "project"
            with patch.dict("os.environ", {"COMFYUI_ROOT": str(comfy), "TTS_AUDIO_SUITE_ROOT": str(suite)}):
                manifest = audio_finetune.stage_dataset(
                    project_dir=project,
                    dataset_name="alice_dataset",
                    model="F5TTS_Base",
                    metadata=b"audio_file|text\nsample.wav|Hello Alice.\n",
                    uploads=[("sample.wav", audio)],
                )
                job = audio_finetune.new_prepare_job(manifest)
                updates: dict = {}
                audio_finetune.prepare_dataset(project_dir=project, job=job, update=updates.update)

            self.assertEqual(updates["status"], "completed")
            self.assertEqual(manifest["sample_count"], 1)
            self.assertTrue(Path(updates["artifacts"]["raw_arrow"]).is_file())
            self.assertFalse(updates.get("training_enabled", False))
            self.assertIn("--finetune", updates["command_preview"])

    def test_stage_rejects_unlisted_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            comfy, suite = self._roots(temp_dir)
            sample = Path(temp_dir) / "sample.wav"
            audio = self._wav(sample)
            with patch.dict("os.environ", {"COMFYUI_ROOT": str(comfy), "TTS_AUDIO_SUITE_ROOT": str(suite)}):
                with self.assertRaisesRegex(audio_finetune.F5DatasetError, "not listed"):
                    audio_finetune.stage_dataset(
                        project_dir=Path(temp_dir) / "project",
                        dataset_name="dataset",
                        model="F5TTS_Base",
                        metadata=b"audio_file|text\nsample.wav|Hello.\n",
                        uploads=[("sample.wav", audio), ("extra.wav", audio)],
                    )


if __name__ == "__main__":
    unittest.main()
