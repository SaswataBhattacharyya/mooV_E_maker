from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path

import pytest

from story_builder.services import production_dialogue_tts as dialogue
from story_builder.services.media_jobs import MediaJobError


def test_build_srt_preserves_exact_text_and_assigns_stable_speakers():
    lines = [
        {"character_id": "maya", "text": "Wait—listen.", "start_seconds": 0, "end_seconds": 2.1},
        {"character_id": "ari", "text": "I hear the rain.", "start_seconds": 2.2, "end_seconds": 5},
    ]
    srt = dialogue.build_srt(lines, {"maya": "1", "ari": "2"})
    assert "Speaker 1: Wait—listen." in srt
    assert "Speaker 2: I hear the rain." in srt
    assert "00:00:02,200 --> 00:00:05,000" in srt


@pytest.mark.parametrize("lines", [
    [{"character_id": "a", "text": "line\nSpeaker 2: injected", "start_seconds": 0, "end_seconds": 2}],
    [{"character_id": "a", "text": "line", "start_seconds": 3, "end_seconds": 2}],
    [{"character_id": "a", "text": "line", "start_seconds": 0, "end_seconds": 2},
     {"character_id": "b", "text": "overlap", "start_seconds": 1, "end_seconds": 3}],
])
def test_build_srt_rejects_srt_injection_or_invalid_intervals(lines):
    with pytest.raises(dialogue.ProductionDialogueTTSError):
        dialogue.build_srt(lines, {"a": "1", "b": "2"})


@pytest.mark.parametrize("speaker_count", [2, 3, 4])
def test_graph_uses_bound_audio_files_and_drops_unused_voice_inputs(speaker_count):
    voices = [{"filename": f"bound-{index}.wav"} for index in range(1, speaker_count + 1)]
    graph = dialogue.build_workflow(srt_content="exact words", voice_files=voices,
        seed=87, filename_prefix="story/dialogue/test")
    assert graph["2"]["inputs"]["opt_audio_input"] == ["5", 0]
    assert graph["1"]["inputs"]["speaker2_voice"] == ["6", 0]
    assert graph["3"]["inputs"]["srt_content"] == "exact words"
    assert graph["3"]["inputs"]["seed"] == 87
    assert graph["4"]["inputs"]["filename_prefix"] == "story/dialogue/test"
    assert [graph[str(4 + index)]["inputs"]["audio"] for index in range(1, speaker_count + 1)] == [
        row["filename"] for row in voices]
    for index in range(speaker_count + 1, 5):
        assert str(4 + index) not in graph


def test_workflow_rejects_single_voice_or_out_of_range_seed():
    with pytest.raises(dialogue.ProductionDialogueTTSError, match="2–4"):
        dialogue.build_workflow(srt_content="x", voice_files=[{"filename": "a.wav"}], seed=1, filename_prefix="x")
    with pytest.raises(dialogue.ProductionDialogueTTSError, match="seed"):
        dialogue.build_workflow(srt_content="x", voice_files=[{"filename": "a.wav"}, {"filename": "b.wav"}], seed=-1, filename_prefix="x")


def test_live_preflight_requires_local_model_and_native_multispeaker(monkeypatch):
    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self):
            if self.payload is not None:
                return json.dumps(self.payload).encode()
            schema = {"input": {"required": {
                "model": [["local:vibevoice-1.5B"]],
                "device": [["cpu", "cuda"]],
                "multi_speaker_mode": [["Native Multi-Speaker"]],
            }, "optional": {"speaker2_voice": ["*"]}}}
            classes = {}
            for node in graph.values():
                class_type = node["class_type"]
                inputs = node.get("inputs", {})
                classes[class_type] = {"input": {"required": {key: [] for key in inputs},
                    "optional": {}, "hidden": {}}}
            classes["VibeVoiceEngineNode"] = schema
            classes["VibeVoiceEngineNode"]["input"]["required"].update({
                key: [] for key in graph["1"]["inputs"]
                if key not in {"model", "device", "multi_speaker_mode",
                               "speaker2_voice", "speaker3_voice", "speaker4_voice"}})
            return json.dumps(classes).encode()

    graph = dialogue.build_workflow(srt_content="x", voice_files=[{"filename": "a.wav"}, {"filename": "b.wav"}],
        seed=1, filename_prefix="x")
    def fake_urlopen(url, **_kwargs):
        return Response(sorted(dialogue.MODEL_REQUIRED_FILES) if url.endswith("/models/TTS") else None)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    dialogue.validate_live_nodes("http://comfy.test", graph)


def test_live_preflight_rejects_missing_local_model_files(monkeypatch):
    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return json.dumps(self.payload).encode()
    graph = dialogue.build_workflow(srt_content="x", voice_files=[{"filename": "a.wav"}, {"filename": "b.wav"}],
        seed=1, filename_prefix="x")
    monkeypatch.setattr("urllib.request.urlopen", lambda url, **_kwargs:
        Response([]) if url.endswith("/models/TTS") else Response({}))
    with pytest.raises(dialogue.ProductionDialogueTTSError, match="no prompt was submitted"):
        dialogue.validate_live_nodes("http://comfy.test", graph)


