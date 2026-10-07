import os
import shutil
import subprocess
from pathlib import Path

# Defaults based on your reference style
DEFAULT_VIDEO_DIR = "/path/to/webm_videos"
DEFAULT_OUT_DIR = "/path/to/mp4_outputs"
VIDEO_EXTS = {".webm"}

def has_ffmpeg() -> bool:
    """Check if ffmpeg is installed in the system path."""
    return shutil.which("ffmpeg") is not None

def convert_to_mp4(video_path: Path, out_dir: Path):
    """Convert webm to mp4 using H.264 and AAC codecs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (video_path.stem + ".mp4")

    # Command optimized for compatibility and quality
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-c:v", "libx264",    # Video codec: H.264
        "-preset", "medium",  # Encoding speed vs compression
        "-crf", "23",         # Quality (18-28 is standard; lower is better)
        "-c:a", "aac",        # Audio codec: AAC
        "-b:a", "128k",       # Audio bitrate
        "-movflags", "+faststart", # Optimizes for web streaming
        str(out_file)
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully converted: {video_path.name}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting {video_path.name}: {e}")

def main():
    video_dir = input(f"WebM folder [{DEFAULT_VIDEO_DIR}]: ").strip() or DEFAULT_VIDEO_DIR
    out_dir = input(f"Save MP4s to [{DEFAULT_OUT_DIR}]: ").strip() or DEFAULT_OUT_DIR

    video_dir = Path(video_dir)
    out_dir = Path(out_dir)

    if not has_ffmpeg():
        print("ffmpeg not found. Please install ffmpeg and retry.")
        return

    # Find all .webm files in the source directory
    videos = [p for p in sorted(video_dir.glob("*"))
              if p.is_file() and p.suffix.lower() in VIDEO_EXTS]

    if not videos:
        print(f"No .webm files found in {video_dir}")
        return

    print(f"Found {len(videos)} files. Starting conversion...")
    for video in videos:
        convert_to_mp4(video, out_dir)
    
    print("\nAll tasks completed.")

if __name__ == "__main__":
    main()