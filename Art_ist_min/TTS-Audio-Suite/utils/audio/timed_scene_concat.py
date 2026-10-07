"""
Manifest-driven scene clip concatenation utilities.

Concatenates clips in the explicit order defined by a JSON manifest and inserts
scheduled silence gaps between clips.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
import torchaudio

from utils.compatibility.pytorch_patches import apply_pytorch_patches
from utils.audio.processing import AudioProcessingUtils

apply_pytorch_patches(verbose=False)


def _load_manifest(manifest_path: str) -> Dict[str, Any]:
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a JSON object")

    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Manifest must contain a non-empty 'items' list")

    sample_rate = manifest.get("sample_rate")
    if sample_rate is not None:
        try:
            sample_rate = int(sample_rate)
        except Exception as exc:
            raise ValueError("Manifest 'sample_rate' must be an integer or null") from exc
        if sample_rate <= 0:
            raise ValueError("Manifest 'sample_rate' must be greater than zero")

    normalized_items: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest item {index} must be an object")

        file_name = str(item.get("file", "")).strip()
        if not file_name:
            raise ValueError(f"Manifest item {index} is missing required field 'file'")

        try:
            gap_after_seconds = float(item.get("gap_after_seconds", 0.0))
        except Exception as exc:
            raise ValueError(f"Manifest item {index} has invalid 'gap_after_seconds'") from exc

        if gap_after_seconds < 0:
            raise ValueError(f"Manifest item {index} has negative 'gap_after_seconds'")

        normalized_items.append(
            {
                "file": file_name,
                "gap_after_seconds": gap_after_seconds,
            }
        )

    return {
        "version": manifest.get("version", 1),
        "sample_rate": sample_rate,
        "items": normalized_items,
    }


def _normalize_waveform(waveform: torch.Tensor) -> torch.Tensor:
    if waveform.dim() == 1:
        return waveform.unsqueeze(0)
    if waveform.dim() == 2:
        return waveform
    if waveform.dim() == 3 and waveform.shape[0] == 1:
        return waveform.squeeze(0)
    raise ValueError(f"Unsupported waveform shape: {tuple(waveform.shape)}")


def _load_audio_with_ffmpeg_fallback(audio_path: Path) -> Tuple[torch.Tensor, int]:
    try:
        return AudioProcessingUtils.safe_load_audio(str(audio_path))
    except Exception as original_exc:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(f"Failed to load audio file {audio_path}: {original_exc}") from original_exc

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as temp_wav:
            command = [
                "ffmpeg",
                "-y",
                "-i",
                str(audio_path),
                "-vn",
                "-acodec",
                "pcm_f32le",
                temp_wav.name,
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode != 0:
                stderr = completed.stderr.strip() or "Unknown ffmpeg failure"
                raise RuntimeError(
                    f"Failed to load audio file {audio_path}: {original_exc}. "
                    f"ffmpeg fallback also failed: {stderr}"
                ) from original_exc
            return AudioProcessingUtils.safe_load_audio(temp_wav.name)


def concat_scene_audio_by_manifest(
    folder_path: str,
    manifest_path: str,
    output_path: Optional[str] = None,
) -> Dict[str, object]:
    manifest = _load_manifest(manifest_path)
    clips_dir = Path(folder_path)
    if not clips_dir.exists():
        raise FileNotFoundError(f"Clips folder not found: {folder_path}")
    if not clips_dir.is_dir():
        raise ValueError(f"Clips path is not a folder: {folder_path}")

    loaded: List[Tuple[str, torch.Tensor, int, float]] = []
    sample_rates: List[int] = []
    for item in manifest["items"]:
        clip_path = clips_dir / item["file"]
        if not clip_path.exists():
            raise FileNotFoundError(f"Clip listed in manifest was not found: {clip_path}")
        if not clip_path.is_file():
            raise ValueError(f"Manifest entry is not a file: {clip_path}")

        waveform, sample_rate = _load_audio_with_ffmpeg_fallback(clip_path)
        waveform = _normalize_waveform(waveform)
        loaded.append((clip_path.name, waveform, sample_rate, float(item["gap_after_seconds"])))
        sample_rates.append(sample_rate)

    target_sample_rate = manifest["sample_rate"] or max(sample_rates)
    assembled_segments: List[torch.Tensor] = []
    used_files: List[str] = []
    total_inserted_silence_seconds = 0.0

    for index, (file_name, waveform, sample_rate, gap_after_seconds) in enumerate(loaded):
        if sample_rate != target_sample_rate:
            resampler = torchaudio.transforms.Resample(sample_rate, target_sample_rate)
            waveform = resampler(waveform)

        assembled_segments.append(waveform)
        used_files.append(file_name)

        is_last_item = index == len(loaded) - 1
        if not is_last_item and gap_after_seconds > 0:
            silence = AudioProcessingUtils.create_silence(
                duration_seconds=gap_after_seconds,
                sample_rate=target_sample_rate,
                channels=waveform.shape[0],
                device=waveform.device,
                dtype=waveform.dtype,
            )
            silence = _normalize_waveform(silence)
            assembled_segments.append(silence)
            total_inserted_silence_seconds += gap_after_seconds

    final_audio = AudioProcessingUtils.concatenate_audio_segments(
        segments=assembled_segments,
        method="simple",
        sample_rate=target_sample_rate,
    )

    manifest_stem = Path(manifest_path).stem
    if output_path:
        final_path = Path(output_path)
    else:
        final_path = clips_dir / f"{manifest_stem}_final.wav"

    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_audio = _normalize_waveform(final_audio)
    torchaudio.save(str(final_path), final_audio.cpu(), target_sample_rate)

    total_duration_seconds = AudioProcessingUtils.get_audio_duration(final_audio, target_sample_rate)

    return {
        "output_path": str(final_path.resolve()),
        "manifest_path": str(Path(manifest_path).resolve()),
        "clip_count": len(used_files),
        "sample_rate": target_sample_rate,
        "used_files": used_files,
        "inserted_silence_seconds": round(total_inserted_silence_seconds, 6),
        "total_duration_seconds": round(total_duration_seconds, 6),
        "audio": AudioProcessingUtils.format_for_comfyui(final_audio, target_sample_rate),
    }
