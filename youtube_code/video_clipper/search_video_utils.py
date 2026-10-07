#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import shutil
import subprocess
import tempfile
from pathlib import Path

from search_config import FRAME_SAMPLE_COUNT


def require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found. Install ffmpeg and ensure it's in PATH.")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found (usually comes with ffmpeg).")


def get_video_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def generate_windows(duration_sec: float, clip_len_sec: float, overlap_sec: float) -> list[dict]:
    if clip_len_sec <= 0:
        raise ValueError("clip_len_sec must be > 0")
    if overlap_sec < 0:
        raise ValueError("overlap_sec must be >= 0")
    if overlap_sec >= clip_len_sec:
        raise ValueError("overlap_sec must be smaller than clip_len_sec")

    if duration_sec <= 0:
        return []

    step = clip_len_sec - overlap_sec
    windows = []
    start_sec = 0.0

    while start_sec < duration_sec:
        end_sec = min(start_sec + clip_len_sec, duration_sec)
        windows.append(
            {
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
            }
        )
        if end_sec >= duration_sec:
            break
        start_sec += step

    return windows


def sample_window_frames(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    temp_root: Path | None = None,
    sample_count: int = FRAME_SAMPLE_COUNT,
) -> list[Path]:
    duration_sec = max(0.05, end_sec - start_sec)
    sample_count = max(1, int(sample_count))
    temp_base = Path(tempfile.mkdtemp(prefix="search_clip_frames_", dir=str(temp_root) if temp_root else None))
    out_pattern = temp_base / "frame_%03d.jpg"
    fps_value = max(sample_count / duration_sec, 0.2)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-t",
        f"{duration_sec:.3f}",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps_value:.6f},scale='min(640,iw)':-2",
        "-frames:v",
        str(sample_count),
        "-q:v",
        "3",
        str(out_pattern),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    frames = sorted(temp_base.glob("frame_*.jpg"))

    if result.returncode != 0:
        stderr_text = (result.stderr or "").strip()
        if "Nothing was written into output file" in stderr_text or not frames:
            return []
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=result.stderr,
        )

    return frames


def extract_clip(video_path: Path, output_path: Path, start_sec: float, end_sec: float):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_sec = max(0.05, end_sec - start_sec)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-t",
        f"{duration_sec:.3f}",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
