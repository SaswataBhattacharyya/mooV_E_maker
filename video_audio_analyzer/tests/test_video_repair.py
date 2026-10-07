from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_scene_summarizer.config.settings import load_settings
from video_scene_summarizer.models.qwen_vl import OllamaVisionAnalyzer, _encode_image, probe_ollama_model
from video_scene_summarizer.models.schemas import SceneBoundary
from video_scene_summarizer.processing.continuity import analyze_scene_transitions


ROOT = Path(__file__).resolve().parents[1]


def scene(number: int, text: str) -> SceneBoundary:
    return SceneBoundary(
        scene_id=f"scene_{number:04d}", scene_number=number,
        start_time_sec=float(number - 1), end_time_sec=float(number), duration_sec=1.0,
        start_time_hms=f"00:00:0{number - 1}", end_time_hms=f"00:00:0{number}",
        scene_story_text=text, scene_compiled_text=text, transcript_text=f"spoken {number}",
    )


class FakeGenerator:
    def __init__(self, responses: list[str]): self.responses = iter(responses)
    def generate(self, **_kwargs): return next(self.responses)


class VideoRepairTests(unittest.TestCase):
    def test_config_uses_one_direct_ollama_model(self):
        config = load_settings(ROOT)
        self.assertEqual(config.model_provider, "ollama")
        self.assertEqual(config.visual_model_path, "qwen3.6:35b")
        self.assertEqual(config.visual_model_path, config.text_model_path)
        self.assertEqual(config.text_model_path, config.structuring_model_path)
        self.assertEqual(config.ui_port, 3020)

    def test_image_encoding_keeps_every_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.jpg"; raw = bytes(range(256)) * 8; path.write_bytes(raw)
            self.assertEqual(base64.b64decode(_encode_image(str(path))), raw)

    def test_one_scene_requires_no_transition_calls(self):
        generator = FakeGenerator([])
        self.assertEqual(analyze_scene_transitions([scene(1, "A person works")], generator, True), [])

    def test_valid_transition_is_structured(self):
        raw = json.dumps({"persistent_entities": ["artisan"], "appearing_entities": ["loom"],
                          "disappearing_entities": [], "location_change": "none", "time_change": "continuous",
                          "visual_transition": "cut to a wider view", "activity_change": "thread preparation to weaving",
                          "narrative_connection": "the process advances", "transcript_connection": "the narration continues",
                          "evidence": ["artisan remains visible"], "confidence": "high", "uncertainty_notes": []})
        result = analyze_scene_transitions([scene(1, "An artisan prepares thread"), scene(2, "The artisan uses a loom")], FakeGenerator([raw]), True)
        self.assertEqual(len(result), 1); self.assertEqual(result[0].persistent_entities, ["artisan"]); self.assertEqual(result[0].confidence, "high")

    def test_invalid_transition_repairs_once(self):
        repaired = json.dumps({"confidence": "medium", "narrative_connection": "next step", "evidence": ["same material"]})
        result = analyze_scene_transitions([scene(1, "thread"), scene(2, "cloth")], FakeGenerator(["not json", repaired]), False)
        self.assertEqual(result[0].narrative_connection, "next step")

    def test_invalid_transition_after_repair_is_uncertain(self):
        result = analyze_scene_transitions([scene(1, "thread"), scene(2, "cloth")], FakeGenerator(["bad", "still bad"]), False)
        self.assertEqual(result[0].confidence, "unknown"); self.assertTrue(result[0].uncertainty_notes)

    @patch("video_scene_summarizer.models.qwen_vl._get_json")
    @patch("video_scene_summarizer.models.qwen_vl._post_json")
    def test_preflight_rejects_nonvision_model(self, post, get):
        get.return_value = {"models": [{"name": "qwen3.6:35b"}]}
        post.return_value = {"capabilities": ["completion"]}
        result = probe_ollama_model("http://ollama", "qwen3.6:35b")
        self.assertFalse(result["ready"]); self.assertIn("vision", str(result["error"]))

    def test_vision_errors_are_not_saved_as_placeholder_success(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.jpg"; frame.write_bytes(b"frame")
            analyzer = OllamaVisionAnalyzer("http://ollama", "qwen3.6:35b")
            with patch("video_scene_summarizer.models.qwen_vl._post_json", side_effect=TimeoutError()):
                with self.assertRaises(RuntimeError): analyzer.describe("describe", [str(frame)])

    @patch("video_scene_summarizer.models.qwen_vl._post_json")
    def test_vision_cpu_mode_sets_request_scoped_zero_gpu(self, post):
        post.return_value = {"message": {"content": "ok"}}
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.jpg"; frame.write_bytes(b"frame")
            analyzer = OllamaVisionAnalyzer("http://ollama", "qwen3.6:35b", num_gpu=0)
            self.assertEqual(analyzer.describe("describe", [str(frame)]), "ok")
        payload = post.call_args.args[1]
        self.assertEqual(payload["options"]["num_gpu"], 0)

    @patch("video_scene_summarizer.processing.frame_detail.DominantColorProvider")
    def test_cpu_only_support_signals_skip_optional_model_providers(self, color_provider):
        from video_scene_summarizer.processing.frame_detail import collect_support_signals
        color_provider.return_value.analyze.return_value.data = {"dominant_colors": [{"name": "blue"}]}
        signals, warnings = collect_support_signals(Path("frame.png"), cpu_only=True)
        self.assertEqual(signals["dominant_colors"][0]["name"], "blue")
        self.assertEqual(warnings, [])
        color_provider.return_value.analyze.assert_called_once()


if __name__ == "__main__": unittest.main()
