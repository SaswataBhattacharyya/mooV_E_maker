from __future__ import annotations

import json
from pathlib import Path

from video_audio_analyzer.pipeline import AnalyzerOptions, analyze_video
from video_audio_analyzer.preflight import run_preflight
from video_audio_analyzer.repertoire import promote_run


FIXTURE = Path(__file__).resolve().parents[1].parent / "plan" / "Brother eww what’s that？💀 #meme.mp4"


def test_preflight_is_read_only_and_records_registry(tmp_path: Path) -> None:
    report = run_preflight(tmp_path)
    assert report["registry"]
    assert report["docker_boundary"].startswith("isolated")
    assert (tmp_path / "manifests" / "preflight.json").exists()


def test_dummy_video_produces_timeline_audio_and_frames(tmp_path: Path) -> None:
    if not FIXTURE.exists():
        raise AssertionError(f"fixture missing: {FIXTURE}")
    manifest = analyze_video(FIXTURE, tmp_path, AnalyzerOptions())
    run_dir = tmp_path / "runs" / manifest["source"]["video_id"]
    assert manifest["source"]["duration_sec"] > 0
    assert manifest["source"]["source_fps"] > 0
    assert manifest["scenes"]
    assert all(scene["frames"] for scene in manifest["scenes"])
    assert manifest["statuses"]["compact_frame_evidence"] == "completed"
    assert manifest["frame_evidence"]
    assert "measurements" in manifest["frame_evidence"][0]
    assert manifest["frame_evidence"][0]["confidence"]["semantic_objects"] == 0.0
    assert Path(manifest["audio"]["analysis_wav"]).exists()
    assert Path(manifest["audio"]["preview_mp3"]).exists()
    assert manifest["audio_events"]
    assert manifest["statuses"]["music_analysis"] in {"completed", "unavailable"}
    assert "music_features" in manifest
    assert manifest["transcript"]["status"] in {"completed", "unavailable"}
    assert manifest["transcript"].get("source") in {"embedded", None}
    assert manifest["statuses"]["demucs"] in {"completed", "unavailable", "not_requested", "disabled"}
    assert manifest["frame_shaving"]["sampling_fps"] == 4.0
    assert manifest["frame_shaving"]["intermediate_cleanup"] is True
    assert not (run_dir / "_decoded_frames").exists()
    repertoire = tmp_path / "video_repertoire"
    record = promote_run(run_dir, repertoire, "dummy-project")
    assert record["approved"] is True
    assert (repertoire / "manifests" / "analyzer-runs" / f"{run_dir.name}.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert json.loads((run_dir / "manifest.json").read_text()) ["statuses"]["sam_audio"].startswith("on_demand")
    assert manifest["media_collection"]["settings"] == {
        "collect_voice_examples": False, "collect_music_clips": False, "collect_sfx_clips": False}
    assert manifest["voices"]["status"] == "disabled"
    assert manifest["media_collection"]["assets"] == []


def test_repertoire_can_promote_only_opted_in_audio_assets(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / ("a" * 16)
    run_dir.mkdir(parents=True)
    clip = run_dir / "collected" / "music" / "music_001.wav"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"wav-fixture")
    frame = run_dir / "frame.jpg"
    frame.write_bytes(b"frame-fixture")
    (run_dir / "manifest.json").write_text(json.dumps({
        "source": {"video_id": "a" * 16},
        "scenes": [{"frames": [{"frame_id": "frame_1", "path": str(frame)}]}],
        "audio": {"analysis_wav": str(run_dir / "audio.wav")},
        "media_collection": {"assets": [{"asset_id": "music_001", "category": "music", "path": str(clip)}]},
    }), encoding="utf-8")
    repertoire = tmp_path / "video_repertoire"
    record = promote_run(run_dir, repertoire, "project-1", include_standard_media=False)
    assert record["collected_assets"]
    assert len(record["copied_assets"]) == 1
    assert (repertoire / "music" / "music_001" / "music_001.wav").is_file()
    assert not (repertoire / "frames").exists()
    assert not (repertoire / "audio").exists()


def test_in_place_analyzer_assets_are_indexed_without_duplicate_media_or_manifest_collision(tmp_path: Path) -> None:
    repertoire = tmp_path / "video_repertoire"
    run_dir = repertoire / "analyses" / "video_audio_analyzer" / ("b" * 16)
    clip = run_dir / "collected" / "voices" / "voice_001.wav"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"wav-fixture")
    source_manifest = repertoire / "manifests" / f"{'b' * 16}.json"
    source_manifest.parent.mkdir(parents=True)
    source_manifest.write_text(json.dumps({"asset_id": "video-b", "sha256": "original-video-metadata"}), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps({
        "source": {"video_id": "b" * 16},
        "media_collection": {"assets": [{"asset_id": "voice_001", "category": "voices", "path": str(clip)}]},
    }), encoding="utf-8")

    record = promote_run(run_dir, repertoire, "project-1", include_standard_media=False)

    assert record["copied_assets"] == []
    assert record["collected_assets"][0]["path"] == clip.relative_to(repertoire).as_posix()
    assert clip.is_file()
    assert not (repertoire / "voices" / "voice_001" / clip.name).exists()
    assert json.loads(source_manifest.read_text(encoding="utf-8"))["sha256"] == "original-video-metadata"
    assert (repertoire / "manifests" / "analyzer-runs" / f"{'b' * 16}.json").is_file()
