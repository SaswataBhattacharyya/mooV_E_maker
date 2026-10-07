from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "runner"
sys.path.insert(0, str(RUNNER))

from comfyui_runner import _minimax_frames, prepare_workflow  # noqa: E402
from request_schema import MediaRequest  # noqa: E402


class WorkflowInjectionTests(unittest.TestCase):
    def test_text_to_image_injection(self) -> None:
        request = MediaRequest.from_dict({"workflow": "z-image-turbo", "prompt": "A red fox", "width": 1024, "height": 768, "seed": 7})
        workflow = prepare_workflow(request, [], "test/run")
        self.assertEqual(workflow["45"]["inputs"]["text"], "A red fox")
        self.assertEqual(workflow["41"]["inputs"]["width"], 1024)
        self.assertEqual(workflow["44"]["inputs"]["seed"], 7)
        self.assertEqual(workflow["76"]["inputs"]["filename_prefix"], "test/run")

    def test_optional_second_minimax_frame_is_removed(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            request = MediaRequest.from_dict({"workflow": "minimax-h3-i2v", "prompt": "Move forward", "input_images": [image.name], "duration": 5})
            workflow = prepare_workflow(request, ["uploaded.png"], "test/run")
        self.assertNotIn("2", workflow)
        self.assertNotIn("last_frame", workflow["104"]["inputs"])
        self.assertEqual(workflow["104"]["inputs"]["length"], _minimax_frames(5))

    def test_unused_qwen_references_are_removed(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            request = MediaRequest.from_dict({"workflow": "qwen-image-edit-2511", "prompt": "Change only the sky", "input_images": [image.name]})
            workflow = prepare_workflow(request, ["uploaded.png"], "test/run")
        self.assertNotIn("120", workflow)
        self.assertNotIn("image2", workflow["111"]["inputs"])


if __name__ == "__main__":
    unittest.main()
