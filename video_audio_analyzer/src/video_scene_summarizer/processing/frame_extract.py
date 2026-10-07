from __future__ import annotations

import re
import shutil
import subprocess
from math import ceil
from pathlib import Path

import cv2


PTS_TIME_PATTERN = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH.")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found in PATH.")


def probe_video_duration(video_path: Path) -> float:
    require_ffmpeg()
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
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError as exc:
        raise RuntimeError(f"Could not parse duration for {video_path.name}") from exc


def detect_cut_timestamps_ffmpeg(video_path: Path, scene_thresh: float) -> list[float]:
    require_ffmpeg()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video_path),
        "-filter:v",
        f"select='gt(scene,{scene_thresh})',showinfo",
        "-vsync",
        "vfr",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    stderr = result.stderr or ""
    cut_times: list[float] = []
    for match in PTS_TIME_PATTERN.finditer(stderr):
        timestamp = float(match.group(1))
        if not cut_times or abs(cut_times[-1] - timestamp) > 0.05:
            cut_times.append(timestamp)
    return cut_times


def build_scene_spans(
    video_path: Path,
    scene_thresh: float,
    min_scene_length_sec: float,
) -> list[tuple[float, float]]:
    duration = probe_video_duration(video_path)
    if duration <= 0.0:
        return [(0.0, 0.1)]

    cut_points = [point for point in detect_cut_timestamps_ffmpeg(video_path, scene_thresh) if 0.0 < point < duration]
    raw_points = [0.0, *cut_points, duration]
    spans: list[tuple[float, float]] = []

    for index in range(len(raw_points) - 1):
        start_sec = raw_points[index]
        end_sec = raw_points[index + 1]
        if end_sec <= start_sec:
            continue
        if spans and (end_sec - start_sec) < min_scene_length_sec:
            prev_start, _prev_end = spans[-1]
            spans[-1] = (prev_start, end_sec)
            continue
        spans.append((start_sec, end_sec))

    if not spans:
        spans.append((0.0, duration))
    return spans


def extract_frames_between_ffmpeg(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    out_dir: Path,
    jpg_q: int = 2,
    fps: float | None = None,
) -> list[str]:
    require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%06d.jpg")
    duration = max(0.05, end_sec - start_sec)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-i",
        str(video_path),
        "-t",
        f"{duration:.3f}",
    ]
    if fps is not None and fps > 0:
        cmd.extend(["-vf", f"fps={fps:g}"])
    cmd.extend([
        "-q:v",
        str(jpg_q),
        pattern,
    ])
    subprocess.run(cmd, check=True)
    return [str(path) for path in sorted(out_dir.glob("frame_*.jpg"))]


def score_frame_change(prev_frame_path: str, curr_frame_path: str) -> float:
    prev = cv2.imread(prev_frame_path, cv2.IMREAD_GRAYSCALE)
    curr = cv2.imread(curr_frame_path, cv2.IMREAD_GRAYSCALE)
    if prev is None or curr is None:
        return 1.0

    target_size = (160, 90)
    prev = cv2.resize(prev, target_size, interpolation=cv2.INTER_AREA)
    curr = cv2.resize(curr, target_size, interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(prev, curr)
    return float(diff.mean() / 255.0)


def select_progressive_frames(frame_paths: list[str], change_threshold: float) -> list[str]:
    if len(frame_paths) <= 3:
        return frame_paths[:]

    anchor_indices = [0]
    last_anchor_index = 0
    for index in range(1, len(frame_paths) - 1):
        score = score_frame_change(frame_paths[last_anchor_index], frame_paths[index])
        if score >= change_threshold:
            anchor_indices.append(index)
            last_anchor_index = index
    if anchor_indices[-1] != len(frame_paths) - 1:
        anchor_indices.append(len(frame_paths) - 1)

    selected_indices: set[int] = set()
    for start_index, end_index in zip(anchor_indices, anchor_indices[1:]):
        for chosen in _progressive_indices_between(start_index, end_index):
            selected_indices.add(chosen)

    if len(anchor_indices) == 2:
        for fallback_index in _progressive_indices_between(0, len(frame_paths) - 1):
            selected_indices.add(fallback_index)

    ordered_indices = sorted(selected_indices)
    if 0 not in ordered_indices:
        ordered_indices.insert(0, 0)
    if ordered_indices[-1] != len(frame_paths) - 1:
        ordered_indices.append(len(frame_paths) - 1)
    return [frame_paths[index] for index in ordered_indices]


def _progressive_indices_between(start_index: int, end_index: int) -> list[int]:
    if end_index <= start_index:
        return [start_index]

    gap = end_index - start_index
    target_points = 2 + ceil(gap / 20)
    target_points = min(target_points, gap + 1)
    if target_points <= 2:
        return [start_index, end_index]

    indices = {start_index, end_index}
    denominator = target_points - 1
    for step in range(1, target_points - 1):
        candidate = start_index + round((gap * step) / denominator)
        indices.add(candidate)
    return sorted(indices)


def extract_interval_ffmpeg(video_path: Path, interval_sec: float, out_dir: Path, jpg_q: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%06d.jpg")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps=1/{interval_sec}",
        "-vsync",
        "vfr",
        "-q:v",
        str(jpg_q),
        pattern,
    ]
    subprocess.run(cmd, check=True)


def extract_keyframes_ffmpeg(video_path: Path, out_dir: Path, jpg_q: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "kf_%06d.jpg")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        "select='eq(pict_type,I)'",
        "-vsync",
        "vfr",
        "-q:v",
        str(jpg_q),
        pattern,
    ]
    subprocess.run(cmd, check=True)


def extract_scenes_ffmpeg(video_path: Path, scene_thresh: float, out_dir: Path, jpg_q: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "sc_%06d.jpg")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"select='gt(scene,{scene_thresh})'",
        "-vsync",
        "vfr",
        "-q:v",
        str(jpg_q),
        pattern,
    ]
    subprocess.run(cmd, check=True)
