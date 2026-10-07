import unittest
from unittest.mock import patch

from api_server.main import _inspect_image_candidate_with_recovery
from api_server.services.openclaw_supervisor import SupervisorError


class MainVisionRecoveryTests(unittest.TestCase):
    @patch("api_server.main.time.sleep", return_value=None)
    @patch("api_server.main._write_supervisor_event")
    @patch("api_server.main.run_local_vision_recovery")
    @patch("api_server.main.inspect_image_candidate")
    def test_recovery_retry_success_keeps_automation_running(
        self,
        mock_inspect,
        mock_recovery,
        mock_write_event,
        _mock_sleep,
    ) -> None:
        mock_inspect.side_effect = [
            SupervisorError("CUDA out of memory"),
            SupervisorError("CUDA out of memory"),
            {"candidate_id": "cand-1", "passes": True, "score": 8},
        ]
        mock_recovery.return_value = {
            "eligible": True,
            "attempted": True,
            "contention_class": "ollama_resident_models",
            "cleanup_actions": [{"kind": "ollama_stop_model", "target": "gemma4:latest", "status": "succeeded"}],
            "retry_recommended": True,
            "snapshot_before": {"gpu": None, "ollama": None, "comfyui": None},
            "snapshot_after": {"gpu": None, "ollama": None, "comfyui": None},
        }

        inspection = _inspect_image_candidate_with_recovery(
            project_id="project-1",
            project={"id": "project-1"},
            job={"job_id": "job-1", "title": "Hero shot"},
            candidate={"candidate_id": "cand-1"},
            image_path="/tmp/example.png",
        )

        self.assertEqual(inspection["candidate_id"], "cand-1")
        event_kinds = [call.kwargs["kind"] for call in mock_write_event.call_args_list]
        self.assertIn("vision_resource_diagnosis", event_kinds)
        self.assertIn("vision_resource_cleanup", event_kinds)
        self.assertIn("vision_resource_retry", event_kinds)
        self.assertIn("vision_resource_retry_succeeded", event_kinds)

    @patch("api_server.main.time.sleep", return_value=None)
    @patch("api_server.main._write_supervisor_event")
    @patch("api_server.main.run_local_vision_recovery")
    @patch("api_server.main.inspect_image_candidate")
    def test_recovery_failure_raises_original_error(
        self,
        mock_inspect,
        mock_recovery,
        mock_write_event,
        _mock_sleep,
    ) -> None:
        mock_inspect.side_effect = [
            SupervisorError("CUDA out of memory"),
            SupervisorError("CUDA out of memory"),
        ]
        mock_recovery.return_value = {
            "eligible": False,
            "attempted": False,
            "contention_class": "skipped_non_resource_error",
            "cleanup_actions": [],
            "retry_recommended": False,
            "snapshot_before": {},
            "snapshot_after": None,
        }

        with self.assertRaises(SupervisorError):
            _inspect_image_candidate_with_recovery(
                project_id="project-1",
                project={"id": "project-1"},
                job={"job_id": "job-1", "title": "Hero shot"},
                candidate={"candidate_id": "cand-1"},
                image_path="/tmp/example.png",
            )

        event_kinds = [call.kwargs["kind"] for call in mock_write_event.call_args_list]
        self.assertNotIn("vision_resource_diagnosis", event_kinds)


if __name__ == "__main__":
    unittest.main()
