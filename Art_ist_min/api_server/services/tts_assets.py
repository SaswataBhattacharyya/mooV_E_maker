"""Helpers for story intake, TTS assets, aliases, and SRT analysis."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESP_DIR = PROJECT_ROOT / "resp"
SRT_ANALYSIS_DIR = PROJECT_ROOT / "srt_analysis"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
CORE_ALIASES = ("Alice", "Bob", "Narrator")


def ensure_storage_dirs() -> None:
    RESP_DIR.mkdir(parents=True, exist_ok=True)
    SRT_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sanitize_filename_stem(value: str, *, preserve_spaces: bool = False) -> str:
    cleaned = re.sub(r"[^\w\s.-]", "", value.strip())
    cleaned = re.sub(r"\s+", " " if preserve_spaces else "_", cleaned)
    cleaned = cleaned.strip(" ._")
    return cleaned or "untitled"


def get_tts_root() -> Path:
    candidates = [
        PROJECT_ROOT / "TTS-Audio-Suite",
        PROJECT_ROOT / "ComfyUI" / "custom_nodes" / "TTS-Audio-Suite",
        PROJECT_ROOT / "comfyui" / "custom_nodes" / "TTS-Audio-Suite",
    ]
    for candidate in candidates:
        if (candidate / "utils").exists():
            return candidate
    raise FileNotFoundError("TTS-Audio-Suite checkout was not found")


def get_voices_examples_dir() -> Path:
    voices_dir = get_tts_root() / "voices_examples"
    voices_dir.mkdir(parents=True, exist_ok=True)
    return voices_dir


def get_alias_map_path() -> Path:
    return get_voices_examples_dir() / "#character_alias_map.txt"


def ensure_alias_map_file() -> Path:
    alias_path = get_alias_map_path()
    if not alias_path.exists():
        alias_path.write_text(
            "# Character Alias Map\n"
            "# Empty lines and comments are ignored\n"
            "# Format: Alias<TAB>Character_Name\n",
            encoding="utf-8",
        )
    return alias_path


def _parse_alias_line(line: str) -> tuple[str | None, str | None]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, None

    if "=" in stripped:
        left, right = stripped.split("=", 1)
        alias = left.strip()
        target = right.split(",", 1)[0].strip()
        return (alias, target) if alias and target else (None, None)

    if "\t" in stripped:
        parts = [part.strip() for part in stripped.split("\t") if part.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]

    return None, None


def load_alias_map() -> dict[str, str]:
    alias_path = ensure_alias_map_file()
    aliases: dict[str, str] = {}
    for raw_line in alias_path.read_text(encoding="utf-8").splitlines():
        alias, target = _parse_alias_line(raw_line)
        if alias and target:
            aliases[alias.lower()] = target
    return aliases


def set_core_aliases(*, alice: str, bob: str, narrator: str) -> dict[str, str]:
    alias_path = ensure_alias_map_file()
    requested = {
        "alice": alice.strip().lower(),
        "bob": bob.strip().lower(),
        "narrator": narrator.strip().lower(),
    }
    missing = [alias for alias, target in requested.items() if not target]
    if missing:
        raise ValueError(f"Alias target missing for: {', '.join(missing)}")

    lines = alias_path.read_text(encoding="utf-8").splitlines()
    updated_lines: list[str] = []
    seen: set[str] = set()
    for line in lines:
        alias, _target = _parse_alias_line(line)
        if alias and alias.lower() in requested:
            updated_lines.append(f"{alias.title()}\t{requested[alias.lower()]}")
            seen.add(alias.lower())
        else:
            updated_lines.append(line)

    if updated_lines and updated_lines[-1].strip():
        updated_lines.append("")

    for alias_name in CORE_ALIASES:
        alias_key = alias_name.lower()
        if alias_key not in seen:
            updated_lines.append(f"{alias_name}\t{requested[alias_key]}")

    alias_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    return {
        "Alice": requested["alice"],
        "Bob": requested["bob"],
        "Narrator": requested["narrator"],
        "alias_file": str(alias_path.resolve()),
    }


def _find_companion_text(audio_path: Path) -> Path | None:
    reference_file = audio_path.with_suffix(".reference.txt")
    if reference_file.exists() and reference_file.read_text(encoding="utf-8").strip():
        return reference_file
    text_file = audio_path.with_suffix(".txt")
    if text_file.exists() and text_file.read_text(encoding="utf-8").strip():
        return text_file
    return None


def discover_voice_options() -> list[dict[str, str]]:
    voices_dir = get_voices_examples_dir()
    options: list[dict[str, str]] = []
    for audio_path in sorted(voices_dir.rglob("*")):
        if not audio_path.is_file() or audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        companion = _find_companion_text(audio_path)
        if companion is None:
            continue
        relative_path = audio_path.relative_to(voices_dir)
        options.append(
            {
                "value": audio_path.stem.lower(),
                "label": audio_path.stem,
                "path": str(relative_path),
                "audio_path": str(audio_path.resolve()),
                "reference_path": str(companion.resolve()),
            }
        )
    return options


def save_story_text(*, name: str, mode: str, story_text: str) -> dict[str, str]:
    ensure_storage_dirs()
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"formatted", "outline"}:
        raise ValueError("Story mode must be 'formatted' or 'outline'")
    if not story_text.strip():
        raise ValueError("Story text is empty")

    safe_name = sanitize_filename_stem(name)
    target_path = RESP_DIR / f"{safe_name}_{normalized_mode}.txt"
    target_path.write_text(story_text.strip() + "\n", encoding="utf-8")
    return {
        "name": safe_name,
        "mode": normalized_mode,
        "path": str(target_path.resolve()),
    }


def _write_text_asset(target_path: Path, content: str) -> None:
    target_path.write_text(content.strip() + "\n", encoding="utf-8")


def save_voice_like_asset(
    *,
    category: str,
    asset_name: str,
    audio_filename: str,
    audio_bytes: bytes,
    reference_text: str,
    overwrite: bool = False,
) -> dict[str, str]:
    voices_dir = get_voices_examples_dir()
    safe_name = sanitize_filename_stem(asset_name, preserve_spaces=True)
    suffix = Path(audio_filename or "upload.wav").suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise ValueError("Unsupported audio file type")
    if not reference_text.strip():
        raise ValueError("Reference text is required")

    audio_path = voices_dir / f"{safe_name}{suffix}"
    reference_path = voices_dir / f"{safe_name}.reference.txt"
    if not overwrite and (audio_path.exists() or reference_path.exists()):
        raise FileExistsError(f"Asset '{safe_name}' already exists")

    audio_path.write_bytes(audio_bytes)
    _write_text_asset(reference_path, reference_text)
    return {
        "category": category,
        "asset_name": safe_name,
        "token": safe_name.lower(),
        "audio_path": str(audio_path.resolve()),
        "reference_path": str(reference_path.resolve()),
    }


def _ensure_tts_imports() -> None:
    tts_root = str(get_tts_root())
    if tts_root not in sys.path:
        sys.path.insert(0, tts_root)


def _parse_srt_content(content: str) -> list[Any]:
    _ensure_tts_imports()
    from utils.timing.parser import SRTParser

    return SRTParser.parse_srt_content(content, allow_overlaps=True)


def _overlap_pairs(subtitles: list[Any]) -> list[tuple[Any, Any]]:
    pairs: list[tuple[Any, Any]] = []
    for index in range(len(subtitles) - 1):
        current = subtitles[index]
        next_subtitle = subtitles[index + 1]
        if current.end_time > next_subtitle.start_time:
            pairs.append((current, next_subtitle))
    return pairs


def build_srt_analysis_report(content: str, *, input_label: str, timing_mode: str = "pad_with_silence") -> dict[str, Any]:
    ensure_storage_dirs()
    subtitles = _parse_srt_content(content)
    overlap_pairs = _overlap_pairs(subtitles)
    total_duration = subtitles[-1].end_time if subtitles else 0.0
    durations = [subtitle.duration for subtitle in subtitles]
    gap_values = []
    for index in range(len(subtitles) - 1):
        gap_values.append(subtitles[index + 1].start_time - subtitles[index].end_time)

    analysis_name = sanitize_filename_stem(input_label) or "srt"
    run_dir = SRT_ANALYSIS_DIR / f"{analysis_name}_{_utc_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    input_path = run_dir / "input.srt"
    input_path.write_text(content, encoding="utf-8")

    lines = [
        "SRT Analysis Report",
        "===================",
        f"Input label: {input_label}",
        f"Timing mode assumption: {timing_mode}",
        f"Total subtitles: {len(subtitles)}",
        f"Total duration: {total_duration:.3f}s",
        f"Shortest subtitle: {min(durations):.3f}s" if durations else "Shortest subtitle: n/a",
        f"Longest subtitle: {max(durations):.3f}s" if durations else "Longest subtitle: n/a",
        f"Overlapping pairs: {len(overlap_pairs)}",
        "",
        "Per-subtitle timing:",
    ]
    for subtitle in subtitles:
        lines.append(
            f"  {subtitle.sequence:2d}. {subtitle.start_time:7.3f}s -> {subtitle.end_time:7.3f}s "
            f"(duration {subtitle.duration:6.3f}s) | {subtitle.text[:80]}"
        )

    lines.extend(["", "Gap/overlap summary:"])
    if not gap_values:
        lines.append("  Only one subtitle block present.")
    else:
        for index, gap in enumerate(gap_values, start=1):
            relation = "overlap" if gap < 0 else "gap"
            lines.append(f"  {index:2d}->{index + 1:2d}: {relation} {abs(gap):.3f}s")

    lines.extend(["", "Detected overlaps:"])
    if not overlap_pairs:
        lines.append("  None")
    else:
        for current, next_subtitle in overlap_pairs:
            lines.append(
                f"  Seq {current.sequence} overlaps Seq {next_subtitle.sequence} by "
                f"{current.end_time - next_subtitle.start_time:.3f}s"
            )

    report_text = "\n".join(lines) + "\n"
    report_path = run_dir / "report.txt"
    report_path.write_text(report_text, encoding="utf-8")

    metadata = {
        "input_label": input_label,
        "timing_mode": timing_mode,
        "subtitle_count": len(subtitles),
        "total_duration": round(total_duration, 6),
        "overlap_count": len(overlap_pairs),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = run_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    return {
        "report": report_text,
        "analysis_dir": str(run_dir.resolve()),
        "report_path": str(report_path.resolve()),
        "input_path": str(input_path.resolve()),
        "metadata_path": str(metadata_path.resolve()),
        "subtitle_count": len(subtitles),
        "overlap_count": len(overlap_pairs),
        "audio_artifacts": [],
    }
