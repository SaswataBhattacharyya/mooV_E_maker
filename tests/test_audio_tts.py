from __future__ import annotations

import json
import unittest

from story_builder.services.audio_tts import TimedTTSError, WORKFLOW_PATH, build_workflow, comfy_voice_key, prepare_srt


def voice(voice_id: str, name: str, source: str = "user", relative_path: str | None = None) -> dict:
    return {
        "id": voice_id,
        "name": name,
        "source": source,
        "relative_path": relative_path or f"{name}.wav",
        "discoverable": True,
    }


class TimedTTSTests(unittest.TestCase):
    def setUp(self) -> None:
        self.voices = [
            voice("user:narrator.wav", "narrator"),
            voice("bundled:people/alice.wav", "alice", "bundled", "people/alice.wav"),
        ]
        self.characters = [
            {"name": "Narrator", "language": "en", "reference_voice_id": "user:narrator.wav"},
            {"name": "Alice", "language": "de", "reference_voice_id": "bundled:people/alice.wav"},
        ]

    def test_rewrites_character_to_selected_voice_and_default_language(self) -> None:
        rewritten, resolved = prepare_srt(
            "1\n00:00:00,000 --> 00:00:02,000\n[Alice] Hallo!\n",
            self.characters,
            self.voices,
        )
        self.assertIn("[German:alice]", rewritten)
        self.assertEqual(resolved["narrator"]["voice_key"], "narrator.wav")

    def test_explicit_language_wins(self) -> None:
        rewritten, _ = prepare_srt(
            "1\n00:00:00,000 --> 00:00:02,000\n[English:Alice] Hello!\n",
            self.characters,
            self.voices,
        )
        self.assertIn("[English:alice]", rewritten)

    def test_untagged_dialogue_requires_narrator(self) -> None:
        with self.assertRaisesRegex(TimedTTSError, "Narrator"):
            prepare_srt(
                "1\n00:00:00,000 --> 00:00:02,000\nHello!\n",
                self.characters[1:],
                self.voices,
            )

    def test_unknown_character_is_rejected(self) -> None:
        with self.assertRaisesRegex(TimedTTSError, "Bob"):
            prepare_srt(
                "1\n00:00:00,000 --> 00:00:02,000\n[Bob] Hello!\n",
                self.characters,
                self.voices,
            )

    def test_voice_keys_match_suite_discovery_prefixes(self) -> None:
        self.assertEqual(comfy_voice_key(self.voices[1]), "voices_examples/people/alice.wav")
        self.assertEqual(comfy_voice_key(voice("tts:x", "x", "tts-user", "x.wav")), "TTS/voices/x.wav")

    def test_builds_independent_fixed_workflow(self) -> None:
        before = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
        workflow = build_workflow(
            rewritten_srt="1\n00:00:00,000 --> 00:00:02,000\n[English:alice] Hello!\n",
            narrator={"voice_key": "narrator.wav"},
            settings={"language": "English", "seed": 42, "timing_mode": "concatenate"},
            filename_prefix="story_builder/project/job",
        )
        self.assertEqual(workflow["3"]["inputs"]["seed"], 42)
        self.assertEqual(workflow["4"]["inputs"]["filename_prefix"], "story_builder/project/job")
        self.assertEqual(workflow["4"]["inputs"]["format"], "flac")
        self.assertEqual(json.loads(WORKFLOW_PATH.read_text(encoding="utf-8")), before)


if __name__ == "__main__":
    unittest.main()
