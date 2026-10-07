# mp3_extract.py
import os
import shutil
import subprocess
from pathlib import Path

# Defaults (change if you want)
DEFAULT_VIDEO_DIR = "/path/out_videos"
DEFAULT_OUT_DIR = "/path/saved_mp3"
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}

def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def extract_mp3(video_path: Path, out_dir: Path):
    """Extract audio from video and save as mp3."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (video_path.stem + ".mp3")

    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-vn",  # no video
        "-acodec", "libmp3lame",
        "-q:a", "2",  # quality (lower is better, 2 is good)
        str(out_file)
    ]
    subprocess.run(cmd, check=True)

def main():
    video_dir = input(f"Video folder [{DEFAULT_VIDEO_DIR}]: ").strip() or DEFAULT_VIDEO_DIR
    out_dir = input(f"Save mp3 to [{DEFAULT_OUT_DIR}]: ").strip() or DEFAULT_OUT_DIR

    video_dir = Path(video_dir)
    out_dir = Path(out_dir)

    if not has_ffmpeg():
        print("ffmpeg not found. Please install ffmpeg and retry.")
        return

    videos = [p for p in sorted(video_dir.glob("*"))
              if p.is_file() and p.suffix.lower() in VIDEO_EXTS]

    if not videos:
        print(f"No videos found in {video_dir}")
        return

    for vid in videos:
        print(f"→ Extracting audio from: {vid.name}")
        try:
            extract_mp3(vid, out_dir)
            print("   Saved.")
        except subprocess.CalledProcessError as e:
            print(f"   Failed: {e}")

if __name__ == "__main__":
    main()
