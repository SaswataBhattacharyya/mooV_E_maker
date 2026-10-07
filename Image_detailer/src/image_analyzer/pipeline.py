from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from image_analyzer.config.settings import AppConfig
from image_analyzer.models.schemas import (
    AnalysisResult,
    AnalysisEvent,
    BoundingBox,
    DescriptionLayer,
    FaceRecord,
    ImageMetadata,
    ImageSummary,
    MeasuredField,
    NormalizedBoundingBox,
    ObjectRecord,
    PersonRecord,
    RegionRecord,
    SceneSummary,
    TextRegion,
    UncertaintyRecord,
)
from image_analyzer.providers.color import DominantColorProvider
from image_analyzer.providers.mediapipe_tools import MediaPipePeopleProvider
from image_analyzer.providers.ollama import OllamaSynthesisProvider, configure_ollama_runtime
from image_analyzer.providers.optional_cv import FlorenceRegionProvider, TesseractOcrProvider, YoloDetectionProvider
from image_analyzer.utils.files import dump_json, dump_text, sha256_file
from image_analyzer.utils.geometry import normalize_bbox
from image_analyzer.utils.image_ops import load_image_size


def analyze_image(
    image_path: Path,
    config: AppConfig,
    output_root: Path | None = None,
    save_debug: bool | None = None,
    event_callback: Callable[[AnalysisEvent], None] | None = None,
) -> AnalysisResult:
    image_path = image_path.resolve()
    output_root = output_root or config.paths.artifact_dir
    save_debug = config.pipeline.save_debug_by_default if save_debug is None else save_debug
    events: list[AnalysisEvent] = []
    width, height = load_image_size(image_path)
    _emit_event(
        events,
        "load_image",
        "running",
        f"Loaded image metadata for {image_path.name}.",
        {"image_path": str(image_path)},
        event_callback,
    )
    metadata = ImageMetadata(
        source_path=str(image_path),
        file_name=image_path.name,
        sha256=sha256_file(image_path),
        width=width,
        height=height,
    )

    module_outputs: dict[str, object] = {}
    uncertainties: list[UncertaintyRecord] = []

    _emit_event(events, "run_yolo", "running", "Running object detection.", {}, event_callback)
    yolo = YoloDetectionProvider().analyze(image_path, {})
    _record_provider(events, yolo.provider, yolo, event_callback)
    _emit_event(events, "run_florence", "running", "Running region captioning.", {}, event_callback)
    florence = FlorenceRegionProvider().analyze(image_path, {})
    _record_provider(events, florence.provider, florence, event_callback)
    _emit_event(events, "run_colors", "running", "Extracting dominant colors.", {}, event_callback)
    colors = DominantColorProvider().analyze(image_path, {})
    _record_provider(events, colors.provider, colors, event_callback)

    needs_people = _needs_people_modules(config, yolo.data)
    people_reason = "Detected at least one person; running pose/face/segmentation modules." if needs_people else (
        "Skipping pose/face/segmentation because no person detection was present or those modules are disabled."
    )
    _emit_event(
        events,
        "decide_people_modules",
        "completed",
        people_reason,
        {"enabled": needs_people},
        event_callback,
    )
    mediapipe = None
    if needs_people:
        _emit_event(events, "run_mediapipe", "running", "Running MediaPipe people analysis.", {}, event_callback)
        mediapipe = MediaPipePeopleProvider().analyze(image_path, {})
        _record_provider(events, mediapipe.provider, mediapipe, event_callback)

    ocr = None
    if config.pipeline.enable_ocr:
        _emit_event(events, "run_ocr", "running", "Running OCR extraction.", {}, event_callback)
        ocr = TesseractOcrProvider().analyze(image_path, {})
        _record_provider(events, ocr.provider, ocr, event_callback)
    else:
        _emit_event(
            events,
            "run_ocr",
            "skipped",
            "Skipping OCR because it is disabled in the pipeline config.",
            {"enabled": False},
            event_callback,
        )

    provider_results = [yolo, florence, colors]
    if mediapipe is not None:
        provider_results.append(mediapipe)
    if ocr is not None:
        provider_results.append(ocr)

    for artifact in provider_results:
        module_outputs[artifact.provider] = artifact.data
        uncertainties.extend(UncertaintyRecord(source=artifact.provider, message=warning) for warning in artifact.warnings)

    objects = _build_objects(yolo.data, width, height, colors.data)
    people = _build_people(objects, mediapipe.data if mediapipe else {})
    faces = _build_faces(mediapipe.data if mediapipe else {}, width, height)
    text_regions = _build_text_regions(ocr.data if ocr else {}, width, height)
    regions = _build_regions(colors.data, width, height)
    short_caption = _extract_short_caption(florence.data)
    scene = SceneSummary(category=_scene_category(objects), confidence=0.45, provenance="heuristic")

    synthesis = OllamaSynthesisProvider(
        base_url=config.models.ollama_base_url,
        model_name=config.models.synthesis_model,
        timeout_sec=config.models.ollama_timeout_sec,
    )
    configure_ollama_runtime(
        max_loaded_models=config.models.ollama_max_loaded_models,
        num_parallel=config.models.ollama_num_parallel,
    )
    _emit_event(
        events,
        "synthesize_layers",
        "running",
        "Synthesizing final layered descriptions from measured findings.",
        {"model": config.models.synthesis_model},
        event_callback,
    )
    synthesis_artifact = synthesis.synthesize(
        image_path,
        {
            "image": metadata.model_dump(),
            "objects": [item.model_dump() for item in objects],
            "people": [item.model_dump() for item in people],
            "faces": [item.model_dump() for item in faces],
            "text_regions": [item.model_dump() for item in text_regions],
            "regions": [item.model_dump() for item in regions],
            "scene": scene.model_dump(),
            "caption": short_caption,
        },
    )
    module_outputs[synthesis_artifact.provider] = synthesis_artifact.data
    uncertainties.extend(
        UncertaintyRecord(source=synthesis_artifact.provider, message=warning)
        for warning in synthesis_artifact.warnings
    )
    long_description = synthesis_artifact.data.get("description") if synthesis_artifact.data else ""
    if not long_description:
        long_description = _fallback_description(short_caption, objects, text_regions, scene)
    _record_provider(events, synthesis_artifact.provider, synthesis_artifact, event_callback)

    layers = _build_description_layers(
        image_name=image_path.stem,
        short_caption=short_caption,
        long_description=long_description,
        objects=objects,
        people=people,
        faces=faces,
        text_regions=text_regions,
        regions=regions,
        scene=scene,
        uncertainties=uncertainties,
    )

    result = AnalysisResult(
        image=metadata,
        summary=ImageSummary(short_caption=short_caption, long_description=long_description),
        objects=objects,
        people=people,
        faces=faces,
        regions=regions,
        text_regions=text_regions,
        scene=scene,
        provenance={artifact.provider: sorted(artifact.data.keys()) for artifact in [*provider_results, synthesis_artifact]},
        uncertainty=uncertainties,
        description_layers=layers,
        orchestration_events=events,
    )
    _emit_event(
        events,
        "write_outputs",
        "running",
        f"Writing output bundle under {(output_root / image_path.stem)!s}.",
        {"output_root": str(output_root)},
        event_callback,
    )
    result.orchestration_events = list(events)
    _write_output_bundle(output_root, image_path.stem, result, module_outputs, save_debug)
    _emit_event(
        events,
        "write_outputs",
        "completed",
        f"Saved {len(layers)} layered descriptions and structured outputs.",
        {"bundle_dir": str(output_root / image_path.stem)},
        event_callback,
    )
    result.orchestration_events = list(events)
    _rewrite_event_bundle(output_root, image_path.stem, result)
    return result


