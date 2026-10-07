from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

import soundfile

from story_builder.services.audio_scene import SceneJobError, new_scene_job, run_split, run_stitch, safe_project_path, validate_edits


def make_wav(path: Path, seconds: float = 1.0, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, rate, int(seconds * rate), "NONE", "not compressed"))
        output.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(seconds * rate))))


class SceneAudioTests(unittest.TestCase):
    def test_validation_rejects_overlap_and_paths(self) -> None:
        with self.assertRaisesRegex(SceneJobError, "overlap"):
            validate_edits([{"start": 0, "end": 0.7}, {"start": 0.6, "end": 0.9}])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SceneJobError): safe_project_path(Path(directory), "../outside.wav")

    def test_split_and_stitch_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"; project.mkdir()
            source = project / "source.wav"; make_wav(source, 1.0)
            split_job = new_scene_job("split"); current = dict(split_job)
            run_split(job=current, project_dir=project, source=source, edits=validate_edits([{"start": .25, "end": .75, "text": "middle"}]), transcript=None, update=lambda changes: current.update(changes))
            self.assertEqual(current["status"], "completed")
            self.assertEqual([clip["kind"] for clip in current["manifest"]["clips"]], ["untouched", "edited_target", "untouched"])
            stitch = new_scene_job("stitch"); stitched = dict(stitch)
            run_stitch(job=stitched, project_dir=project, split_job=current, replacements={}, gaps={}, mode="simple", output_root=Path(directory) / "output", update=lambda changes: stitched.update(changes))
            self.assertEqual(stitched["status"], "completed")
            info = soundfile.info(str(project / stitched["output_path"]))
            self.assertAlmostEqual(info.frames / info.samplerate, 1.0, places=3)

    def test_timed_stitch_adds_gap_and_replacement_wins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"; project.mkdir(); source = project / "source.wav"; make_wav(source, 1.0)
            split_job = new_scene_job("split"); current = dict(split_job)
            run_split(job=current, project_dir=project, source=source, edits=validate_edits([{"start": .5, "end": .75}]), transcript=None, update=lambda changes: current.update(changes))
            replacement = project / "replacement.wav"; make_wav(replacement, .1)
            stitched = new_scene_job("stitch"); result = dict(stitched)
            run_stitch(job=result, project_dir=project, split_job=current, replacements={2: replacement}, gaps={1: .2}, mode="timed", output_root=Path(directory) / "output", update=lambda changes: result.update(changes))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["provenance"][1]["selected"], "replacement")
            self.assertAlmostEqual(result["result"]["inserted_silence_seconds"], .2)


if __name__ == "__main__": unittest.main()
