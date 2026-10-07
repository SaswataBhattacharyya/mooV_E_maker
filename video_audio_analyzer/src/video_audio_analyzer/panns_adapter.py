"""Lazy PANNs sound-event detector for the isolated audio worker."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class PANNsUnavailable(RuntimeError):
    pass


class PANNsDetector:
    def __init__(self, checkpoint_path: str | Path, device: str | None = None):
        self.checkpoint_path = Path(checkpoint_path)
        if not self.checkpoint_path.exists() or self.checkpoint_path.stat().st_size < 300_000_000:
            raise PANNsUnavailable(f"PANNs checkpoint is missing/incomplete: {self.checkpoint_path}")
        try:
            import numpy as np
            import torch
            from panns_inference import SoundEventDetection, labels
        except Exception as exc:  # pragma: no cover - isolated worker dependency
            raise PANNsUnavailable(f"PANNs import failed: {exc}") from exc
        self.np = np
        self.torch = torch
        self.labels = labels
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SoundEventDetection(checkpoint_path=str(self.checkpoint_path), device=self.device)

    def detect(self, wav_path: str | Path, threshold: float = 0.35, window_sec: float = 2.0,
               detect_speech: bool = True, detect_music: bool = True, detect_sfx: bool = True) -> list[dict[str, Any]]:
        import librosa
        audio, _ = librosa.load(str(wav_path), sr=32000, mono=True)
        framewise = self.model.inference(audio[None, :])
        scores = framewise[0] if framewise.ndim == 3 else framewise
        events: list[dict[str, Any]] = []
        frame_count = max(1, scores.shape[0])
        duration = len(audio) / 32000.0
        hop_sec = duration / frame_count
        for frame_index, row in enumerate(scores):
            ranked = self.np.argsort(row)[::-1][:3]
            for class_index in ranked:
                confidence = float(row[class_index])
                if confidence < threshold:
                    continue
                start = frame_index / frame_count * duration
                label = self.labels[int(class_index)] if int(class_index) < len(self.labels) else f"class_{class_index}"
                normalized = str(label).lower()
                speech = any(key in normalized for key in ("speech", "conversation", "narration", "shout", "singing"))
                music = "music" in normalized or "musical instrument" in normalized
                enabled = (detect_speech if speech else False) or (detect_music if music else False) or (detect_sfx if not speech and not music else False)
                if enabled:
                    events.append({"event_id": f"panns_{len(events)+1:05d}", "start_time_sec": round(float(start), 3), "end_time_sec": round(float(start + hop_sec), 3), "label": str(label), "confidence": round(confidence, 6), "detector": "PANNs", "model": "Cnn14_DecisionLevelMax", "event_type": "speech" if speech else "music" if music else "sfx_ambience"})
        # Merge adjacent detections per class into compact timestamped events.
        events.sort(key=lambda event: (event["label"], event["start_time_sec"]))
        merged: list[dict[str, Any]] = []
        for event in events:
            previous = merged[-1] if merged else None
            if previous and previous["label"] == event["label"] and event["start_time_sec"] <= previous["end_time_sec"] + hop_sec * 1.6:
                previous["end_time_sec"] = event["end_time_sec"]
                previous["confidence"] = max(previous["confidence"], event["confidence"])
            else:
                merged.append(dict(event))
        for index, event in enumerate(merged, start=1):
            event["event_id"] = f"panns_{index:05d}"
            event["start_time_sec"] = round(event["start_time_sec"], 3)
            event["end_time_sec"] = round(min(duration, event["end_time_sec"]), 3)
        return merged


def configured_detector() -> PANNsDetector:
    path = os.environ.get("VIDEO_AUDIO_ANALYZER_PANNS_CHECKPOINT")
    if not path:
        raise PANNsUnavailable("VIDEO_AUDIO_ANALYZER_PANNS_CHECKPOINT is not set")
    return PANNsDetector(path)
