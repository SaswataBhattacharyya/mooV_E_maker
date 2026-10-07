"""Measured music/audio features for the isolated analyzer.

This module deliberately reports measurements only. It does not turn BPM or
spectral values into asserted moods/genres; those are later semantic stages.
Imports are lazy so an optional music runtime cannot block frame analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def analyze_music(audio_path: Path, duration: float, enabled: bool = True) -> dict[str, Any]:
    """Return auditable, timestamped measurements from the analysis WAV."""
    result: dict[str, Any] = {
        "status": "disabled" if not enabled else "unavailable",
        "backend": "librosa",
        "segments": [],
        "measurements_only": True,
    }
    if not enabled:
        return result
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        if y.size == 0 or sr <= 0:
            result["reason"] = "empty audio"
            return result
        duration = max(float(duration), float(y.size / sr))
        hop_length = 512
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
        onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
        try:
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
            tempo_value = float(np.asarray(tempo).reshape(-1)[0]) if np.asarray(tempo).size else 0.0
            beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=hop_length).tolist()
        except Exception:
            tempo_value, beat_times = 0.0, []

        segments: list[dict[str, Any]] = []
        for start in np.arange(0.0, duration, 10.0):
            end = min(duration, float(start + 10.0))
            left = max(0, int(start * sr / hop_length))
            right = min(len(rms), max(left + 1, int(end * sr / hop_length)))
            onset_left = max(0, int(start * sr / hop_length))
            onset_right = min(len(onset), max(onset_left + 1, int(end * sr / hop_length)))
            if right <= left:
                continue
            segment_beats = [float(t) for t in beat_times if float(start) <= float(t) < end]
            values = {
                "rms_mean": float(np.mean(rms[left:right])),
                "rms_peak": float(np.max(rms[left:right])),
                "spectral_centroid_hz_mean": float(np.mean(centroid[left:right])),
                "onset_strength_mean": float(np.mean(onset[onset_left:onset_right])) if onset_right > onset_left else 0.0,
                "beat_count": len(segment_beats),
            }
            segments.append({
                "segment_id": f"music_segment_{len(segments)+1:04d}",
                "start_time_sec": round(float(start), 3),
                "end_time_sec": round(float(end), 3),
                "measurements": {key: round(float(value), 6) if isinstance(value, (float, np.floating)) else value for key, value in values.items()},
                "beat_times_sec": [round(value, 3) for value in segment_beats],
            })
        result.update({
            "status": "completed",
            "sample_rate": int(sr),
            "duration_sec": round(float(y.size / sr), 3),
            "global": {"tempo_bpm_estimate": round(tempo_value, 3), "beat_count": len(beat_times)},
            "segments": segments,
        })
    except Exception as exc:
        result["reason"] = str(exc)
    return result