def test_incomplete_local_model_fails_job_before_watchdog_or_prompt_submission(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dialogue, "stage_audio_reference", lambda source, **kwargs: type("Staged", (), {
        "filename": Path(source).name, "sha256": "b" * 64})())
    monkeypatch.setattr(dialogue, "validate_live_nodes", lambda *_args:
        (_ for _ in ()).throw(dialogue.ProductionDialogueTTSError("missing local model")))
    monkeypatch.setattr("story_builder.services.production_job_worker.ensure_prompt_watchdog",
        lambda **_kwargs: calls.append("watchdog"))
    monkeypatch.setattr(dialogue, "submit_and_wait", lambda *_args, **_kwargs: calls.append("submit"))
    monkeypatch.setattr(dialogue, "cleanup_staging", lambda **_kwargs: calls.append("cleanup"))
    job = {"job_id": "dialogue-no-model", "project_id": "film", "prompt_id": "reserved-prompt",
        "status": "queued", "seed": 42, "dialogue_lines": [
            {"character_id": "a", "text": "A.", "start_seconds": 0, "end_seconds": 2},
            {"character_id": "b", "text": "B.", "start_seconds": 2, "end_seconds": 4}]}
    changes = []
    dialogue.run_job(project_dir=tmp_path / "projects", output_root=tmp_path / "output",
        comfy_url="http://comfy.test", job=job,
        voice_sources=[{"character_id": "a", "speaker_id": "S1", "master_asset_id": "m1",
            "excerpt_asset_id": "e1", "excerpt_sha256": "a" * 64, "source_path": str(tmp_path / "a.wav")},
            {"character_id": "b", "speaker_id": "S2", "master_asset_id": "m2",
                "excerpt_asset_id": "e2", "excerpt_sha256": "c" * 64, "source_path": str(tmp_path / "b.wav")}],
        comfy_input_dir=tmp_path / "comfy" / "input", owner_root=tmp_path / "stage",
        update=lambda fields: changes.append(dict(fields)))
    assert changes[-1]["status"] == "failed"
    assert calls == ["cleanup"]


def test_runner_records_exact_prompt_and_marks_unknown_submission_for_recovery(tmp_path, monkeypatch):
    owner_cleanup = []
    monkeypatch.setattr(dialogue, "stage_audio_reference", lambda source, **kwargs: type("Staged", (), {
        "filename": Path(source).name, "sha256": "b" * 64})())
    monkeypatch.setattr(dialogue, "validate_live_nodes", lambda *_args: None)
    monkeypatch.setattr("story_builder.services.production_job_worker.ensure_prompt_watchdog",
        lambda **kwargs: owner_cleanup.append(("watchdog", kwargs["prompt_id"])))
    monkeypatch.setattr(dialogue, "submit_and_wait", lambda *_args, **kwargs: (_ for _ in ()).throw(
        MediaJobError("outcome unknown", prompt_id=kwargs["prompt_id"], remote_state_unknown=True)))
    monkeypatch.setattr(dialogue, "cleanup_staging", lambda **kwargs: owner_cleanup.append(("cleanup", kwargs["owner_id"])))
    monkeypatch.setattr(dialogue, "release_comfyui_models_if_idle", lambda **_kwargs: owner_cleanup.append(("release", None)))
    job = {"job_id": "dialogue-test", "project_id": "film", "prompt_id": "reserved-prompt",
        "status": "queued", "seed": 42, "dialogue_lines": [
            {"character_id": "a", "text": "A.", "start_seconds": 0, "end_seconds": 2},
            {"character_id": "b", "text": "B.", "start_seconds": 2, "end_seconds": 4}],
        "dialogue_speakers": []}
    changes = []
    dialogue.run_job(project_dir=tmp_path / "projects", output_root=tmp_path / "output",
        comfy_url="http://comfy.test", job=job,
        voice_sources=[{"character_id": "a", "speaker_id": "S1", "master_asset_id": "m1",
            "excerpt_asset_id": "e1", "excerpt_sha256": "a" * 64, "source_path": str(tmp_path / "a.wav")},
            {"character_id": "b", "speaker_id": "S2", "master_asset_id": "m2",
            "excerpt_asset_id": "e2", "excerpt_sha256": "c" * 64, "source_path": str(tmp_path / "b.wav")}],
        comfy_input_dir=tmp_path / "comfy" / "input", owner_root=tmp_path / "stage",
        update=lambda fields: (job.update(fields), changes.append(dict(fields))))
    assert job["status"] == "recovery_required", job
    assert job["prompt_id"] == "reserved-prompt"
    assert ("watchdog", "reserved-prompt") in owner_cleanup
    assert not any(row[0] == "cleanup" for row in owner_cleanup)
    assert not any(row[0] == "release" for row in owner_cleanup)


