from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptResult:
    language: str
    text: str
    segments: list[TranscriptSegment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "text": self.text,
            "segments": [segment.to_dict() for segment in self.segments],
        }


@dataclass
class VideoRecord:
    source_query: str
    source_url: str
    video_id: str
    title: str
    sanitized_name: str
    video_path: Path | None = None
    audio_path: Path | None = None
    transcript_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    processed: bool = False
    deleted_video: bool = False
    error: str | None = None


@dataclass
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ObjectDetection:
    label: str
    confidence: float
    bbox_px: BoundingBox
    provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "bbox_px": self.bbox_px.to_dict(),
            "provenance": self.provenance,
        }


@dataclass
class FrameAnalysis:
    frame_id: str
    frame_path: str
    timestamp_sec: float
    width: int
    height: int
    transcript_context: str = ""
    overview_caption: str = ""
    detailed_description: str = ""
    concise_summary: str = ""
    dominant_colors: list[dict[str, Any]] = field(default_factory=list)
    object_detections: list[ObjectDetection] = field(default_factory=list)
    florence_caption: str = ""
    ocr_text: str = ""
    support_signals: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    full_json_path: str = ""
    full_text_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["object_detections"] = [item.to_dict() for item in self.object_detections]
        return payload


@dataclass
class ObjectDelta:
    label: str
    previous_bbox: BoundingBox | None = None
    current_bbox: BoundingBox | None = None
    shift_px: tuple[float, float] = (0.0, 0.0)
    confidence_delta: float = 0.0
    semantic_change: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "previous_bbox": self.previous_bbox.to_dict() if self.previous_bbox else None,
            "current_bbox": self.current_bbox.to_dict() if self.current_bbox else None,
            "shift_px": list(self.shift_px),
            "confidence_delta": self.confidence_delta,
            "semantic_change": self.semantic_change,
        }


@dataclass
class FrameDelta:
    pair_id: str
    previous_frame_id: str
    current_frame_id: str
    previous_frame_path: str
    current_frame_path: str
    previous_timestamp_sec: float
    current_timestamp_sec: float
    delta_time_sec: float
    change_score: float
    transcript_context: str = ""
    natural_language_delta: str = ""
    main_action: str = ""
    secondary_motion: list[str] = field(default_factory=list)
    camera_change: str = ""
    lighting_change: str = ""
    new_objects: list[str] = field(default_factory=list)
    removed_objects: list[str] = field(default_factory=list)
    object_changes: list[ObjectDelta] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    delta_json_path: str = ""
    delta_text_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["object_changes"] = [item.to_dict() for item in self.object_changes]
        return payload


@dataclass
class SceneStory:
    scene_id: str
    scene_title: str
    scene_text: str
    raw_scene_text: str
    story_json_path: str = ""
    story_text_path: str = ""
    event_chain: list[str] = field(default_factory=list)
    key_takeaways: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SceneBoundary:
    scene_id: str
    scene_number: int
    start_time_sec: float
    end_time_sec: float
    duration_sec: float
    start_time_hms: str
    end_time_hms: str
    representative_frame_paths: list[str] = field(default_factory=list)
    selected_frame_paths: list[str] = field(default_factory=list)
    keyframe_paths: list[str] = field(default_factory=list)
    frame_count: int = 0
    scene_dir_path: str = ""
    scene_text_path: str = ""
    raw_scene_text_path: str = ""
    compact_scene_text_path: str = ""
    scene_story_json_path: str = ""
    scene_story_text_path: str = ""
    previous_scene_overlap_frame_path: str = ""
    scene_compiled_text: str = ""
    scene_story_text: str = ""
    frame_text_chunks: list[str] = field(default_factory=list)
    transcript_text: str = ""
    transcript_language: str = "unknown"
    visual_description: str = ""
    previous_scene_context: str = ""
    keywords: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)
    keyframe_analyses: list[FrameAnalysis] = field(default_factory=list)
    frame_deltas: list[FrameDelta] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["keyframe_analyses"] = [item.to_dict() for item in self.keyframe_analyses]
        payload["frame_deltas"] = [item.to_dict() for item in self.frame_deltas]
        return payload


@dataclass
class SceneTransition:
    from_scene_id: str
    to_scene_id: str
    from_time_sec: float
    to_time_sec: float
    persistent_entities: list[str] = field(default_factory=list)
    appearing_entities: list[str] = field(default_factory=list)
    disappearing_entities: list[str] = field(default_factory=list)
    location_change: str = ""
    time_change: str = ""
    visual_transition: str = ""
    activity_change: str = ""
    narrative_connection: str = ""
    transcript_connection: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: str = "unknown"
    uncertainty_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoSummary:
    source_query: str
    source_url: str
    downloaded_video_path_or_deleted_flag: str
    detected_language: str
    number_of_scenes: int
    ordered_scene_ids: list[str]
    brief_video_summary: str
    detailed_video_summary: str
    continuity_map: list[dict[str, Any]]
    main_entities: list[str]
    topics: list[str]
    warnings_or_uncertainties: list[str]
    video_story_text: str = ""
    video_story_json_path: str = ""
    scene_transitions: list[SceneTransition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scene_transitions"] = [item.to_dict() for item in self.scene_transitions]
        return payload
