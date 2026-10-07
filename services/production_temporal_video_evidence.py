"""CPU-only, hash-bound timed-frame evidence; no acceptance or render authority."""
from __future__ import annotations

import hashlib
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw
from story_builder.services.image_detailer import analyze_image


class TemporalEvidenceError(ValueError):
    pass


def collect_temporal_speaker_evidence(*, video_path: Path, expected_sha256: str,
        duration_seconds: float, vision_review: Callable[..., dict[str, Any]] = analyze_image,
        runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    """Inspect sixteen ordered native frames; never infer exact lip sync from a grid."""
    path = Path(video_path).resolve()
    if (isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float))
            or not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 60):
        raise TemporalEvidenceError("Video duration must be finite and within the review bound.")
    def digest() -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_file() or not path.stat().st_size or digest() != expected_sha256:
        raise TemporalEvidenceError("Temporal evidence requires the exact registered video bytes.")
    times = [round(duration_seconds * i / 16, 6) for i in range(16)]
    with tempfile.TemporaryDirectory(prefix="story-builder-temporal-evidence-") as tmp:
        grid = Image.new("RGB", (640 * 4, 384 * 4), "black")
        draw = ImageDraw.Draw(grid)
        for index, timestamp in enumerate(times):
            frame = Path(tmp) / f"frame-{index:02d}.png"
            runner(["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(path),
                "-frames:v", "1", "-vf", "scale=640:-2", "-y", str(frame)],
                check=True, capture_output=True, timeout=30)
            try:
                with Image.open(frame) as source:
                    source.load()
                    image = source.convert("RGB")
                    image.thumbnail((640, 360))
                    x, y = (index % 4) * 640, (index // 4) * 384
                    grid.paste(image, (x, y + 24))
                    draw.text((x + 6, y + 4), f"{timestamp:.3f}s", fill="white")
            except (OSError, ValueError) as exc:
                raise TemporalEvidenceError("A native temporal frame could not be decoded.") from exc
        grid_path = Path(tmp) / "timed-grid.png"
        grid.save(grid_path)
        grid_hash = hashlib.sha256(grid_path.read_bytes()).hexdigest()
        analysis = vision_review(grid_path, mode="quick", cpu_only=True,
            max_visible_subjects=12, inference_timeout_seconds=180,
            review_requirements={"inspection":
                "The image is an ordered native-video contact sheet, left to right then top to bottom; "
                "each panel is labeled with its timestamp. Track the same visible people across panels, "
                "rather than counting repeated panels as new people. Describe observed changes in mouth "
                "position, head turns and speaking gestures by spatial position and clothing. Distinguish "
                "observed change from inference. This grid has no audio: it cannot establish audible words, "
                "voice identity or exact lip sync. Do not assume the requested character is speaking.",
                "timestamps_seconds": times})
        card = analysis.get("frame_card") if isinstance(analysis, dict) else None
        confidence = card.get("confidence") if isinstance(card, dict) else None
        if (not isinstance(card, dict) or analysis.get("analysis_valid") is not True
                or card.get("evidence_valid") is not True or not str(card.get("summary") or "").strip()
                or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 < confidence <= 1):
            raise TemporalEvidenceError("Trusted temporal observations are unavailable.")
        if digest() != expected_sha256:
            raise TemporalEvidenceError("Video bytes changed during temporal inspection.")
        return {"schema_version": 1, "video_sha256": expected_sha256,
            "grid_sha256": grid_hash, "timestamps_seconds": times, "device": "cpu",
            "frame_count": 16, "observations": card,
            "limitations": "Timed images show observable gestures; they do not certify audible speaker identity or exact lip sync."}


def validate_temporal_speaker_evidence(evidence: Any, *, video_sha256: str, duration_seconds: float) -> dict[str, Any]:
    """Refuse stale/malformed cached timed observations before Director inference."""
    if not isinstance(evidence, dict):
        raise TemporalEvidenceError("Temporal observations must be a structured object.")
    times = evidence.get("timestamps_seconds")
    expected = [round(duration_seconds * i / 16, 6) for i in range(16)]
    card = evidence.get("observations")
    confidence = card.get("confidence") if isinstance(card, dict) else None
    if (evidence.get("video_sha256") != video_sha256 or evidence.get("device") != "cpu"
            or evidence.get("frame_count") != 16 or not isinstance(times, list) or len(times) != 16
            or any(isinstance(a, bool) or not isinstance(a, (int, float))
                or not math.isfinite(a) or abs(a - b) > 0.000001 for a, b in zip(times, expected))
            or not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("grid_sha256") or ""))
            or not isinstance(card, dict) or card.get("evidence_valid") is not True
            or not str(card.get("summary") or "").strip() or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
            or not 0 < confidence <= 1):
        raise TemporalEvidenceError("Temporal observations do not match this exact video and sampling contract.")
    return evidence
