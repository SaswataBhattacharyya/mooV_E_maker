from __future__ import annotations

import logging
from pathlib import Path

import whisper

from video_scene_summarizer.models.schemas import TranscriptResult, TranscriptSegment


LOGGER = logging.getLogger(__name__)


def load_whisper_model(model_name: str):
    LOGGER.info("Loading Whisper model %s", model_name)
    return whisper.load_model(model_name)


def transcribe_audio(audio_path: Path, model) -> TranscriptResult:
    result = model.transcribe(str(audio_path), task="transcribe", verbose=False)
    language = result.get("language", "unknown")
    segments = [
        TranscriptSegment(
            start=float(segment.get("start", 0.0)),
            end=float(segment.get("end", 0.0)),
            text=(segment.get("text") or "").strip(),
        )
        for segment in result.get("segments", [])
    ]
    return TranscriptResult(
        language=language,
        text=(result.get("text") or "").strip(),
        segments=segments,
    )
