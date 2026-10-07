from __future__ import annotations

import logging
import shutil
from pathlib import Path

from video_scene_summarizer.models.schemas import SceneBoundary, TranscriptResult
from video_scene_summarizer.processing.frame_extract import build_scene_spans, extract_frames_between_ffmpeg
from video_scene_summarizer.utils.text import seconds_to_hms


LOGGER = logging.getLogger(__name__)


def detect_scene_boundaries(video_path: Path, threshold: float, min_scene_length_sec: float) -> list[tuple[float, float]]:
    return build_scene_spans(
        video_path=video_path,
        scene_thresh=threshold,
        min_scene_length_sec=min_scene_length_sec,
    )


def transcript_slice(transcript: TranscriptResult | None, start_sec: float, end_sec: float) -> str:
    if not transcript:
        return ""
    relevant = [
        segment.text.strip()
        for segment in transcript.segments
        if segment.end >= start_sec and segment.start <= end_sec and segment.text.strip()
    ]
    return " ".join(relevant).strip()


def build_scene_shells(
    video_path: Path,
    scene_spans: list[tuple[float, float]],
    transcript: TranscriptResult | None,
    output_root: Path,
    sample_count: int = 0,
    extract_fps: float | None = None,
) -> list[SceneBoundary]:
    del sample_count
    scenes: list[SceneBoundary] = []
    output_root.mkdir(parents=True, exist_ok=True)

    for index, (start_sec, end_sec) in enumerate(scene_spans, start=1):
        scene_dir = output_root / f"scene_{index}"
        frame_paths = extract_frames_between_ffmpeg(
            video_path=video_path,
            start_sec=start_sec,
            end_sec=end_sec,
            out_dir=scene_dir,
            fps=extract_fps,
        )
        scene = SceneBoundary(
            scene_id=f"scene_{index}",
            scene_number=index,
            start_time_sec=round(start_sec, 3),
            end_time_sec=round(end_sec, 3),
            duration_sec=round(max(0.0, end_sec - start_sec), 3),
            start_time_hms=seconds_to_hms(start_sec),
            end_time_hms=seconds_to_hms(end_sec),
            representative_frame_paths=frame_paths,
            selected_frame_paths=frame_paths[:],
            frame_count=len(frame_paths),
            scene_dir_path=str(scene_dir),
            scene_text_path=str(scene_dir / f"scene_{index}.txt"),
            raw_scene_text_path=str(scene_dir / f"scene_{index}_raw.txt"),
            compact_scene_text_path=str(scene_dir / f"scene_{index}.txt"),
            transcript_text=transcript_slice(transcript, start_sec, end_sec),
            transcript_language=transcript.language if transcript else "unknown",
        )
        scenes.append(scene)

    for index in range(1, len(scenes)):
        previous_scene = scenes[index - 1]
        current_scene = scenes[index]
        if not previous_scene.representative_frame_paths:
            continue
        previous_last_frame = Path(previous_scene.representative_frame_paths[-1])
        if not previous_last_frame.exists():
            continue
        overlap_target = Path(current_scene.scene_dir_path) / f"overlap_prev_scene_{previous_scene.scene_number:04d}.jpg"
        shutil.copy2(previous_last_frame, overlap_target)
        current_scene.previous_scene_overlap_frame_path = str(overlap_target)

    LOGGER.info("Built %s cut-based scene folders for %s", len(scenes), video_path.name)
    return scenes