def analyze_batch(
    input_paths: list[Path],
    config: AppConfig,
    output_root: Path | None = None,
    save_debug: bool | None = None,
    event_callback: Callable[[AnalysisEvent], None] | None = None,
) -> list[AnalysisResult]:
    return [
        analyze_image(path, config, output_root=output_root, save_debug=save_debug, event_callback=event_callback)
        for path in input_paths
    ]


def _needs_people_modules(config: AppConfig, yolo_data: dict[str, object]) -> bool:
    if not (config.pipeline.enable_pose or config.pipeline.enable_face or config.pipeline.enable_segmentation):
        return False
    labels = [item.get("label") for item in yolo_data.get("detections", []) if isinstance(item, dict)]
    return "person" in labels


def _build_objects(
    yolo_data: dict[str, object],
    width: int,
    height: int,
    color_data: dict[str, object],
) -> list[ObjectRecord]:
    colors = color_data.get("dominant_colors", [])
    results: list[ObjectRecord] = []
    for item in yolo_data.get("detections", []):
        if not isinstance(item, dict):
            continue
        bbox = BoundingBox(**item["bbox_px"])
        attributes = {}
        if colors:
            first = colors[0]
            attributes["dominant_color"] = MeasuredField(
                value=first.get("name", "unknown"),
                provenance=str(first.get("provenance", "color")),
                confidence=float(first.get("confidence", 0.5)),
            )
        results.append(
            ObjectRecord(
                label=str(item["label"]),
                bbox_px=bbox,
                bbox_norm=normalize_bbox(bbox, width, height),
                confidence=float(item["confidence"]),
                attributes=attributes,
            )
        )
    return results


