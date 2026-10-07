from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from story_builder.services.minimax_h3_media import (
    H3MediaError,
    cleanup_owned_media,
    probe_media,
    sha256_file,
    stage_audio_reference,
    stage_image_reference,
    stage_video_reference,
)


def _make_fixture_video(path: Path, *, audio: bool = True, duration: int = 3) -> None:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30"]
    if audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    command += ["-t", str(duration), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        command += ["-c:a", "aac", "-shortest"]
    command += [str(path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except FileNotFoundError:
        pytest.skip("FFmpeg is unavailable in this test runtime")
    if completed.returncode:
        pytest.skip(f"FFmpeg fixture could not be created: {completed.stderr[-500:]}")


def test_probe_and_stage_video_to_24fps_with_same_interval_audio(tmp_path):
    source = tmp_path / "source.mp4"
    _make_fixture_video(source)
    original_hash = sha256_file(source)
    comfy_input = tmp_path / "comfy-input"
    owner_root = tmp_path / "owned-staging"

    staged = stage_video_reference(
        source,
        asset_id="action-01",
        owner_id="project-run-shot-attempt-1",
        comfy_input_dir=comfy_input,
        owner_root=owner_root,
        start_sec=0.25,
        end_sec=2.25,
        include_audio=True,
    )

    source_probe = probe_media(source)
    assert source_probe.frame_rate == pytest.approx(30.0)
    assert source_probe.has_audio is True
    assert staged.fps == 24
    assert staged.probe.frame_rate == pytest.approx(24.0)
    assert staged.probe.has_audio is True
    assert staged.duration_seconds == pytest.approx(2.0, abs=0.15)
    assert staged.filename in {path.name for path in comfy_input.iterdir()}
    assert sha256_file(source) == original_hash


def test_cleanup_removes_only_hash_matching_owned_files(tmp_path):
    source = tmp_path / "source.mp4"
    _make_fixture_video(source, audio=False)
    comfy_input = tmp_path / "comfy-input"
    owner_root = tmp_path / "owned-staging"
    staged = stage_video_reference(source, asset_id="action-01", owner_id="owned-run-1",
                                   comfy_input_dir=comfy_input, owner_root=owner_root,
                                   start_sec=0.0, end_sec=2.0, include_audio=False)
    unrelated = comfy_input / "other-user.mp4"
    unrelated.write_bytes(b"belongs to another job")

    result = cleanup_owned_media("owned-run-1", comfy_input_dir=comfy_input, owner_root=owner_root)

    assert result["removed"] == [staged.filename]
    assert not (comfy_input / staged.filename).exists()
    assert unrelated.read_bytes() == b"belongs to another job"


def test_cleanup_retains_modified_file_and_reports_hash_mismatch(tmp_path):
    source = tmp_path / "source.mp4"
    _make_fixture_video(source, audio=False)
    comfy_input = tmp_path / "comfy-input"
    owner_root = tmp_path / "owned-staging"
    staged = stage_video_reference(source, asset_id="action-01", owner_id="owned-run-2",
                                   comfy_input_dir=comfy_input, owner_root=owner_root,
                                   start_sec=0.0, end_sec=2.0, include_audio=False)
    staged_path = comfy_input / staged.filename
    staged_path.write_bytes(staged_path.read_bytes() + b"unexpected change")

    result = cleanup_owned_media("owned-run-2", comfy_input_dir=comfy_input, owner_root=owner_root)

    assert result["removed"] == []
    assert result["skipped"] == [{"filename": staged.filename, "reason": "hash_changed"}]
    assert staged_path.exists()


def test_paired_audio_missing_and_long_untrimmed_video_fail_before_staging(tmp_path):
    silent = tmp_path / "silent.mp4"
    _make_fixture_video(silent, audio=False)
    comfy_input = tmp_path / "comfy-input"
    owner_root = tmp_path / "owned-staging"
    with pytest.raises(H3MediaError) as error:
        stage_video_reference(silent, asset_id="action-01", owner_id="run-3",
                              comfy_input_dir=comfy_input, owner_root=owner_root,
                              start_sec=0.0, end_sec=2.0, include_audio=True)
    assert error.value.code == "paired_audio_missing"
    assert not comfy_input.exists()

    long_video = tmp_path / "long.mp4"
    _make_fixture_video(long_video, audio=False, duration=16)
    with pytest.raises(H3MediaError) as error:
        stage_video_reference(long_video, asset_id="action-02", owner_id="run-4",
                              comfy_input_dir=comfy_input, owner_root=owner_root,
                              include_audio=False)
    assert error.value.code == "video_interval_out_of_bounds"


def test_staging_rejects_interval_outside_source(tmp_path):
    source = tmp_path / "source.mp4"
    _make_fixture_video(source, audio=False)
    with pytest.raises(H3MediaError) as error:
        stage_video_reference(source, asset_id="action-01", owner_id="run-5",
                              comfy_input_dir=tmp_path / "comfy-input", owner_root=tmp_path / "owned-staging",
                              start_sec=1.0, end_sec=4.0)
    assert error.value.code == "video_interval_out_of_bounds"


def test_image_and_standalone_audio_stage_with_same_owner_manifest(tmp_path):
    image_source = Path("plan/image.png")
    if not image_source.is_file():
        pytest.skip("Project fixture image is unavailable")
    audio_source = tmp_path / "source-with-audio.mp4"
    _make_fixture_video(audio_source, audio=True)
    comfy_input = tmp_path / "comfy-input"
    owner_root = tmp_path / "owned-staging"

    image = stage_image_reference(image_source, asset_id="identity-01", owner_id="project-run-shot-1",
                                 comfy_input_dir=comfy_input, owner_root=owner_root)
    image_retry = stage_image_reference(image_source, asset_id="identity-01", owner_id="project-run-shot-1",
                                       comfy_input_dir=comfy_input, owner_root=owner_root)
    audio = stage_audio_reference(audio_source, asset_id="voice-01", owner_id="project-run-shot-1",
                                  comfy_input_dir=comfy_input, owner_root=owner_root,
                                  start_sec=0.25, end_sec=2.25)
    result = cleanup_owned_media("project-run-shot-1", comfy_input_dir=comfy_input, owner_root=owner_root)

    assert image.width and image.height
    assert image_retry.filename == image.filename
    assert image.media_type == "image"
    assert audio.duration_seconds == pytest.approx(2.0, abs=0.15)
    assert audio.media_type == "audio"
    assert set(result["removed"]) == {image.filename, audio.filename}
    assert not (comfy_input / image.filename).exists()
    assert not (comfy_input / audio.filename).exists()
