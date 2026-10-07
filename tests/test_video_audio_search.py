from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from story_builder.services import video_audio_search


def test_search_exposes_safe_run_relative_artifacts_without_vectors(monkeypatch, tmp_path):
    run_id = "0123456789abcdef"
    run = tmp_path / run_id
    artifact = run / "scenes" / "scene_0001" / "frame_0001.jpg"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"image")
    (run / "manifest.json").write_text(json.dumps({"scenes": [{"scene_id": "scene_0001", "cuts": [
        {"cut_id": "scene_0001_cut_0001", "parent_scene_id": "scene_0001", "start_time_sec": 1.0,
         "end_time_sec": 2.5, "duration_sec": 1.5, "boundary_method": "motion_compensated_sampled_frame_difference",
         "boundary_confidence": "estimated"}
    ]}]}), encoding="utf-8")
    monkeypatch.setattr(video_audio_search, "RUNS_ROOT", tmp_path)
    monkeypatch.setattr(video_audio_search, "_asset_id", lambda _video_id: "video-test")

    src = str(video_audio_search.ANALYZER_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from video_audio_analyzer import retrieval

    monkeypatch.setattr(retrieval, "search_all", lambda *_args, **_kwargs: {
        "query": "rain", "mode": "keyword", "results": [{
            "record_id": "scene_0001", "result_id": f"{run_id}:scene_0001", "run_id": run_id,
            "video_id": "video-hash", "source_video_id": "video-hash", "source_file": "source.mp4",
            "kind": "scene_clip", "scene_id": "scene_0001", "start_time_sec": 1.0,
            "end_time_sec": 4.0, "text": "rain", "score": 0.9,
            "source_path": f"/app/runs/{run_id}/scenes/scene_0001/frame_0001.jpg",
            "pe_av_vector": [0.1, 0.2], "clap_vector": [0.3],
        }], "total_candidates": 1, "next_offset": None,
    })

    result = video_audio_search.search(query="rain", mode="keyword")
    row = result["results"][0]
    assert row["artifact_path"] == "scenes/scene_0001/frame_0001.jpg"
    assert row["asset_id"] == "video-test"
    assert row["cuts"][0]["cut_id"] == "scene_0001_cut_0001"
    assert "source_path" not in row
    assert "pe_av_vector" not in row and "clap_vector" not in row


def test_artifact_path_rejects_traversal_and_untrusted_container_path(tmp_path, monkeypatch):
    monkeypatch.setattr(video_audio_search, "RUNS_ROOT", tmp_path)
    run_id = "0123456789abcdef"
    run = tmp_path / run_id
    run.mkdir()
    assert video_audio_search._artifact_path(run_id, f"/app/runs/{run_id}/../../secret") is None
    assert video_audio_search._artifact_path(run_id, "/tmp/secret") is None


def test_search_rejects_empty_and_invalid_mode():
    with pytest.raises(ValueError, match="search description"):
        video_audio_search.search(query="  ")
    with pytest.raises(ValueError, match="Search mode"):
        video_audio_search.search(query="rain", mode="magic")