def _build_people(objects: list[ObjectRecord], mediapipe_data: dict[str, object]) -> list[PersonRecord]:
    results: list[PersonRecord] = []
    pose_data = mediapipe_data.get("pose", {}) if isinstance(mediapipe_data, dict) else {}
    for index, item in enumerate(objects, start=1):
        if item.label != "person":
            continue
        facing_direction = "frontal or unclear"
        if item.bbox_px.x2 - item.bbox_px.x1 > item.bbox_px.y2 - item.bbox_px.y1:
            facing_direction = "sideways or seated"
        results.append(
            PersonRecord(
                id=f"person_{index}",
                bbox_px=item.bbox_px,
                bbox_norm=item.bbox_norm,
                pose_angles_deg={},
                landmarks={},
                facing_direction=MeasuredField(
                    value=facing_direction,
                    provenance="yolo+heuristic",
                    confidence=0.25 if pose_data else 0.2,
                ),
                gesture_hints=[],
            )
        )
    return results


def _build_faces(mediapipe_data: dict[str, object], width: int, height: int) -> list[FaceRecord]:
    del width, height
    face_data = mediapipe_data.get("face", {}) if isinstance(mediapipe_data, dict) else {}
    detections = face_data.get("face_landmarks", []) if isinstance(face_data, dict) else []
    results: list[FaceRecord] = []
    for index, _item in enumerate(detections, start=1):
        bbox = BoundingBox(x1=0, y1=0, x2=0, y2=0)
        results.append(
            FaceRecord(
                id=f"face_{index}",
                bbox_px=bbox,
                bbox_norm=NormalizedBoundingBox(x1=0.0, y1=0.0, x2=0.0, y2=0.0),
                landmarks={},
                blendshapes={},
                inferred_expression=MeasuredField(
                    value="face detected but expression not resolved",
                    provenance="mediapipe",
                    confidence=0.2,
                ),
            )
        )
    return results


def _build_text_regions(ocr_data: dict[str, object], width: int, height: int) -> list[TextRegion]:
    text = str(ocr_data.get("ocr_text", "")).strip()
    if not text:
        return []
    bbox = BoundingBox(x1=0, y1=0, x2=width, y2=height)
    return [
        TextRegion(
            text=text,
            bbox_px=bbox,
            bbox_norm=normalize_bbox(bbox, width, height),
            confidence=0.35,
            provenance="tesseract",
        )
    ]


def _build_regions(color_data: dict[str, object], width: int, height: int) -> list[RegionRecord]:
    colors = color_data.get("dominant_colors", [])
    if not colors:
        return []
    bbox = BoundingBox(x1=0, y1=0, x2=width, y2=height)
    return [
        RegionRecord(
            id="full_image",
            label="full_image",
            bbox_px=bbox,
            bbox_norm=normalize_bbox(bbox, width, height),
            dominant_colors=[
                MeasuredField(
                    value={"name": item.get("name"), "rgb": item.get("rgb")},
                    provenance=str(item.get("provenance", "color")),
                    confidence=float(item.get("confidence", 0.5)),
                )
                for item in colors
                if isinstance(item, dict)
            ],
        )
    ]


def _extract_short_caption(florence_data: dict[str, object]) -> str:
    caption = florence_data.get("caption")
    if isinstance(caption, dict):
        if caption:
            return next(iter(caption.values())) if isinstance(next(iter(caption.values())), str) else str(caption)
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    return "Image analyzed with measured-first fallback pipeline."


def _scene_category(objects: list[ObjectRecord]) -> str:
    labels = {item.label for item in objects}
    if "person" in labels:
        return "person-centric scene"
    if labels:
        return "object-centric scene"
    return "unclassified scene"


def _fallback_description(
    short_caption: str,
    objects: list[ObjectRecord],
    text_regions: list[TextRegion],
    scene: SceneSummary,
) -> str:
    object_labels = ", ".join(item.label for item in objects) or "no confident objects"
    text_note = text_regions[0].text[:120] if text_regions else "no OCR text"
    return (
        f"{short_caption} Scene type: {scene.category}. "
        f"Detected objects: {object_labels}. OCR: {text_note}."
    )


