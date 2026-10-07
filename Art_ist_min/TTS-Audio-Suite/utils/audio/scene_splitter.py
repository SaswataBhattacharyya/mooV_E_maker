"""
Scene audio splitting utilities.

Splits a scene audio file into ordered clips based on target edit ranges while
preserving untouched gaps as separate clips.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
import torchaudio

from utils.compatibility.pytorch_patches import apply_pytorch_patches
from utils.audio.processing import AudioProcessingUtils

apply_pytorch_patches(verbose=False)


SUPPORTED_AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}


@dataclass
class EditInstruction:
    start: float
    end: float
    text: str
    params: Dict[str, Any]


def _parse_time_value(value: str) -> float:
    value = value.strip()
    if ":" in value:
        parts = value.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
    return float(value)


def parse_instruction_file(instruction_path: str) -> List[EditInstruction]:
    """
    Parse JSON or simple text edit instructions.

    JSON is the preferred format. Text blocks are accepted as a fallback:

        5.0,10.0
        Text for this clip
        edit_type=emotion
        emotion=sad
    """
    path = Path(instruction_path)
    if not path.exists():
        raise FileNotFoundError(f"Instruction file not found: {instruction_path}")

    if path.suffix.lower() == ".json":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            raw = raw.get("edits", [])
        if not isinstance(raw, list):
            raise ValueError("JSON edit instructions must be a list or a dict with an 'edits' list")

        instructions = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Each JSON edit item must be an object")
            start = float(item["start"])
            end = float(item["end"])
            text = str(item.get("text", "")).strip()
            params = {k: v for k, v in item.items() if k not in {"start", "end", "text", "file_name"}}
            instructions.append(EditInstruction(start=start, end=end, text=text, params=params))
        return instructions

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        return []

    instructions = []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", content) if b.strip()]
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError(f"Invalid text instruction block: {block!r}")
        time_line = lines[0]
        if "," in time_line:
            start_s, end_s = time_line.split(",", 1)
        elif "-" in time_line:
            start_s, end_s = time_line.split("-", 1)
        else:
            raise ValueError(f"Invalid timing line: {time_line!r}")
        start = _parse_time_value(start_s)
        end = _parse_time_value(end_s)
        text = lines[1]
        params: Dict[str, Any] = {}
        for line in lines[2:]:
            if "=" in line:
                key, value = line.split("=", 1)
                params[key.strip()] = value.strip()
        instructions.append(EditInstruction(start=start, end=end, text=text, params=params))
    return instructions


def _validate_and_sort_instructions(instructions: List[EditInstruction], duration: float) -> List[EditInstruction]:
    sorted_instructions = sorted(instructions, key=lambda item: item.start)
    last_end = 0.0
    for item in sorted_instructions:
        if item.start < 0 or item.end <= item.start:
            raise ValueError(f"Invalid range: {item.start} -> {item.end}")
        if item.end > duration + 1e-6:
            raise ValueError(f"Range {item.start}->{item.end} exceeds audio duration {duration:.3f}s")
        if item.start < last_end - 1e-6:
            raise ValueError("Edit ranges overlap; ranges must be non-overlapping and sorted")
        last_end = item.end
    return sorted_instructions


def _extract_segment(audio: torch.Tensor, start_sample: int, end_sample: int) -> torch.Tensor:
    if audio.dim() == 1:
        return audio[start_sample:end_sample]
    return audio[:, start_sample:end_sample]


def _save_wav(audio: torch.Tensor, sample_rate: int, output_path: str) -> None:
    if audio.dim() == 3:
        audio = audio.squeeze(0)
    elif audio.dim() == 1:
        audio = audio.unsqueeze(0)
    torchaudio.save(output_path, audio.cpu(), sample_rate)


def split_scene_audio(
    audio_path: str,
    instruction_path: str,
    output_dir: str,
    transcript_path: Optional[str] = None,
    clip_name_template: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Split scene audio into sequential clips and write enriched JSON + manifest.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    waveform, sample_rate = AudioProcessingUtils.safe_load_audio(audio_path)
    if waveform.dim() == 1:
        working_audio = waveform.unsqueeze(0)
    else:
        working_audio = waveform

    duration = working_audio.shape[-1] / sample_rate
    instructions = _validate_and_sort_instructions(parse_instruction_file(instruction_path), duration)

    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    for item in instructions:
        if item.start > cursor:
            segments.append({"kind": "untouched", "start": cursor, "end": item.start, "text": "", "params": {}})
        segments.append({
            "kind": "edited_target",
            "start": item.start,
            "end": item.end,
            "text": item.text,
            "params": dict(item.params),
        })
        cursor = item.end
    if cursor < duration:
        segments.append({"kind": "untouched", "start": cursor, "end": duration, "text": "", "params": {}})

    scene_stem = Path(audio_path).stem
    pad_width = max(2, len(str(len(segments))))
    manifest: List[Dict[str, Any]] = []
    enriched_instructions: List[Dict[str, Any]] = []

    for index, segment in enumerate(segments, start=1):
        start_sample = max(0, int(segment["start"] * sample_rate))
        end_sample = max(start_sample, int(segment["end"] * sample_rate))
        clip_audio = _extract_segment(working_audio, start_sample, end_sample)
        if clip_name_template:
            clip_name = clip_name_template.format(
                scene_stem=scene_stem,
                index=index,
                pad_width=pad_width,
                kind=segment["kind"],
                start=round(segment["start"], 6),
                end=round(segment["end"], 6),
            )
        else:
            clip_name = f"{scene_stem}_{index:0{pad_width}d}.wav"
        clip_path = output_path / clip_name
        _save_wav(clip_audio, sample_rate, str(clip_path))

        manifest_item = {
            "clip_index": index,
            "start": round(segment["start"], 6),
            "end": round(segment["end"], 6),
            "duration": round(segment["end"] - segment["start"], 6),
            "kind": segment["kind"],
            "text": segment["text"],
            "source_file": os.path.basename(audio_path),
            "split_file": clip_name,
            "edited_file": f"edited_{clip_name}" if segment["kind"] == "edited_target" else None,
        }
        manifest.append(manifest_item)

        if segment["kind"] == "edited_target":
            enriched = {
                "file_name": clip_name,
                "start": round(segment["start"], 6),
                "end": round(segment["end"], 6),
                "text": segment["text"],
                **segment["params"],
            }
            enriched_instructions.append(enriched)

    transcript_text = None
    if transcript_path:
        transcript_text = Path(transcript_path).read_text(encoding="utf-8")

    enriched_json_path = output_path / f"{Path(instruction_path).stem}_enriched.json"
    manifest_path = output_path / f"{scene_stem}_scene_manifest.json"

    with open(enriched_json_path, "w", encoding="utf-8") as f:
        json.dump(enriched_instructions, f, indent=2, ensure_ascii=False)
        f.write("\n")

    scene_manifest = {
        "source_audio": os.path.basename(audio_path),
        "source_audio_path": str(Path(audio_path).resolve()),
        "sample_rate": sample_rate,
        "duration": round(duration, 6),
        "transcript_path": str(Path(transcript_path).resolve()) if transcript_path else None,
        "transcript_text": transcript_text,
        "clips": manifest,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(scene_manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return {
        "output_dir": str(output_path.resolve()),
        "enriched_json_path": str(enriched_json_path.resolve()),
        "scene_manifest_path": str(manifest_path.resolve()),
        "clip_count": len(segments),
        "edited_target_count": len(enriched_instructions),
        "sample_rate": sample_rate,
        "duration": round(duration, 6),
    }
