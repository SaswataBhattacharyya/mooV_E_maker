from pathlib import Path

from video_audio_analyzer import demucs_adapter
from video_audio_analyzer.pipeline import _music_detected


def test_demucs_mode_names_are_normalized_and_use_expected_stems(tmp_path, monkeypatch):
    monkeypatch.setattr(demucs_adapter.importlib.util, "find_spec", lambda name: object())
    calls = []

    class Completed:
        stdout = "ok"

    def fake_run(command, **kwargs):
        calls.append(command)
        output = Path(command[command.index("-o") + 1])
        stem_dir = output / "htdemucs" / "source"
        stem_dir.mkdir(parents=True, exist_ok=True)
        (stem_dir / "vocals.wav").touch()
        return Completed()

    monkeypatch.setattr(demucs_adapter.subprocess, "run", fake_run)
    audio = tmp_path / "mix.wav"
    audio.touch()

    result = demucs_adapter.separate(audio, tmp_path / "two", "2-stem", False)
    assert result["status"] == "completed"
    assert "--two-stems" in calls[-1] and "vocals" in calls[-1]

    result = demucs_adapter.separate(audio, tmp_path / "four", "4-stem", False)
    assert result["status"] == "completed"
    assert "--two-stems" not in calls[-1]

    result = demucs_adapter.separate(audio, tmp_path / "auto", "AUTO", False, auto_voice_requested=True)
    assert result["status"] == "completed"
    assert "--two-stems" in calls[-1]


def test_demucs_auto_skips_when_no_requested_category(tmp_path, monkeypatch):
    result = demucs_adapter.separate(tmp_path / "mix.wav", tmp_path / "out", "AUTO", False)
    assert result["status"] == "not_requested"


def test_music_event_type_triggers_demucs_auto_even_without_literal_music_label():
    assert _music_detected([{"event_type": "music", "label": "Cello", "confidence": 0.71}]) is True
    assert _music_detected([{"event_type": "sfx_ambience", "label": "Music hall door", "confidence": 0.9}]) is False
    assert _music_detected([{"event_type": "music", "label": "Singing", "confidence": 0.24}]) is False
