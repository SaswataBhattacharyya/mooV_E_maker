from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from video_scene_summarizer.models.schemas import SceneBoundary, TranscriptResult, VideoRecord, VideoSummary
from video_scene_summarizer.utils.text import dump_json, dump_text, make_json_safe


LOGGER = logging.getLogger(__name__)


def video_output_dir(output_dir: Path, record: VideoRecord) -> Path:
    return output_dir / record.sanitized_name


def write_video_outputs(
    output_dir: Path,
    record: VideoRecord,
    transcript: TranscriptResult | None,
    scenes: list[SceneBoundary],
    final_summary: VideoSummary,
) -> None:
    target_dir = video_output_dir(output_dir, record)
    target_dir.mkdir(parents=True, exist_ok=True)

    scene_compiled_parts: list[str] = []
    scene_story_parts: list[str] = []
    scene_metadata: list[dict[str, Any]] = []
    for scene in scenes:
        scene_text = scene.scene_compiled_text.strip()
        if scene_text:
            scene_compiled_parts.append(f"{scene.scene_id} [{scene.start_time_hms} - {scene.end_time_hms}]\n{scene_text}")
        scene_story_text = (scene.scene_story_text or scene.scene_compiled_text).strip()
        if scene_story_text:
            scene_story_parts.append(f"{scene.scene_id} [{scene.start_time_hms} - {scene.end_time_hms}]\n{scene_story_text}")
        scene_metadata.append(
            {
                "scene_id": scene.scene_id,
                "scene_number": scene.scene_number,
                "start_time_sec": scene.start_time_sec,
                "end_time_sec": scene.end_time_sec,
                "duration_sec": scene.duration_sec,
                "start_time_hms": scene.start_time_hms,
                "end_time_hms": scene.end_time_hms,
                "frame_count": scene.frame_count,
                "scene_dir_path": scene.scene_dir_path,
                "scene_text_path": scene.scene_text_path,
                "raw_scene_text_path": scene.raw_scene_text_path,
                "compact_scene_text_path": scene.compact_scene_text_path,
                "scene_story_json_path": scene.scene_story_json_path,
                "scene_story_text_path": scene.scene_story_text_path,
                "previous_scene_overlap_frame_path": scene.previous_scene_overlap_frame_path,
                "keyframe_paths": scene.keyframe_paths,
                "keyframe_analyses": [analysis.to_dict() for analysis in scene.keyframe_analyses],
                "frame_deltas": [delta.to_dict() for delta in scene.frame_deltas],
            }
        )

    audio_text = ""
    if transcript:
        segments_text = "\n".join(f"[{segment.start:.2f}-{segment.end:.2f}] {segment.text}" for segment in transcript.segments)
        audio_text = (
            f"Language: {transcript.language}\n\n"
            "Full Transcript:\n"
            f"{transcript.text}\n\n"
            "Timestamped Segments:\n"
            f"{segments_text}".strip()
        )

    metadata_payload = {
        "source_query": record.source_query,
        "source_url": record.source_url,
        "video_title": record.title,
        "video_path": str(record.video_path) if record.video_path else None,
        "audio_path": str(record.audio_path) if record.audio_path else None,
        "transcript_path": str(record.transcript_path) if record.transcript_path else None,
        "scene_count": len(scenes),
        "detected_language": transcript.language if transcript else record.metadata.get("detected_language", "unknown"),
        "scenes": scene_metadata,
        "record_metadata": {
            key: value
            for key, value in record.metadata.items()
            if not str(key).startswith("_")
        },
    }

    dump_json(target_dir / "metadata.json", make_json_safe(metadata_payload))
    dump_text(target_dir / "audio.txt", audio_text)
    dump_text(target_dir / "video_scene.txt", "\n\n".join(scene_compiled_parts).strip())
    dump_text(target_dir / "video_story.txt", "\n\n".join(scene_story_parts).strip())
    transition_rows = [item.to_dict() for item in final_summary.scene_transitions]
    dump_json(target_dir / "cross_scene_analysis.json", transition_rows)
    dump_text(
        target_dir / "cross_scene_analysis.txt",
        "\n\n".join(
            f"{item.from_scene_id} → {item.to_scene_id}\n"
            f"Visual transition: {item.visual_transition or 'Not established'}\n"
            f"Activity change: {item.activity_change or 'Not established'}\n"
            f"Narrative connection: {item.narrative_connection or 'Not established'}\n"
            f"Confidence: {item.confidence}"
            for item in final_summary.scene_transitions
        ),
    )
    dump_json(
        target_dir / "video_story.json",
        {
            "video_title": record.title,
            "scene_count": len(scenes),
            "video_story_text": final_summary.video_story_text,
            "scenes": scene_metadata,
            "scene_transitions": transition_rows,
        },
    )
    dump_text(target_dir / "summary_video.txt", final_summary.detailed_video_summary)
    dump_json(target_dir / "summary_video.json", final_summary.to_dict())
    LOGGER.info("Wrote raw pipeline outputs for %s to %s", record.title, target_dir)


def cache_path(cache_dir: Path, record: VideoRecord, suffix: str) -> Path:
    return cache_dir / record.sanitized_name / suffix


def cached_exists(cache_dir: Path, record: VideoRecord, suffix: str) -> bool:
    return cache_path(cache_dir, record, suffix).exists()


def write_cache(cache_dir: Path, record: VideoRecord, suffix: str, payload: Any) -> Path:
    path = cache_path(cache_dir, record, suffix)
    dump_json(path, payload)
    return path
