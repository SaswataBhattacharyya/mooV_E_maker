import unittest
from unittest.mock import patch

from api_server.services.local_vision_recovery import (
    classify_resource_contention,
    is_resource_exhaustion_error,
    run_local_vision_recovery,
)


class LocalVisionRecoveryTests(unittest.TestCase):
    def test_resource_exhaustion_classifier_matches_gpu_errors(self) -> None:
        self.assertTrue(is_resource_exhaustion_error("CUDA out of memory while loading the model"))
        self.assertTrue(is_resource_exhaustion_error("Vision model failed to load because VRAM is full"))
        self.assertFalse(is_resource_exhaustion_error("Could not reach native OpenClaw Gateway"))

    def test_contention_classifier_detects_mixed_case(self) -> None:
        snapshot = {
            "ollama": {
                "running_models": [
                    {"name": "qwen2.5vl:7b"},
                    {"name": "gemma4:latest"},
                ]
            },
            "gpu": {"available": True, "processes": [{"process_name": "python", "args": "ComfyUI main.py"}]},
            "processes": {"processes": [{"command": "python", "args": "ComfyUI"}]},
        }
        self.assertEqual(
            classify_resource_contention(snapshot, {"qwen2.5vl:7b"}),
            "mixed_contention",
        )

    @patch("api_server.services.local_vision_recovery.time.sleep", return_value=None)
    @patch("api_server.services.local_vision_recovery.request_memory_release")
    @patch("api_server.services.local_vision_recovery.stop_model")
    @patch("api_server.services.local_vision_recovery.collect_resource_snapshot")
    @patch("api_server.services.local_vision_recovery.gateway_runtime_summary")
    def test_recovery_stops_non_vision_models(
        self,
        mock_gateway,
        mock_snapshot,
        mock_stop_model,
        mock_request_memory_release,
        _mock_sleep,
    ) -> None:
        mock_gateway.return_value = {"is_local": True, "provider_mode": "local"}
        mock_snapshot.side_effect = [
            {
                "ollama": {
                    "running_models": [
                        {"name": "qwen2.5vl:7b"},
                        {"name": "gemma4:latest"},
                        {"name": "qwen2.5-coder:14b"},
                    ]
                },
                "gpu": {"available": True, "memory": {"used_mb": 22000, "total_mb": 24000}, "processes": []},
                "processes": {"processes": []},
                "comfyui": {"reachable": True},
            },
            {
                "ollama": {"running_models": [{"name": "qwen2.5vl:7b"}]},
                "gpu": {"available": True, "memory": {"used_mb": 12000, "total_mb": 24000}, "processes": []},
                "processes": {"processes": []},
                "comfyui": {"reachable": True},
            },
        ]
        mock_request_memory_release.return_value = {
            "kind": "comfyui_memory_release",
            "status": "skipped",
            "endpoint": None,
        }

        result = run_local_vision_recovery(
            error_text="CUDA out of memory while loading the vision model",
            vision_model="qwen2.5vl:7b",
            reasoning_model="gemma4:latest",
            coder_model="qwen2.5-coder:14b",
        )

        self.assertTrue(result["eligible"])
        self.assertTrue(result["attempted"])
        self.assertTrue(result["retry_recommended"])
        self.assertEqual(mock_stop_model.call_count, 2)
        self.assertEqual(mock_stop_model.call_args_list[0].args[0], "gemma4:latest")
        self.assertEqual(mock_stop_model.call_args_list[1].args[0], "qwen2.5-coder:14b")


if __name__ == "__main__":
    unittest.main()
