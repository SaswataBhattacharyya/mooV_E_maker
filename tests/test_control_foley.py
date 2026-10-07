import tempfile
import unittest
from pathlib import Path

from story_builder.services.control_foley import ControlFoleyError, build_workflow, new_job, stage_inputs


class ControlFoleyTests(unittest.TestCase):
    def test_text_mode_maps_prompt_and_has_no_video(self):
        job = new_job({"mode": "text_audio", "prompt": "rain", "duration": 5, "seed": 9})
        stage_inputs(project_dir=Path(tempfile.mkdtemp()), comfy_input_dir=Path(tempfile.mkdtemp()), job=job, video=None, reference_audio=None)
        workflow = build_workflow(job)
        self.assertEqual(workflow["2"]["inputs"]["prompt"], "rain")
        self.assertNotIn("LoadControlFoleyVideo", {node["class_type"] for node in workflow.values()})

    def test_video_mode_requires_video(self):
        job = new_job({"mode": "text_video_audio", "prompt": "steps"})
        with self.assertRaisesRegex(ControlFoleyError, "video"):
            stage_inputs(project_dir=Path(tempfile.mkdtemp()), comfy_input_dir=Path(tempfile.mkdtemp()), job=job, video=None, reference_audio=None)

    def test_reference_mode_stages_both_inputs(self):
        project, comfy = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        job = new_job({"mode": "reference_video_audio"})
        stage_inputs(project_dir=project, comfy_input_dir=comfy, job=job, video=("a.mp4", b"video"), reference_audio=("a.wav", b"audio"))
        workflow = build_workflow(job)
        self.assertIn("story_builder_control_foley", workflow["2"]["inputs"]["video_path"])
        self.assertIn("story_builder_control_foley", workflow["3"]["inputs"]["reference_audio_path"])


if __name__ == "__main__": unittest.main()
