from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def extract_mp3(video_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{video_path.stem}.mp3"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
        str(out_file),
    ]
    subprocess.run(cmd, check=True)
    return out_file
