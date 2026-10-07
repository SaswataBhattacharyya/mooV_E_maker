from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _confidence(value: float, threshold: float = 0.0) -> float:
    return round(float(max(0.0, min(1.0, value - threshold))), 3)


def analyze_frame(frame_path: Path, frame_id: str, timestamp_sec: float) -> dict[str, Any]:
    """Produce compact measurable evidence, never a hallucinated narrative."""
    frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if frame is None:
        return {
            "frame_id": frame_id,
            "timestamp_sec": timestamp_sec,
            "status": "error",
            "error": "frame could not be decoded",
            "warnings": ["No visual evidence was produced."],
        }
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    brightness = float(gray.mean() / 255.0)
    contrast = float(gray.std() / 128.0)
    saturation = float(hsv[:, :, 1].mean() / 255.0)
    edge_density = float((cv2.Canny(gray, 80, 160) > 0).mean())
    # Quantized color evidence is intentionally small and reproducible.
    quantized = (frame.reshape(-1, 3).astype(np.float32) // 32) * 32 + 16
    colors, counts = np.unique(quantized.astype(np.uint8), axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:5]
    dominant_colors = [
        {"rgb": [int(color[2]), int(color[1]), int(color[0])], "fraction": round(float(counts[index] / len(quantized)), 3)}
        for index, color in ((int(item), colors[int(item)]) for item in order)
    ]
    evidence: dict[str, Any] = {
        "frame_id": frame_id,
        "timestamp_sec": round(float(timestamp_sec), 3),
        "status": "completed",
        "dimensions": {"width": width, "height": height},
        "measurements": {
            "brightness": round(brightness, 4),
            "contrast": round(contrast, 4),
            "saturation": round(saturation, 4),
            "edge_density": round(edge_density, 4),
            "orientation": "portrait" if height > width else "landscape" if width > height else "square",
        },
        "dominant_colors": dominant_colors,
        "regions": {"full_frame": {"x": 0, "y": 0, "width": width, "height": height}},
        "objects": [],
        "subjects": [],
        "actions_visible": [],
        "camera": {"framing": "unclassified", "motion": "unclassified"},
        "lighting": {"brightness_level": "dark" if brightness < 0.3 else "bright" if brightness > 0.7 else "mid", "contrast_level": "high" if contrast > 0.55 else "low" if contrast < 0.2 else "mid"},
        "ocr": {"status": "unavailable", "text": "", "engine": None},
        "depth": {"status": "not_requested"},
        "continuity_facts": [],
        "uncertainties": ["No object, subject, action, camera, or text claim is made without a specialist model."],
        "confidence": {
            "decode": 1.0,
            "measurements": 1.0,
            "dominant_colors": 1.0,
            "semantic_objects": 0.0,
        },
        "model_evidence": {"compact_extractor": "video_audio_analyzer.evidence/0.1.0", "doctr_available": importlib.util.find_spec("doctr") is not None, "yolo_available": importlib.util.find_spec("ultralytics") is not None},
        "warnings": [],
    }
    if evidence["model_evidence"]["doctr_available"]:
        evidence["ocr"]["status"] = "available_not_run_compact_mode"
    if evidence["model_evidence"]["yolo_available"]:
        evidence["model_evidence"]["yolo_note"] = "detector available but not run in compact baseline"
    return evidence
