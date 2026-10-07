import unittest

from story_builder.services.audio_automation import new_pipeline, validate_pipeline


def valid_definition():
    return {"name": "test", "steps": [
        {"id": "tts", "operation": "timed_tts", "parameters": {"srt_content": "srt"}, "inputs": {}},
        {"id": "split", "operation": "split_audio", "parameters": {"edits": [{"start": 0, "end": 1, "text": "x"}]}, "inputs": {"source_audio": {"step": "tts", "output": "audio"}}},
        {"id": "emotion", "operation": "emotion", "parameters": {"transcript": "x", "emotion": "happy"}, "inputs": {"source_audio": {"step": "split", "output": "clips", "clip_index": 0}}},
        {"id": "stitch", "operation": "stitch_audio", "parameters": {"mode": "simple"}, "inputs": {"split": {"step": "split", "output": "split_job"}, "replacements": [{"step": "emotion", "output": "audio", "clip_index": 0}]}},
    ]}


class AudioAutomationTests(unittest.TestCase):
    def test_acceptance_pipeline_validates(self):
        self.assertEqual(validate_pipeline(valid_definition()), [])
        self.assertTrue(new_pipeline(valid_definition()).get("valid"))

    def test_forward_binding_rejected(self):
        data = valid_definition(); data["steps"][1]["inputs"]["source_audio"]["step"] = "emotion"
        self.assertTrue(any("earlier" in error for error in validate_pipeline(data)))

    def test_unknown_output_rejected(self):
        data = valid_definition(); data["steps"][2]["inputs"]["source_audio"]["output"] = "missing"
        self.assertTrue(any("unknown source output" in error for error in validate_pipeline(data)))


if __name__ == "__main__": unittest.main()
