"""Optional WhisperX-compatible ASR adapter.

The worker never downloads a model during analysis. A prepared
`faster-whisper-large-v3` directory must be mounted and selected explicitly;
otherwise the manifest records an unavailable stage and preserves the audio
timeline. This keeps unattended runs deterministic and avoids hidden network
or shared-environment changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def transcribe(audio_path: Path) -> dict[str, Any]:
    model_dir = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_ASR_MODEL", "/models/faster-whisper-large-v3"))
    base: dict[str, Any] = {
        "status": "unavailable",
        "backend": "faster-whisper",
        "model": "Systran/faster-whisper-large-v3",
        "segments": [],
        "text": "",
        "word_timestamps": False,
    }
    if not model_dir.exists():
        base["reason"] = f"prepared ASR model not mounted: {model_dir}"
        return base
    try:
        from faster_whisper import WhisperModel

        device = os.environ.get("VIDEO_AUDIO_ANALYZER_ASR_DEVICE", "cuda")
        compute_type = os.environ.get("VIDEO_AUDIO_ANALYZER_ASR_COMPUTE_TYPE", "float16" if device == "cuda" else "int8")
        try:
            model = WhisperModel(str(model_dir), device=device, compute_type=compute_type)
        except Exception as first_error:
            if device != "cuda":
                raise
            # Some aarch64 wheels ship CTranslate2 without CUDA kernels even
            # when the host has a GPU. Keep ASR usable on CPU and record it.
            device, compute_type = "cpu", "int8"
            model = WhisperModel(str(model_dir), device=device, compute_type=compute_type)
        segments, info = model.transcribe(str(audio_path), word_timestamps=True, vad_filter=True)
        rows: list[dict[str, Any]] = []
        words: list[dict[str, Any]] = []
        for segment in segments:
            row = {"start_time_sec": round(float(segment.start), 3), "end_time_sec": round(float(segment.end), 3), "text": segment.text.strip()}
            if row["text"]:
                rows.append(row)
            for word in getattr(segment, "words", None) or []:
                words.append({"start_time_sec": round(float(word.start), 3), "end_time_sec": round(float(word.end), 3), "word": word.word})
        base.update({"status": "completed", "language": getattr(info, "language", "unknown"), "text": " ".join(row["text"] for row in rows), "segments": rows, "words": words, "word_timestamps": True, "device": device, "compute_type": compute_type})
    except Exception as exc:
        base["reason"] = str(exc)
    return base
