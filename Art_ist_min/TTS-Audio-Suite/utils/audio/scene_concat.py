"""
Scene clip concatenation utilities.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torchaudio

from utils.compatibility.pytorch_patches import apply_pytorch_patches
from utils.audio.processing import AudioProcessingUtils

apply_pytorch_patches(verbose=False)


CLIP_RE = re.compile(r"^(edited_)?(.+?)_(\d+)\.(wav|flac|mp3|ogg|m4a|aac)$", re.IGNORECASE)


def _discover_scene_clips(folder_path: str) -> List[Tuple[int, Path, bool]]:
    candidates: Dict[int, Tuple[Path, bool]] = {}
    for path in Path(folder_path).iterdir():
        if not path.is_file():
            continue
        match = CLIP_RE.match(path.name)
        if not match:
            continue
        is_edited = bool(match.group(1))
        index = int(match.group(3))
        existing = candidates.get(index)
        if existing is None or (is_edited and not existing[1]):
            candidates[index] = (path, is_edited)
    return [(index, path, is_edited) for index, (path, is_edited) in sorted(candidates.items())]


def concat_scene_audio(folder_path: str, output_path: Optional[str] = None) -> Dict[str, object]:
    clip_entries = _discover_scene_clips(folder_path)
    if not clip_entries:
        raise ValueError(f"No numbered scene clips found in folder: {folder_path}")

    loaded = []
    sample_rates = []
    for _, path, _ in clip_entries:
        waveform, sample_rate = AudioProcessingUtils.safe_load_audio(str(path))
        if waveform.dim() == 1:
            waveform = waveform.unsqueeze(0)
        loaded.append((path, waveform, sample_rate))
        sample_rates.append(sample_rate)

    target_sample_rate = max(sample_rates)
    segments = []
    used_files = []
    for path, waveform, sample_rate in loaded:
        if sample_rate != target_sample_rate:
            resampler = torchaudio.transforms.Resample(sample_rate, target_sample_rate)
            waveform = resampler(waveform)
        segments.append(waveform)
        used_files.append(path.name)

    final_audio = AudioProcessingUtils.concatenate_audio_segments(
        segments=segments,
        method="simple",
        sample_rate=target_sample_rate,
    )

    if output_path:
        final_path = Path(output_path)
    else:
        folder = Path(folder_path)
        scene_name = CLIP_RE.match(used_files[0]).group(2)
        final_path = folder / f"{scene_name}_final.wav"

    final_path.parent.mkdir(parents=True, exist_ok=True)
    if final_audio.dim() == 1:
        final_audio = final_audio.unsqueeze(0)
    torchaudio.save(str(final_path), final_audio.cpu(), target_sample_rate)

    return {
        "output_path": str(final_path.resolve()),
        "clip_count": len(used_files),
        "sample_rate": target_sample_rate,
        "used_files": used_files,
        "audio": AudioProcessingUtils.format_for_comfyui(final_audio, target_sample_rate),
    }