def _build_description_layers(
    image_name: str,
    short_caption: str,
    long_description: str,
    objects: list[ObjectRecord],
    people: list[PersonRecord],
    faces: list[FaceRecord],
    text_regions: list[TextRegion],
    regions: list[RegionRecord],
    scene: SceneSummary,
    uncertainties: list[UncertaintyRecord],
) -> list[DescriptionLayer]:
    object_summary = ", ".join(sorted({item.label for item in objects})) or "no confident objects"
    color_summary = _format_color_summary(regions)
    ocr_summary = " | ".join(item.text.strip() for item in text_regions if item.text.strip()) or "No OCR text detected."
    people_summary = (
        "; ".join(
            f"{person.id}: {person.facing_direction.value if person.facing_direction else 'orientation unclear'}"
            for person in people
        )
        or "No people-specific pose signals were produced."
    )
    face_summary = (
        "; ".join(
            face.inferred_expression.value if face.inferred_expression else f"{face.id}: expression unresolved"
            for face in faces
        )
        or "No face-specific expression signals were produced."
    )
    uncertainty_summary = (
        "; ".join(f"{item.source}: {item.message}" for item in uncertainties)
        or "No provider warnings were reported."
    )

    layer_specs = [
        (
            "summary",
            "Summary",
            f"{short_caption}\n\nDetected scene: {scene.category}. Main objects: {object_summary}.",
        ),
        (
            "detailed_description",
            "Detailed Description",
            long_description,
        ),
        (
            "colors_and_materials",
            "Colors And Materials",
            f"Dominant colors: {color_summary}\n\nObjects contributing context: {object_summary}.",
        ),
        (
            "composition_and_camera",
            "Composition And Camera",
            (
                f"Scene framing: {scene.category}. "
                f"Detected objects suggest the composition centers on {object_summary}. "
                f"People analysis: {people_summary}."
            ),
        ),
        (
            "emotion_style_or_intent",
            "Emotion Style Or Intent",
            (
                f"People cues: {people_summary}\n"
                f"Face cues: {face_summary}\n"
                f"Uncertainty notes: {uncertainty_summary}"
            ),
        ),
        (
            "ocr_and_context",
            "OCR And Context",
            f"OCR findings: {ocr_summary}\n\nScene category: {scene.category}.",
        ),
    ]
    return [
        DescriptionLayer(
            key=key,
            title=title,
            text=text.strip(),
            file_name=f"{image_name}_desc_{index}.txt",
        )
        for index, (key, title, text) in enumerate(layer_specs, start=1)
    ]


def _format_color_summary(regions: list[RegionRecord]) -> str:
    if not regions:
        return "No dominant color information detected."
    colors: list[str] = []
    for region in regions:
        for field in region.dominant_colors:
            value = field.value if isinstance(field.value, dict) else {"name": field.value}
            name = value.get("name", "unknown")
            rgb = value.get("rgb")
            if rgb:
                colors.append(f"{name} {tuple(rgb)}")
            else:
                colors.append(str(name))
    return ", ".join(colors) if colors else "No dominant color information detected."


def _emit_event(
    events: list[AnalysisEvent],
    stage: str,
    status: str,
    message: str,
    payload: dict[str, object],
    event_callback: Callable[[AnalysisEvent], None] | None,
) -> AnalysisEvent:
    event = AnalysisEvent(
        timestamp=datetime.now(timezone.utc),
        stage=stage,
        status=status,
        message=message,
        payload=payload,
    )
    events.append(event)
    if event_callback is not None:
        event_callback(event)
    return event


def _record_provider(
    events: list[AnalysisEvent],
    provider_name: str,
    artifact: object,
    event_callback: Callable[[AnalysisEvent], None] | None,
) -> None:
    warnings = getattr(artifact, "warnings", [])
    data = getattr(artifact, "data", {})
    status = "warning" if warnings else "completed"
    message = (
        f"{provider_name} finished with warnings."
        if warnings
        else f"{provider_name} finished successfully."
    )
    payload = {
        "warning_count": len(warnings),
        "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
    }
    if warnings:
        payload["warnings"] = [str(item) for item in warnings]
    _emit_event(events, provider_name, status, message, payload, event_callback)


def _write_output_bundle(
    output_root: Path,
    stem: str,
    result: AnalysisResult,
    module_outputs: dict[str, object],
    save_debug: bool,
) -> None:
    bundle_dir = output_root / stem
    dump_json(bundle_dir / "details.json", result.model_dump(mode="json"))
    dump_text(bundle_dir / "description.txt", result.summary.long_description)
    dump_json(bundle_dir / "events.json", [event.model_dump(mode="json") for event in result.orchestration_events])
    dump_json(
        bundle_dir / "layers.json",
        [layer.model_dump() for layer in result.description_layers],
    )
    for layer in result.description_layers:
        dump_text(bundle_dir / layer.file_name, layer.text + "\n")
    if save_debug:
        dump_json(bundle_dir / "module_outputs.json", module_outputs)


def _rewrite_event_bundle(output_root: Path, stem: str, result: AnalysisResult) -> None:
    bundle_dir = output_root / stem
    dump_json(bundle_dir / "details.json", result.model_dump(mode="json"))
    dump_json(bundle_dir / "events.json", [event.model_dump(mode="json") for event in result.orchestration_events])
