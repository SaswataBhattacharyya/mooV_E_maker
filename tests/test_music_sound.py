from pathlib import Path
import unittest

from story_builder.services.music_sound import MusicSoundError, build_ace_workflow, new_music_job


class MusicSoundTests(unittest.TestCase):
    def test_ace_workflow_maps_friendly_settings(self):
        job = new_music_job({"mode": "song", "tags": "folk, warm", "lyrics": "[Verse]\nHello", "duration": 12, "seed": 42, "steps": 27, "cfg": 4.5})
        workflow = build_ace_workflow(job)
        self.assertEqual(workflow["2"]["inputs"]["seconds"], 12)
        self.assertEqual(workflow["3"]["inputs"]["tags"], "folk, warm")
        self.assertEqual(workflow["8"]["inputs"]["seed"], 42)
        self.assertTrue(workflow["10"]["inputs"]["filename_prefix"].endswith(job["job_id"]))

    def test_song_requires_lyrics(self):
        with self.assertRaisesRegex(MusicSoundError, "lyrics"):
            new_music_job({"mode": "song", "tags": "folk", "lyrics": ""})

    def test_original_ace_workflows_remain_present(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "workflows/qwen_image/audio_ace_step_1_t2a_song.json").is_file())
        self.assertTrue((root / "workflows/qwen_image/audio_ace_step_1_t2a_instrumentals.json").is_file())