def test_admission_failure_before_post_does_not_become_ambiguous_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(dialogue, "stage_audio_reference", lambda source, **kwargs: type("Staged", (), {
        "filename": Path(source).name, "sha256": "b" * 64})())
    monkeypatch.setattr(dialogue, "validate_live_nodes", lambda *_args: None)
    monkeypatch.setattr("story_builder.services.production_job_worker.ensure_prompt_watchdog", lambda **_kwargs: None)
    monkeypatch.setattr(dialogue, "submit_and_wait", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        MediaJobError("admission blocked", remote_state_unknown=False)))
    cleaned = []
    changes = []
    monkeypatch.setattr(dialogue, "cleanup_staging", lambda **kwargs: cleaned.append(kwargs["owner_id"]))
    monkeypatch.setattr(dialogue, "release_comfyui_models_if_idle", lambda **_kwargs: cleaned.append("release"))
    job = {"job_id": "dialogue-test", "project_id": "film", "prompt_id": "reserved-prompt",
        "status": "queued", "seed": 1, "dialogue_lines": [
            {"character_id": "a", "text": "A.", "start_seconds": 0, "end_seconds": 2},
            {"character_id": "b", "text": "B.", "start_seconds": 2, "end_seconds": 4}]}
    dialogue.run_job(project_dir=tmp_path / "projects", output_root=tmp_path / "output",
        comfy_url="http://comfy.test", job=job,
        voice_sources=[{"character_id": "a", "speaker_id": "S1", "master_asset_id": "m1", "excerpt_asset_id": "e1", "excerpt_sha256": "a" * 64, "source_path": str(tmp_path / "a.wav")},
            {"character_id": "b", "speaker_id": "S2", "master_asset_id": "m2", "excerpt_asset_id": "e2", "excerpt_sha256": "c" * 64, "source_path": str(tmp_path / "b.wav")}],
        comfy_input_dir=tmp_path / "comfy" / "input", owner_root=tmp_path / "stage",
        update=lambda fields: changes.append(dict(fields)))
    assert job["status"] == "queued"  # The API persists updates in a separate object.
    assert changes[-1]["status"] == "failed"
    assert cleaned == ["dialogue-dialogue-test", "release"]


def test_known_completion_cleans_owned_voice_staging_when_updater_copies_job(tmp_path, monkeypatch):
    monkeypatch.setattr(dialogue, "stage_audio_reference", lambda source, **kwargs: type("Staged", (), {
        "filename": Path(source).name, "sha256": "b" * 64})())
    monkeypatch.setattr(dialogue, "validate_live_nodes", lambda *_args: None)
    monkeypatch.setattr("story_builder.services.production_job_worker.ensure_prompt_watchdog", lambda **_kwargs: None)
    monkeypatch.setattr(dialogue, "submit_and_wait", lambda *_args, **kwargs: (kwargs["prompt_id"], {kwargs["prompt_id"]: {}}))
    monkeypatch.setattr(dialogue, "collect_outputs", lambda *_args, **_kwargs: [{"kind": "audio", "filename": "speech.flac"}])
    cleaned = []
    changes = []
    monkeypatch.setattr(dialogue, "cleanup_staging", lambda **kwargs: cleaned.append(kwargs["owner_id"]))
    monkeypatch.setattr(dialogue, "release_comfyui_models_if_idle", lambda **_kwargs: cleaned.append("release"))
    job = {"job_id": "dialogue-success", "project_id": "film", "prompt_id": "reserved-prompt",
        "status": "queued", "seed": 42, "dialogue_lines": [
            {"character_id": "a", "text": "A.", "start_seconds": 0, "end_seconds": 2},
            {"character_id": "b", "text": "B.", "start_seconds": 2, "end_seconds": 4}]}
    dialogue.run_job(project_dir=tmp_path / "projects", output_root=tmp_path / "output",
        comfy_url="http://comfy.test", job=job,
        voice_sources=[{"character_id": "a", "speaker_id": "S1", "master_asset_id": "m1", "excerpt_asset_id": "e1", "excerpt_sha256": "a" * 64, "source_path": str(tmp_path / "a.wav")},
            {"character_id": "b", "speaker_id": "S2", "master_asset_id": "m2", "excerpt_asset_id": "e2", "excerpt_sha256": "c" * 64, "source_path": str(tmp_path / "b.wav")}],
        comfy_input_dir=tmp_path / "comfy" / "input", owner_root=tmp_path / "stage",
        update=lambda fields: changes.append(dict(fields)))
    assert changes[-1]["status"] == "completed", changes
    assert job["status"] == "queued"
    assert cleaned == ["dialogue-dialogue-success", "release"]
