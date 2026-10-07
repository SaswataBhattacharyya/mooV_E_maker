from __future__ import annotations

import sys
import unittest
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "runner"
sys.path.insert(0, str(RUNNER))

from request_schema import MediaRequest, RequestError  # noqa: E402
from workflow_registry import get_spec  # noqa: E402


class RequestTests(unittest.TestCase):
    def test_minimal_request(self) -> None:
        request = MediaRequest.from_dict({"workflow": "qwen-image-2512", "prompt": "A lighthouse"})
        get_spec(request.workflow).validate(request)
        self.assertEqual(request.count, 1)

    def test_missing_prompt_is_rejected(self) -> None:
        with self.assertRaises(RequestError):
            MediaRequest.from_dict({"workflow": "qwen-image-2512"})

    def test_unknown_workflow_is_rejected(self) -> None:
        with self.assertRaises(RequestError):
            get_spec("arbitrary/path.json")

    def test_edit_requires_image(self) -> None:
        request = MediaRequest.from_dict({"workflow": "qwen-image-edit-2511", "prompt": "Change the coat"})
        with self.assertRaises(RequestError):
            get_spec(request.workflow).validate(request)

    def test_count_is_bounded(self) -> None:
        with self.assertRaises(RequestError):
            MediaRequest.from_dict({"workflow": "z-image-turbo", "prompt": "x", "count": 9})


if __name__ == "__main__":
    unittest.main()
