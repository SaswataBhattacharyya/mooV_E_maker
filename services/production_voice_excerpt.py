"""Create an explicit short H3 voice reference from a project voice master."""
from __future__ import annotations

import math
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from story_builder.services.production_assets import ProductionAssetError, probe_media, register_output


class VoiceExcerptError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def create_h3_voice_excerpt(*, storage_root: Path, output_root: Path, project_id: str,
                            run_id: str, character_id: str, source_asset: dict[str, Any],
                            source_path: Path, start_sec: float, duration_seconds: float,
                            run_process: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                            probe: Callable[[Path, str], dict[str, Any]] = probe_media) -> dict[str, Any]:
    try:
        canonical_run = str(uuid.UUID(run_id))
        canonical_character = str(uuid.UUID(character_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise VoiceExcerptError("identity_invalid", "Run and character IDs must be UUIDs.") from exc
    if canonical_run != run_id.lower() or canonical_character != character_id.lower():
        raise VoiceExcerptError("identity_invalid", "Run and character IDs must use canonical UUID form.")
    if not math.isfinite(float(start_sec)) or not math.isfinite(float(duration_seconds)):
        raise VoiceExcerptError("excerpt_interval_invalid", "Excerpt time values must be finite numbers.")
    if start_sec < 0 or duration_seconds < 2 or duration_seconds > 15:
        raise VoiceExcerptError("excerpt_interval_invalid", "H3 voice excerpts must be 2–15 seconds and start at or after zero.")
    if source_asset.get("kind") != "audio" or "voice_master" not in source_asset.get("roles", []):
        raise VoiceExcerptError("source_not_voice_master", "Only a registered voice_master audio asset can be excerpted.")
    media = source_asset.get("media") if isinstance(source_asset.get("media"), dict) else {}
    source_duration = media.get("duration_seconds")
    if not isinstance(source_duration, (int, float)) or start_sec + duration_seconds > source_duration:
        raise VoiceExcerptError("excerpt_outside_source", "Requested excerpt must fit inside the verified source voice master.")
    source = Path(source_path).resolve()
    if not source.is_file():
        raise VoiceExcerptError("source_missing", "Registered voice master file is missing.")
    project_root = Path(output_root).resolve() / project_id
    destination_dir = (project_root / "voices" / canonical_character / "references").resolve()
    if not destination_dir.is_relative_to(project_root) or not project_root.is_relative_to(Path(output_root).resolve()):
        raise VoiceExcerptError("unsafe_output_path", "Voice excerpt destination escapes the project output directory.")
    destination_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{start_sec:.3f}-{duration_seconds:.3f}".replace(".", "p")
    relative = Path("voices") / canonical_character / "references" / f"{source_asset['asset_id']}-{suffix}.wav"
    target = (project_root / relative).resolve()
    if not target.is_relative_to(project_root):
        raise VoiceExcerptError("unsafe_output_path", "Voice excerpt filename escapes the project output directory.")
    if not target.exists():
        fd, temporary = tempfile.mkstemp(prefix=".voice-excerpt-", suffix=".wav", dir=destination_dir)
        os.close(fd)
        try:
            run_process(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{start_sec:.6f}", "-i", str(source), "-t", f"{duration_seconds:.6f}",
                "-vn", "-ac", "1", "-ar", "32000", "-c:a", "pcm_s16le", temporary],
                check=True, capture_output=True, text=True, timeout=90)
            probed = probe(Path(temporary), "audio")
            if abs(float(probed.get("duration_seconds") or 0) - duration_seconds) > 0.2:
                raise VoiceExcerptError("excerpt_duration_mismatch", "Prepared H3 excerpt duration differs from its requested interval.")
            os.replace(temporary, target)
        except VoiceExcerptError:
            Path(temporary).unlink(missing_ok=True)
            raise
        except (OSError, subprocess.SubprocessError, ProductionAssetError) as exc:
            Path(temporary).unlink(missing_ok=True)
            raise VoiceExcerptError("excerpt_conversion_failed", f"FFmpeg could not prepare the H3 voice excerpt: {exc}") from exc
    record = register_output(storage_root, output_root, project_id,
        relative_path=relative.as_posix(), role="voice_excerpt",
        metadata={"approval_status": "accepted", "source_voice_asset_id": source_asset["asset_id"],
            "source_sha256": source_asset.get("sha256"), "run_id": canonical_run,
            "character_id": canonical_character, "start_sec": float(start_sec),
            "duration_seconds": float(duration_seconds), "sample_rate_hz": 32000,
            "channels": 1, "format": "pcm_s16le_wav", "purpose": "h3_voice_timbre_reference"})
    return record
