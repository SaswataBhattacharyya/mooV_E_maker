import json
from pathlib import Path

from video_audio_analyzer import internvideo3_stage as stage


class FakeCaptioner:
    instances = []

    def __init__(self, sample_fps=1.0):
        self.calls = []
        self.instances.append(self)

    def summarize_video(self, video_path, prompt):
        self.calls.append(("video", str(video_path), prompt))
        return {"text": f"Visible action in {Path(video_path).name}.", "seconds": 0.1,
                "input_mode": "direct_video_path", "sample_fps": 1.0}

    def synthesize_text(self, prompt, max_new_tokens=400):
        self.calls.append(("text", prompt))
        if "Write the coherent overall summary" in prompt:
            text = "Two moments unfold in chronological order, linked by the supplied evidence."
        else:
            text = "This moment advances the action described in the overall context."
        return {"text": text, "seconds": 0.1, "input_mode": "text_context"}


def test_direct_video_drafts_then_whole_summary_then_one_refinement_per_clip(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    run = tmp_path / "run"
    run.mkdir()
    manifest_path = run / "manifest.json"
    manifest_path.write_text(json.dumps({
        "source": {"file_name": "source.mp4", "duration_sec": 4.0},
        "summary": "structural fallback",
        "transcript": {"source": "youtube", "language": "en", "segments": [
            {"start_time_sec": 0.4, "end_time_sec": 1.2, "text": "First line", "source": "youtube"},
            {"start_time_sec": 2.4, "end_time_sec": 3.1, "text": "Second line", "source": "youtube"},
        ]},
        "audio_events": [{"event_id": "evt-1", "start_time_sec": 2.0, "end_time_sec": 2.8,
            "label": "music", "event_type": "music", "confidence": 0.91}],
        "scenes": [
            {"scene_id": "scene_1", "start_time_sec": 0.0, "end_time_sec": 2.0},
            {"scene_id": "scene_2", "start_time_sec": 2.0, "end_time_sec": 4.0},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(stage, "InternVideo3Captioner", FakeCaptioner)
    monkeypatch.setattr(stage, "_cut", lambda source, target, start, end: target.write_bytes(b"clip"))
    FakeCaptioner.instances.clear()

    result = stage.summarize_manifest(manifest_path, source)

    calls = FakeCaptioner.instances[0].calls
    assert [call[0] for call in calls] == ["video", "video", "text", "text", "text"]
    assert all(call[2].find("directly") >= 0 for call in calls[:2])
    assert "First line" in calls[0][2]
    assert "music" in calls[1][2]
    assert result["sequence"] == ["direct_video_clip_drafts", "chronological_full_video_synthesis", "single_context_refinement_pass"]
    assert len(result["clips"]) == 2 and all(item["summary"] for item in result["clips"])
    assert result["direct_video_input"] is True
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated["summary"] == result["full_video_summary"]
    assert updated["scenes"][0]["summary_source"]["phase"] == "single_context_refinement"
    assert not list(run.glob("internvideo3-clips-*"))


def test_cleans_reasoning_tags_from_generated_text():
    assert stage.InternVideo3Captioner is not None
    from video_audio_analyzer.internvideo3_captioner import _clean_generated_text
    assert _clean_generated_text("<think>private reasoning</think>\nA concise visible summary.") == "A concise visible summary."
