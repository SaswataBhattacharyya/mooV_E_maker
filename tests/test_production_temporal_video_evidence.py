import hashlib
from pathlib import Path
import pytest
from PIL import Image
from story_builder.services.production_temporal_video_evidence import collect_temporal_speaker_evidence, TemporalEvidenceError


def fixtures(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"registered-native-media")
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        Image.new("RGB", (640, 360), "blue").save(command[-1])
    def vision(path, **kwargs):
        assert path.is_file()
        assert kwargs["cpu_only"] is True
        assert kwargs["inference_timeout_seconds"] == 180
        assert kwargs["max_visible_subjects"] == 12
        assert "no audio" in kwargs["review_requirements"]["inspection"]
        return {"analysis_valid": True, "frame_card": {"evidence_valid": True,
            "confidence": .8, "summary": "Left person turns and changes mouth pose."}}
    return video, sha, calls, runner, vision


def test_temporal_sampling_uses_ordered_exact_times_and_removes_only_own_temporary_files(tmp_path):
    video, sha, calls, runner, vision = fixtures(tmp_path)
    result = collect_temporal_speaker_evidence(video_path=video, expected_sha256=sha,
        duration_seconds=8, runner=runner, vision_review=vision)
    assert result["timestamps_seconds"] == [i / 2 for i in range(16)]
    assert [float(c[c.index("-ss") + 1]) for c in calls] == result["timestamps_seconds"]
    assert result["video_sha256"] == sha and result["frame_count"] == 16
    assert video.read_bytes() == b"registered-native-media"
    assert not Path(calls[0][-1]).exists()
    assert "exact lip sync" in result["limitations"]


@pytest.mark.parametrize("duration", [True, 0, float("nan"), float("inf"), 61])
def test_invalid_duration_does_not_extract_or_analyze(tmp_path, duration):
    video, sha, calls, runner, vision = fixtures(tmp_path)
    with pytest.raises(TemporalEvidenceError, match="duration"):
        collect_temporal_speaker_evidence(video_path=video, expected_sha256=sha,
            duration_seconds=duration, runner=runner, vision_review=vision)
    assert calls == []


def test_wrong_hash_fails_before_extraction(tmp_path):
    video, sha, calls, runner, vision = fixtures(tmp_path)
    with pytest.raises(TemporalEvidenceError, match="exact registered"):
        collect_temporal_speaker_evidence(video_path=video, expected_sha256="0" * 64,
            duration_seconds=8, runner=runner, vision_review=vision)
    assert calls == []


def test_changed_video_and_invalid_analysis_cannot_be_trusted(tmp_path):
    video, sha, calls, runner, vision = fixtures(tmp_path)
    def changing(path, **kwargs):
        answer = vision(path, **kwargs)
        video.write_bytes(b"changed")
        return answer
    with pytest.raises(TemporalEvidenceError, match="changed"):
        collect_temporal_speaker_evidence(video_path=video, expected_sha256=sha,
            duration_seconds=8, runner=runner, vision_review=changing)
    video.write_bytes(b"registered-native-media")
    with pytest.raises(TemporalEvidenceError, match="Trusted"):
        collect_temporal_speaker_evidence(video_path=video, expected_sha256=sha,
            duration_seconds=8, runner=runner, vision_review=lambda *a, **k: {})


@pytest.mark.parametrize("mutation", [None, "hash", "times", "confidence", "grid", "device"])
def test_director_replays_only_matching_temporal_evidence_without_reanalysis(tmp_path, mutation):
    import json, subprocess
    from story_builder.services.production_video_director import review_video_take
    video, sha, calls, runner, vision = fixtures(tmp_path)
    temporal = collect_temporal_speaker_evidence(video_path=video, expected_sha256=sha,
        duration_seconds=8, runner=runner, vision_review=vision)
    if mutation == "hash": temporal["video_sha256"] = "0" * 64
    if mutation == "times": temporal["timestamps_seconds"][1] = .75
    if mutation == "confidence": temporal["observations"]["confidence"] = True
    if mutation == "grid": temporal["grid_sha256"] = "invalid"
    if mutation == "device": temporal["device"] = "gpu"
    prior = {"video_sha256": sha, "evidence": [{"time_seconds": t, "summary": "Person in room"}
        for t in (1.2, 4., 6.8)], "native_audio": {"text": "Ready?", "segments": [],
        "dialogue_match": True}, "temporal_speaker_evidence": temporal}
    provider_calls = []
    def director(**kwargs):
        payload = json.loads(kwargs["prompt"])
        assert payload["temporal_speaker_evidence"] == temporal
        provider_calls.append(True)
        return {"action": "accept", "confidence": .9, "reason": "Saved matching observations pass",
            "criteria": [{"name": "speaker", "passed": True, "evidence": "Timed gesture supports assignment"}]}
    args = dict(video_path=video, take={"input_snapshot": {"validation_request": {"prompt": "<d>Ready?</d>"}}},
        run_config={"provider": "codex", "director_profile": {}}, prior_review=prior,
        runner=lambda *a, **k: subprocess.CompletedProcess([], 0, stdout="8.0"), director=director,
        temporal_review=lambda **k: pytest.fail("Do not repeat saved temporal analysis"),
        vision_review=lambda *a, **k: pytest.fail("Do not repeat saved scene analysis"),
        audio_review=lambda **k: pytest.fail("Do not repeat saved ASR"))
    if mutation is None:
        assert review_video_take(**args)["temporal_speaker_evidence"] == temporal
        assert provider_calls == [True]
    else:
        with pytest.raises(TemporalEvidenceError): review_video_take(**args)
        assert provider_calls == []
