#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import shutil
import subprocess
from pathlib import Path

# -------- Defaults (edit if you like) --------
DEFAULT_VIDEO_DIR = "/home/saswata/web_dev/youtube_song/out_videos"
DEFAULT_OUT_DIR = "/home/saswata/web_dev/youtube_song/frames"
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}

# Default thresholds (tune as needed)
DEFAULT_SCENE_THRESH = 0.35   # 0.2–0.5 typical; lower => more frames
DEFAULT_INTERVAL_SEC = 2.0
DEFAULT_JPG_Q = 2            # 2 is high quality, 31 is low (ffmpeg -q:v)
# ---------------------------------------------

def slugify(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)

def require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found. Install ffmpeg and ensure it's in PATH.")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found (usually comes with ffmpeg).")

def run(cmd):
    subprocess.run(cmd, check=True)

def extract_interval_ffmpeg(video_path: Path, interval_sec: float, out_dir: Path, jpg_q: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%06d.jpg")
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-vf", f"fps=1/{interval_sec}",
        "-vsync", "vfr",
        "-q:v", str(jpg_q),
        pattern,
    ]
    run(cmd)

def extract_all_frames_lossless(video_path: Path, out_dir: Path):
    """Extract EVERY frame from video at its native rate as high-quality PNG."""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # %04d creates a numbered sequence (0001.png, 0002.png, etc.)
    out_pattern = out_dir / f"{video_path.stem}_%04d.png"

    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-pix_fmt", "rgb24",      # Best color quality for painting
        "-vsync", "passthrough",  # Keeps original frame timing 1:1
        str(out_pattern)
    ]
    
    print(f"Extracting all frames from {video_path.name}...")
    subprocess.run(cmd, check=True)

def extract_keyframes_ffmpeg(video_path: Path, out_dir: Path, jpg_q: int):
    """
    Extract true keyframes (I-frames) only.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "kf_%06d.jpg")
    # select I-frames; showinfo helps debug but we keep it minimal
    vf = "select='eq(pict_type,I)'"
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-vsync", "vfr",
        "-q:v", str(jpg_q),
        pattern,
    ]
    run(cmd)

def extract_scenes_ffmpeg(video_path: Path, scene_thresh: float, out_dir: Path, jpg_q: int):
    """
    Extract scene-change frames using ffmpeg's scene score.
    These are often the best 'key frames' for summarizing a video.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "sc_%06d.jpg")
    vf = f"select='gt(scene,{scene_thresh})'"
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-vsync", "vfr",
        "-q:v", str(jpg_q),
        pattern,
    ]
    run(cmd)

def extract_scene_keyframes_ffmpeg(video_path: Path, scene_thresh: float, out_dir: Path, jpg_q: int):
    """
    Scene change frames, but restrict to I-frames when possible.
    This reduces motion-blur-ish mid-GOP frames.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "sckf_%06d.jpg")
    # keep frames that are scene changes AND I-frames
    vf = f"select='gt(scene,{scene_thresh})*eq(pict_type,I)'"
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-vsync", "vfr",
        "-q:v", str(jpg_q),
        pattern,
    ]
    run(cmd)

def main():
    require_ffmpeg()

    video_dir = input(f"Video folder [{DEFAULT_VIDEO_DIR}]: ").strip() or DEFAULT_VIDEO_DIR
    out_root  = input(f"Save frames to [{DEFAULT_OUT_DIR}]: ").strip() or DEFAULT_OUT_DIR

    mode = input("Mode [interval/keyframe/scene/scene+keyframe] (default scene): ").strip().lower() or "scene"

    interval_sec = DEFAULT_INTERVAL_SEC
    scene_thresh = DEFAULT_SCENE_THRESH

    if mode == "interval":
        val = input(f"Extract every X seconds [{DEFAULT_INTERVAL_SEC}]: ").strip()
        interval_sec = float(val) if val else DEFAULT_INTERVAL_SEC
        if interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")
    elif mode in {"scene", "scene+keyframe"}:
        val = input(f"Scene threshold 0.2–0.5 [{DEFAULT_SCENE_THRESH}]: ").strip()
        scene_thresh = float(val) if val else DEFAULT_SCENE_THRESH
        if not (0.0 < scene_thresh < 1.0):
            raise ValueError("scene_thresh should be between 0 and 1")

    val = input(f"JPG quality (ffmpeg -q:v) [1(best)-31(worst)] [{DEFAULT_JPG_Q}]: ").strip()
    jpg_q = int(val) if val else DEFAULT_JPG_Q
    if jpg_q < 1 or jpg_q > 31:
        raise ValueError("jpg_q must be in [1, 31]")

    video_dir = Path(video_dir)
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    videos = [
        p for p in sorted(video_dir.glob("*"))
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    ]
    if not videos:
        print(f"No videos found in: {video_dir}")
        return

    for vid in videos:
        subdir = out_root / slugify(vid.stem) / mode.replace("+", "_")
        print(f"\n→ {vid.name}: mode={mode} -> {subdir}")

        try:
            if mode == "all":
                # New mode for professional animation work
                extract_all_frames_lossless(vid, subdir)
            elif mode == "interval":
                extract_interval_ffmpeg(vid, interval_sec, subdir, jpg_q)
            elif mode == "keyframe":
                extract_keyframes_ffmpeg(vid, subdir, jpg_q)
            elif mode == "scene":
                extract_scenes_ffmpeg(vid, scene_thresh, subdir, jpg_q)
            elif mode == "scene+keyframe":
                extract_scene_keyframes_ffmpeg(vid, scene_thresh, subdir, jpg_q)
            else:
                raise ValueError("Mode must be one of: interval, keyframe, scene, scene+keyframe")

            print("   Done.")
        except subprocess.CalledProcessError as e:
            print(f"   ffmpeg failed: {e} (skipping)")

if __name__ == "__main__":
    main()
