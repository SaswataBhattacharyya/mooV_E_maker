from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RUNNER = Path(__file__).resolve().parents[1] / "runner"
sys.path.insert(0, str(RUNNER))

from comfyui_client import ComfyUIClient  # noqa: E402


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class OutputTests(unittest.TestCase):
    @patch("urllib.request.urlopen", side_effect=lambda *_args, **_kwargs: _Response(b"media"))
    def test_collects_image_and_video(self, _urlopen) -> None:
        history = {"outputs": {"1": {"images": [{"filename": "a.png"}]}, "2": {"videos": [{"filename": "b.mp4"}]}}}
        with tempfile.TemporaryDirectory() as temp:
            outputs = ComfyUIClient().download_outputs(history, Path(temp))
            self.assertEqual([item["kind"] for item in outputs], ["image", "video"])
            self.assertTrue((Path(temp) / "a.png").exists())
            self.assertTrue((Path(temp) / "b.mp4").exists())


if __name__ == "__main__":
    unittest.main()
