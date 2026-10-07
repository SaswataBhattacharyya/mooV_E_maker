from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from story_builder.services import production_assets
from story_builder.services.production_voice_excerpt import VoiceExcerptError, create_h3_voice_excerpt


def test_voice_excerpt_is_explicit_timestamped_mono_wav_output_without_source_mutation(tmp_path, monkeypatch):
    storage, output = tmp_path / "storage", tmp_path / "output"
    project_id, run_id, character_id = "film", str(uuid.uuid4()), str(uuid.uuid4())
    source = storage / project_id / "inputs" / "master.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original voice bytes")
    source_before = source.read_bytes()
    source_asset = {"asset_id": "pa-0123456789abcdef", "kind": "audio", "roles": ["voice_master"],
        "sha256": "a" * 64, "media": {"duration_seconds": 40.0}}
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"derived")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(production_assets, "_probe_media", lambda *_a, **_k: {
        "duration_seconds": 6.0, "format": "wav", "streams": [{"codec_type": "audio", "sample_rate": "32000", "channels": 1}]})
    first = create_h3_voice_excerpt(storage_root=storage, output_root=output, project_id=project_id,
        run_id=run_id, character_id=character_id, source_asset=source_asset, source_path=source,
        start_sec=4.0, duration_seconds=6.0, run_process=fake_run,
        probe=lambda _path, _kind: {"duration_seconds": 6.0})
    second = create_h3_voice_excerpt(storage_root=storage, output_root=output, project_id=project_id,
        run_id=run_id, character_id=character_id, source_asset=source_asset, source_path=source,
        start_sec=4.0, duration_seconds=6.0, run_process=fake_run,
        probe=lambda _path, _kind: {"duration_seconds": 6.0})
    assert first["asset_id"] == second["asset_id"]
    assert first["metadata"]["source_voice_asset_id"] == source_asset["asset_id"]
    assert first["metadata"]["start_sec"] == 4.0
    assert first["metadata"]["sample_rate_hz"] == 32000
    assert source.read_bytes() == source_before
    assert len(commands) == 1
    assert "-ac" in commands[0] and commands[0][commands[0].index("-ac") + 1] == "1"


@pytest.mark.parametrize("start,duration,code", [(-1, 4, "excerpt_interval_invalid"),
    (0, 1, "excerpt_interval_invalid"), (30, 15, "excerpt_outside_source")])
def test_voice_excerpt_rejects_invalid_intervals_before_ffmpeg(tmp_path, start, duration, code):
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    with pytest.raises(VoiceExcerptError) as error:
        create_h3_voice_excerpt(storage_root=tmp_path / "storage", output_root=tmp_path / "output",
            project_id="film", run_id=str(uuid.uuid4()), character_id=str(uuid.uuid4()),
            source_asset={"asset_id": "pa-0123456789abcdef", "kind": "audio", "roles": ["voice_master"],
                "media": {"duration_seconds": 40.0}}, source_path=source,
            start_sec=start, duration_seconds=duration, run_process=lambda *_a, **_k: None)
    assert error.value.code == code


def test_voice_excerpt_rejects_non_voice_asset(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    with pytest.raises(VoiceExcerptError) as error:
        create_h3_voice_excerpt(storage_root=tmp_path / "storage", output_root=tmp_path / "output",
            project_id="film", run_id=str(uuid.uuid4()), character_id=str(uuid.uuid4()),
            source_asset={"asset_id": "pa-0123456789abcdef", "kind": "audio", "roles": ["music_candidate"],
                "media": {"duration_seconds": 40.0}}, source_path=source,
            start_sec=0, duration_seconds=4)
    assert error.value.code == "source_not_voice_master"
