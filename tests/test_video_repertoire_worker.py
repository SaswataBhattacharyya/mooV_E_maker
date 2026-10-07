from __future__ import annotations

from pathlib import Path
import sys
import types
import pytest

from story_builder.services.video_repertoire_worker import _analyzer_visual_scenes


def test_cancel_requested_job_cannot_be_overwritten_by_worker_progress(tmp_path, monkeypatch):
    from story_builder.services import video_repertoire as store
    from story_builder.services import video_repertoire_worker as worker

    monkeypatch.setattr(store, "REPERTOIRE_ROOT", tmp_path / "repertoire")
    job = store.create_job("analysis", {"asset_ids": []})
    job.update(status="cancel_requested", stage="cancelling")
    store._atomic_json(store.job_path("analysis", job["job_id"]), job)

    worker.save_job("analysis", job["job_id"], status="failed", message="container stopped")
    with pytest.raises(KeyboardInterrupt, match="cancelled"):
        worker.event("analysis", job["job_id"], "analysis", "running", "still working", 50)

    current = store.read_job("analysis", job["job_id"])
    assert current["status"] == "cancel_requested"


def test_analyzer_visual_result_contains_run_relative_images_and_no_host_paths(tmp_path):
    run_id = "0123456789abcdef"
    run_dir = tmp_path / run_id
    frame = run_dir / "scenes" / "scene_0001" / "frame_0001.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"jpeg fixture")
    clip = run_dir / "embeddings" / "scene_0001.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"mp4 fixture")
    manifest = {"run_id": run_id, "scenes": [{
        "scene_id": "scene_0001", "start_time_sec": 0, "end_time_sec": 2,
        "frames": [{
            "frame_id": "frame_0001", "timestamp_sec": 0.5,
            "path": f"/app/runs/{run_id}/scenes/scene_0001/frame_0001.jpg",
            "evidence": {"camera": {"framing": "medium"}, "uncertainties": ["No semantic model"]},
        }, {
            "frame_id": "escape", "timestamp_sec": 1,
            "path": f"/app/runs/{run_id}/../../outside.jpg", "camera_motion_score": 0.2, "evidence": {},
        }],
    }]}

    result = _analyzer_visual_scenes(manifest, run_dir)
    assert result[0]["clip_artifact_path"] == "embeddings/scene_0001.mp4"
    assert len(result[0]["frames"]) == 2
    assert result[0]["frames"][0]["artifact_path"] == "scenes/scene_0001/frame_0001.jpg"
    assert result[0]["frames"][0]["camera"]["framing"] == "medium"
    assert result[0]["frames"][1]["artifact_path"] is None
    assert result[0]["frames"][1]["camera_motion_score"] == 0.2
    assert str(run_dir) not in str(result)


def test_website_worker_uses_direct_analyzer_as_primary_and_shapes_clip_results(tmp_path, monkeypatch):
    import hashlib
    import json
    from contextlib import contextmanager
    from types import SimpleNamespace
    from story_builder.services import video_repertoire as store
    from story_builder.services import video_repertoire_worker as worker

    project = tmp_path / "project"
    analyzer = project / "video_audio_analyzer"
    analyzer.mkdir(parents=True)
    (analyzer / "run_peav_worker.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    source = project / "video_repertoire" / "uploads" / "fixture.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video-fixture")
    jobs_root = project / "video_repertoire" / "jobs" / "analysis" / "analysis-fixture"
    jobs_root.mkdir(parents=True)
    run_id = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    run_root = project / "video_repertoire" / "analyses" / "video_audio_analyzer" / run_id
    run_root.mkdir(parents=True)
    (run_root / "embeddings").mkdir()
    (run_root / "embeddings" / "scene_0001.mp4").write_bytes(b"clip")
    manifest = {"run_id": run_id, "source": {"file_name": "fixture.mp4"}, "summary": "a direct video summary",
        "internvideo3": {"model": "InternVideo3", "full_video_summary": "a direct video summary"},
        "statuses": {}, "scenes": [{"scene_id": "scene_0001", "start_time_sec": 0, "end_time_sec": 2,
            "summary": "a person gestures", "frames": []}], "audio_events": [], "transcript": {"segments": []}}
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(store, "PROJECT_ROOT", project)
    monkeypatch.setattr(store, "REPERTOIRE_ROOT", project / "video_repertoire")
    monkeypatch.setattr(store, "LEGACY_VIDEO_ROOT", project / "video_summariser" / "out_videos")
    monkeypatch.setattr(store, "VIDEO_SUMMARISER_ROOT", analyzer)
    monkeypatch.setattr(store, "get_asset", lambda _asset_id: {"asset_id": "video-fixture", "path": str(source)})
    monkeypatch.setattr(store, "job_path", lambda _kind, _job_id: jobs_root / "job.json")
    monkeypatch.setattr(store, "sha256_file", lambda _path: run_id + "0" * 48)
    monkeypatch.setattr(worker, "event", lambda *_args, **_kwargs: None)
    gpu_lease = {"acquired": False}

    @contextmanager
    def acquire_gpu_lease(*, comfy_url):
        assert comfy_url == "http://127.0.0.1:3008"
        gpu_lease["acquired"] = True
        yield

    monkeypatch.setattr(worker, "gpu_workload_guard", acquire_gpu_lease)
    monkeypatch.setattr(worker.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(worker, "_analyzer_visual_scenes", lambda *_args: [])
    monkeypatch.setattr("video_audio_analyzer.codex_director_review.apply_director_overlay", lambda manifest, *_args: manifest)
    monkeypatch.setattr("video_audio_analyzer.repertoire.promote_run", lambda *_args, **_kwargs: {"status": "completed"})

    result = worker.run_analysis("analysis-fixture", {"asset_ids": ["video-fixture"], "settings": {}})

    assert result["primary_backend"] == "video_audio_analyzer"
    assert result["videos"][0]["summary"]["detailed_video_summary"] == "a direct video summary"
    assert result["videos"][0]["scenes"][0]["summary"] == "a person gestures"
    assert result["videos"][0]["scenes"][0]["clip_path"].endswith("embeddings/scene_0001.mp4")
    assert gpu_lease["acquired"] is True
