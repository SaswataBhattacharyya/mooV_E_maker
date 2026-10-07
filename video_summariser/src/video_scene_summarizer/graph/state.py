from __future__ import annotations

from typing import Any, TypedDict

from video_scene_summarizer.models.schemas import SceneBoundary, VideoRecord, VideoSummary


class WorkflowState(TypedDict, total=False):
    source_query: str
    requested_video_count: int
    output_root: str
    keep_downloaded_videos: bool
    use_transcript_fusion: bool
    reuse_cache: bool
    use_frame_shaving: bool
    use_scene_compaction: bool
    delete_frame_images: bool
    extract_fps: float | None
    config: Any
    visual_analyzer: Any
    text_generator: Any
    compact_text_generator: Any
    structuring_generator: Any
    whisper_model: Any
    event_callback: Any
    candidate_urls: list[dict[str, Any]]
    queued_videos: list[VideoRecord]
    processed_videos: list[VideoRecord]
    current_video: VideoRecord
    transcript: Any
    scenes: list[SceneBoundary]
    final_summary: VideoSummary | None
    errors: list[str]
    skipped_videos: list[str]
    download_root: str
