from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from video_scene_summarizer.config.settings import AppConfig
from video_scene_summarizer.models.qwen_vl import OllamaTextGenerator, OllamaVisionAnalyzer
from video_scene_summarizer.models.schemas import BoundingBox, FrameAnalysis, FrameDelta, ObjectDelta, ObjectDetection, SceneBoundary, SceneStory
from video_scene_summarizer.processing.frame_extract import score_frame_change, select_progressive_frames
from video_scene_summarizer.providers.color import DominantColorProvider
from video_scene_summarizer.providers.optional_cv import ComfySam3Provider, DepthAnythingProvider, DINOEmbeddingProvider, DocTROcrProvider, FlorenceRegionProvider, ViTPoseProvider, YoloDetectionProvider
from video_scene_summarizer.utils.image_ops import load_image_size
from video_scene_summarizer.utils.text import dump_json, dump_text


LOGGER = logging.getLogger(__name__)


def select_scene_keyframes(scene: SceneBoundary, config: AppConfig, use_frame_shaving: bool) -> list[str]:
    frame_paths = scene.representative_frame_paths[:]
    if not frame_paths:
        return []
    if use_frame_shaving:
        frame_paths = select_progressive_frames(frame_paths, config.frame_change_threshold)
    selected_indices = {0, len(frame_paths) - 1, len(frame_paths) // 2}
    last_kept_index = 0
    for index in range(1, len(frame_paths) - 1):
        score = score_frame_change(frame_paths[last_kept_index], frame_paths[index])
        if score >= config.frame_change_threshold:
            selected_indices.add(index)
            last_kept_index = index
    ordered = sorted(selected_indices)
    if len(ordered) > config.max_keyframes_per_scene:
        ordered = _downsample_indices(ordered, config.max_keyframes_per_scene)
    if len(ordered) < config.min_keyframes_per_scene and len(frame_paths) >= config.min_keyframes_per_scene:
        ordered = sorted(set(ordered) | set(_checkpoint_indices(len(frame_paths))))
    return [frame_paths[index] for index in ordered]


def estimate_scene_timestamps(scene: SceneBoundary, frame_paths: list[str]) -> dict[str, float]:
    if not frame_paths:
        return {}
    if len(frame_paths) == 1:
        return {frame_paths[0]: scene.start_time_sec}
    delta = max(scene.duration_sec, 0.001) / max(len(frame_paths) - 1, 1)
    return {
        frame_path: round(scene.start_time_sec + delta * index, 3)
        for index, frame_path in enumerate(frame_paths)
    }


def build_frame_analysis(
    frame_path: str,
    frame_id: str,
    timestamp_sec: float,
    transcript_text: str,
    scene: SceneBoundary,
    config: AppConfig,
    visual_analyzer: OllamaVisionAnalyzer,
) -> FrameAnalysis:
    width, height = load_image_size(Path(frame_path))
    support_signals, warnings = collect_support_signals(Path(frame_path))
    prompt = (
        "Analyze this video keyframe in detail for downstream scene reconstruction.\n"
        "Focus on visible people, objects, setting, pose, spatial arrangement, text on screen, color palette, and anything that matters for continuity.\n"
        "Use practical searchable wording and avoid poetic language.\n"
        f"Scene id: {scene.scene_id}\n"
        f"Scene timing: {scene.start_time_hms} to {scene.end_time_hms}\n"
        "Return only factual visible detail from this frame."
    )
    structured_context = json.dumps(support_signals, ensure_ascii=False, indent=2)
    detailed_description = visual_analyzer.describe(
        prompt=prompt,
        frame_paths=[frame_path],
        transcript_text=transcript_text,
        structured_context=structured_context,
    ).strip()
    concise_summary = detailed_description.split("\n")[0].strip() if detailed_description else "No visual summary produced."
    analysis = FrameAnalysis(
        frame_id=frame_id,
        frame_path=frame_path,
        timestamp_sec=timestamp_sec,
        width=width,
        height=height,
        transcript_context=transcript_text,
        overview_caption=str(support_signals.get("florence_caption", "")).strip(),
        detailed_description=detailed_description,
        concise_summary=concise_summary,
        dominant_colors=support_signals.get("dominant_colors", []),
        object_detections=_build_object_detections(support_signals.get("detections", [])),
        florence_caption=str(support_signals.get("florence_caption", "")).strip(),
        ocr_text=str(support_signals.get("ocr_text", "")).strip(),
        support_signals=support_signals,
        warnings=warnings,
    )
    return analysis


def build_frame_delta(
    previous_analysis: FrameAnalysis,
    current_analysis: FrameAnalysis,
    transcript_text: str,
    visual_analyzer: OllamaVisionAnalyzer,
) -> FrameDelta:
    change_score = round(score_frame_change(previous_analysis.frame_path, current_analysis.frame_path), 6)
    object_changes, new_objects, removed_objects = _compare_objects(previous_analysis.object_detections, current_analysis.object_detections)
    camera_change = "large framing or subject shift" if change_score >= 0.18 else "small framing drift or local motion"
    lighting_change = _lighting_delta(previous_analysis.dominant_colors, current_analysis.dominant_colors)
    delta_prompt = (
        "You are comparing two consecutive kept video frames from the same cut-defined scene.\n"
        "Describe only what changed from the first image to the second image.\n"
        "Call out motion, pose shifts, new objects, removed objects, camera movement, and text changes.\n"
        "Do not restate the whole frame from scratch."
    )
    structured_context = json.dumps(
        {
            "previous_frame": previous_analysis.support_signals,
            "current_frame": current_analysis.support_signals,
            "change_score": change_score,
        },
        ensure_ascii=False,
        indent=2,
    )
    natural_language_delta = visual_analyzer.describe(
        prompt=delta_prompt,
        frame_paths=[previous_analysis.frame_path, current_analysis.frame_path],
        transcript_text=transcript_text,
        structured_context=structured_context,
    ).strip()
    main_action = natural_language_delta.split(".")[0].strip() if natural_language_delta else "Minor motion change."
    secondary_motion = [item.semantic_change for item in object_changes if item.semantic_change][:3]
    return FrameDelta(
        pair_id=f"{previous_analysis.frame_id}_to_{current_analysis.frame_id}",
        previous_frame_id=previous_analysis.frame_id,
        current_frame_id=current_analysis.frame_id,
        previous_frame_path=previous_analysis.frame_path,
        current_frame_path=current_analysis.frame_path,
        previous_timestamp_sec=previous_analysis.timestamp_sec,
        current_timestamp_sec=current_analysis.timestamp_sec,
        delta_time_sec=round(current_analysis.timestamp_sec - previous_analysis.timestamp_sec, 3),
        change_score=change_score,
        transcript_context=transcript_text,
        natural_language_delta=natural_language_delta,
        main_action=main_action,
        secondary_motion=secondary_motion,
        camera_change=camera_change,
        lighting_change=lighting_change,
        new_objects=new_objects,
        removed_objects=removed_objects,
        object_changes=object_changes,
    )


def stitch_scene_story(
    scene: SceneBoundary,
    structuring_generator: OllamaTextGenerator,
    use_transcript_fusion: bool,
) -> SceneStory:
    frame_sections: list[str] = []
    for analysis in scene.keyframe_analyses:
        frame_sections.append(
            f"{analysis.frame_id} @ {analysis.timestamp_sec:.2f}s\n"
            f"Full description:\n{analysis.detailed_description}".strip()
        )
    for delta in scene.frame_deltas:
        frame_sections.append(
            f"{delta.pair_id} [{delta.previous_timestamp_sec:.2f}s -> {delta.current_timestamp_sec:.2f}s]\n"
            f"Delta:\n{delta.natural_language_delta}".strip()
        )
    raw_scene_text = "\n\n".join(frame_sections).strip()
    prompt = (
        "You are stitching keyframe descriptions and frame-to-frame deltas into one coherent scene explanation.\n"
        "Respect the original order. Explain the visible progression clearly.\n"
        "Do not invent actions not supported by the evidence."
    )
    transcript_context = scene.transcript_text if use_transcript_fusion else ""
    scene_text = structuring_generator.generate(
        prompt=prompt,
        transcript_text=transcript_context,
        structured_context=raw_scene_text,
    ).strip()
    if not scene_text:
        scene_text = raw_scene_text
    event_chain = [delta.main_action for delta in scene.frame_deltas if delta.main_action]
    key_takeaways = [analysis.concise_summary for analysis in scene.keyframe_analyses[:3] if analysis.concise_summary]
    return SceneStory(
        scene_id=scene.scene_id,
        scene_title=f"{scene.scene_id} [{scene.start_time_hms} - {scene.end_time_hms}]",
        scene_text=scene_text,
        raw_scene_text=raw_scene_text,
        event_chain=event_chain,
        key_takeaways=key_takeaways,
    )


def write_scene_analysis_bundle(scene: SceneBoundary) -> None:
    analysis_dir = Path(scene.scene_dir_path) / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    for analysis in scene.keyframe_analyses:
        json_path = analysis_dir / f"{analysis.frame_id}_full.json"
        text_path = analysis_dir / f"{analysis.frame_id}_full.txt"
        analysis.full_json_path = str(json_path)
        analysis.full_text_path = str(text_path)
        dump_json(json_path, analysis.to_dict())
        dump_text(text_path, analysis.detailed_description + "\n")
    for delta in scene.frame_deltas:
        json_path = analysis_dir / f"{delta.pair_id}_delta.json"
        text_path = analysis_dir / f"{delta.pair_id}_delta.txt"
        delta.delta_json_path = str(json_path)
        delta.delta_text_path = str(text_path)
        dump_json(json_path, delta.to_dict())
        dump_text(text_path, delta.natural_language_delta + "\n")


def collect_support_signals(image_path: Path, *, cpu_only: bool = False) -> tuple[dict[str, object], list[str]]:
    if cpu_only:
        # The Director review path must not start opportunistic torch/CUDA
        # providers. Color is deterministic, local, and CPU-only.
        artifact = DominantColorProvider().analyze(image_path, {})
        return {"dominant_colors": artifact.data.get("dominant_colors", [])}, list(artifact.warnings)
    providers = [YoloDetectionProvider(), DominantColorProvider(), DocTROcrProvider()]
    if os.environ.get("VIDEO_SUMMARIZER_DISABLE_FLORENCE", "").lower() not in {"1", "true", "yes"}:
        providers.insert(1, FlorenceRegionProvider())
    if os.environ.get("VIDEO_SUMMARIZER_ENABLE_DEPTH", "1").lower() in {"1", "true", "yes"}:
        providers.append(DepthAnythingProvider())
    if os.environ.get("VIDEO_SUMMARIZER_ENABLE_DINO", "0").lower() in {"1", "true", "yes"}:
        providers.append(DINOEmbeddingProvider())
    if os.environ.get("VIDEO_SUMMARIZER_ENABLE_SAM3", "1").lower() in {"1", "true", "yes"}:
        providers.append(ComfySam3Provider())
    if os.environ.get("VIDEO_SUMMARIZER_ENABLE_POSE", "1").lower() in {"1", "true", "yes"}:
        providers.append(ViTPoseProvider())
    support_signals: dict[str, object] = {}
    warnings: list[str] = []
    for provider in providers:
        artifact = provider.analyze(image_path, {})
        warnings.extend(artifact.warnings)
        if provider.name == "yolo":
            support_signals["detections"] = artifact.data.get("detections", [])
        elif provider.name == "florence2":
            support_signals["florence_caption"] = artifact.data.get("caption", "")
        elif provider.name == "color":
            support_signals["dominant_colors"] = artifact.data.get("dominant_colors", [])
        elif provider.name == "doctr":
            support_signals["ocr_text"] = artifact.data.get("ocr_text", "")
            support_signals["ocr_words"] = artifact.data.get("words", [])
        elif provider.name == "depth_anything_v2":
            support_signals["depth"] = artifact.data
        elif provider.name == "dinov3":
            support_signals["embedding"] = artifact.data
        elif provider.name == "comfyui_sam3":
            support_signals["sam3"] = artifact.data
        elif provider.name == "vitpose":
            support_signals["pose"] = artifact.data
    return support_signals, warnings


def _checkpoint_indices(length: int) -> list[int]:
    if length <= 1:
        return [0]
    return sorted({0, length // 2, length - 1})


def _downsample_indices(indices: list[int], target_count: int) -> list[int]:
    if len(indices) <= target_count:
        return indices
    step = (len(indices) - 1) / max(target_count - 1, 1)
    selected = {indices[0], indices[-1]}
    for position in range(1, target_count - 1):
        selected.add(indices[round(position * step)])
    return sorted(selected)


def _build_object_detections(payload: object) -> list[ObjectDetection]:
    detections: list[ObjectDetection] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        bbox_payload = item.get("bbox_px", {})
        detections.append(
            ObjectDetection(
                label=str(item.get("label", "object")),
                confidence=float(item.get("confidence", 0.0)),
                bbox_px=BoundingBox(
                    x1=int(bbox_payload.get("x1", 0)),
                    y1=int(bbox_payload.get("y1", 0)),
                    x2=int(bbox_payload.get("x2", 0)),
                    y2=int(bbox_payload.get("y2", 0)),
                ),
                provenance=str(item.get("provenance", "")),
            )
        )
    return detections


def _compare_objects(
    previous_objects: list[ObjectDetection],
    current_objects: list[ObjectDetection],
) -> tuple[list[ObjectDelta], list[str], list[str]]:
    previous_by_label = _group_by_label(previous_objects)
    current_by_label = _group_by_label(current_objects)
    labels = sorted(set(previous_by_label) | set(current_by_label))
    changes: list[ObjectDelta] = []
    new_objects: list[str] = []
    removed_objects: list[str] = []
    for label in labels:
        prev_items = previous_by_label.get(label, [])
        curr_items = current_by_label.get(label, [])
        if not prev_items and curr_items:
            new_objects.extend([label] * len(curr_items))
            continue
        if prev_items and not curr_items:
            removed_objects.extend([label] * len(prev_items))
            continue
        for prev_item, curr_item in zip(prev_items, curr_items):
            prev_center = prev_item.bbox_px.center()
            curr_center = curr_item.bbox_px.center()
            shift = (round(curr_center[0] - prev_center[0], 3), round(curr_center[1] - prev_center[1], 3))
            semantic = _shift_to_text(shift)
            changes.append(
                ObjectDelta(
                    label=label,
                    previous_bbox=prev_item.bbox_px,
                    current_bbox=curr_item.bbox_px,
                    shift_px=shift,
                    confidence_delta=round(curr_item.confidence - prev_item.confidence, 4),
                    semantic_change=semantic,
                )
            )
    return changes, new_objects, removed_objects


def _group_by_label(items: list[ObjectDetection]) -> dict[str, list[ObjectDetection]]:
    grouped: dict[str, list[ObjectDetection]] = {}
    for item in items:
        grouped.setdefault(item.label, []).append(item)
    return grouped


def _shift_to_text(shift: tuple[float, float]) -> str:
    x_shift, y_shift = shift
    if abs(x_shift) < 2 and abs(y_shift) < 2:
        return "mostly stable position"
    horizontal = "right" if x_shift > 0 else "left"
    vertical = "down" if y_shift > 0 else "up"
    if abs(x_shift) >= abs(y_shift):
        return f"moves slightly {horizontal}"
    return f"moves slightly {vertical}"


def _lighting_delta(previous_colors: list[dict[str, object]], current_colors: list[dict[str, object]]) -> str:
    prev_name = str(previous_colors[0].get("name", "")) if previous_colors else ""
    curr_name = str(current_colors[0].get("name", "")) if current_colors else ""
    if prev_name == curr_name:
        return "lighting and dominant colors remain broadly stable"
    if not prev_name or not curr_name:
        return "lighting change uncertain"
    return f"dominant palette shifts from {prev_name} to {curr_name}"
