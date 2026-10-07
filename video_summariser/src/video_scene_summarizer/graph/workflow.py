from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from video_scene_summarizer.config.settings import AppConfig
from video_scene_summarizer.graph.state import WorkflowState
from video_scene_summarizer.io.downloader import download_video
from video_scene_summarizer.io.reporting import write_cache, write_video_outputs
from video_scene_summarizer.io.youtube_search import search_youtube_urls

from video_scene_summarizer.models.qwen_vl import OllamaTextGenerator, OllamaVisionAnalyzer, configure_ollama_runtime, probe_ollama_model

from video_scene_summarizer.models.schemas import BoundingBox, FrameAnalysis, FrameDelta, ObjectDelta, ObjectDetection, SceneBoundary, SceneTransition, TranscriptResult, TranscriptSegment, VideoRecord, VideoSummary
from video_scene_summarizer.processing.audio import VIDEO_EXTS, extract_mp3
from video_scene_summarizer.processing.frame_detail import (
    build_frame_analysis,
    build_frame_delta,
    estimate_scene_timestamps,
    select_scene_keyframes,
    stitch_scene_story,
    write_scene_analysis_bundle,
)
from video_scene_summarizer.processing.continuity import analyze_scene_transitions
from video_scene_summarizer.processing.scenes import build_scene_shells, detect_scene_boundaries
from video_scene_summarizer.processing.transcribe import load_whisper_model, transcribe_audio
from video_scene_summarizer.utils.files import append_unique_line, read_json, read_lines, safe_delete
from video_scene_summarizer.utils.text import dump_json, dump_text, sanitize_name


LOGGER = logging.getLogger(__name__)


def build_workflow(config: AppConfig):
    def run(initial_state: WorkflowState) -> WorkflowState:
        enriched = dict(initial_state)
        enriched["config"] = config
        return run_full_pipeline(config, enriched)

    return run


def run_full_pipeline(
    config: AppConfig,
    initial_state: WorkflowState,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> WorkflowState:
    state = dict(initial_state)
    state["config"] = config
    state["event_callback"] = event_callback
    return _run_nodes(
        state,
        _query_intake,
        _url_search,
        _url_dedup,
        _download_queue,
        _audio_extraction,
        _transcription,
        _scene_detection,
        _visual_analysis,
        _cross_scene_analysis,
        _video_summary_generation,
        _report_writing,
        _cleanup,
    )


def run_download_stage(
    config: AppConfig,
    source_query: str,
    requested_video_count: int,
    download_root: Path,
) -> WorkflowState:
    return _run_nodes(
        {
            "config": config,
            "source_query": source_query,
            "requested_video_count": requested_video_count,
            "download_root": str(download_root),
            "errors": [],
            "processed_videos": [],
            "skipped_videos": [],
        },
        _url_search,
        _url_dedup,
        _download_queue,
    )


def run_analysis_stage(
    config: AppConfig,
    input_dir: Path,
    output_root: Path,
    keep_downloaded_videos: bool,
    use_transcript_fusion: bool,
    reuse_cache: bool,
    source_query: str = "local video analysis",
    skip_existing: bool = True,
    use_frame_shaving: bool = False,
    extract_fps: float | None = None,
    use_scene_compaction: bool = False,
    delete_frame_images: bool = False,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> WorkflowState:
    queued_videos, skipped_videos = _collect_local_video_records(input_dir, output_root, source_query, skip_existing)
    return _run_nodes(
        {
            "config": config,
            "source_query": source_query,
            "requested_video_count": len(queued_videos),
            "queued_videos": queued_videos,
            "processed_videos": [],
            "output_root": str(output_root),
            "keep_downloaded_videos": keep_downloaded_videos,
            "use_transcript_fusion": use_transcript_fusion,
            "reuse_cache": reuse_cache,
            "use_frame_shaving": use_frame_shaving,
            "extract_fps": extract_fps,
            "use_scene_compaction": use_scene_compaction,
            "delete_frame_images": delete_frame_images,
            "errors": [],
            "skipped_videos": skipped_videos,
            "event_callback": event_callback,
        },
        _query_intake,
        _audio_extraction,
        _transcription,
        _scene_detection,
        _visual_analysis,
        _cross_scene_analysis,
        _video_summary_generation,
        _report_writing,
        _cleanup,
    )


def _run_nodes(initial_state: WorkflowState, *nodes) -> WorkflowState:
    current = dict(initial_state)
    current.setdefault("errors", [])
    current.setdefault("processed_videos", [])
    current.setdefault("queued_videos", [])
    current.setdefault("skipped_videos", [])
    for node in nodes:
        current = node(current)
    return current


def _query_intake(state: WorkflowState) -> WorkflowState:
    config = state["config"]
    configure_ollama_runtime(config.ollama_max_loaded_models, config.ollama_num_parallel, config.ollama_keep_alive)
    LOGGER.info(
        "Preparing direct Ollama model | visual_model=%s | structuring_model=%s | text_model=%s | whisper_model=%s",
        config.visual_model_path,
        config.structuring_model_path,
        config.text_model_path,
        config.whisper_model,
    )

    preflight = probe_ollama_model(config.ollama_base_url, config.visual_model_path, timeout_sec=min(config.ollama_timeout_sec, 30))
    state["model_preflight"] = preflight
    if not preflight["ready"]:
        raise RuntimeError(preflight["error"])
    client_args = {"base_url": config.ollama_base_url, "model_name": config.visual_model_path,
                   "max_new_tokens": config.llm_max_new_tokens, "timeout_sec": config.ollama_timeout_sec,
                   "keep_alive": config.ollama_keep_alive}
    state["visual_analyzer"] = OllamaVisionAnalyzer(**client_args)
    state["text_generator"] = OllamaTextGenerator(**client_args)
    state["compact_text_generator"] = OllamaTextGenerator(**client_args)
    state["structuring_generator"] = OllamaTextGenerator(**client_args)

    try:
        state["whisper_model"] = load_whisper_model(config.whisper_model)
        LOGGER.info("Whisper model ready | model=%s", config.whisper_model)
    except Exception as exc:
        _record_error(
            state,
            "model_setup",
            f"Whisper model load failed: {exc}",
            {"whisper_model": config.whisper_model},
        )
        state["whisper_model"] = None
    _emit_event(state, "model_setup", "completed", "Loaded direct Ollama clients and Whisper model.", {"model": config.visual_model_path})
    return state


def _url_search(state: WorkflowState) -> WorkflowState:
    candidates = search_youtube_urls(state["source_query"], state["requested_video_count"] * 2)
    for item in candidates:
        append_unique_line(state["config"].url_list_path, item["url"])
    state["candidate_urls"] = candidates
    return state


def _url_dedup(state: WorkflowState) -> WorkflowState:
    downloaded = set(read_lines(state["config"].down_url_list_path))
    queued: list[VideoRecord] = []
    for item in state.get("candidate_urls", []):
        if item["url"] in downloaded:
            continue
        record = VideoRecord(
            source_query=state["source_query"],
            source_url=item["url"],
            video_id=item["video_id"],
            title=item["title"],
            sanitized_name=sanitize_name(item["title"] or item["video_id"] or "video"),
        )
        queued.append(record)
        if len(queued) >= state["requested_video_count"]:
            break
    state["queued_videos"] = queued
    return state


def _download_queue(state: WorkflowState) -> WorkflowState:
    processed: list[VideoRecord] = []
    download_root = Path(state.get("download_root") or state["config"].downloads_dir)
    for record in state.get("queued_videos", []):
        try:
            LOGGER.info("Downloading video | url=%s", record.source_url)
            video_path, metadata = download_video(record.source_url, download_root)
            record.video_path = video_path
            record.metadata = metadata
            append_unique_line(state["config"].down_url_list_path, record.source_url)
            processed.append(record)
            LOGGER.info("Download complete | video=%s", video_path.name)
        except Exception as exc:
            record.error = f"Download failed: {exc}"
            _record_error(
                state,
                "download",
                f"Download failed for {record.source_url}: {exc}",
                {"video": record.title, "source_url": record.source_url},
            )
            processed.append(record)
    state["queued_videos"] = processed
    return state


def _audio_extraction(state: WorkflowState) -> WorkflowState:
    for record in state.get("queued_videos", []):
        if record.error or not record.video_path:
            continue
        try:
            LOGGER.info("Audio extraction started | video=%s", record.video_path.name)
            record.audio_path = extract_mp3(record.video_path, state["config"].transcripts_dir)
            LOGGER.info("Audio extraction complete | video=%s | audio=%s", record.video_path.name, record.audio_path.name)
            _emit_event(state, "audio_extraction", "completed", f"Extracted audio for {record.title}.", {"video": record.title})
        except Exception as exc:
            record.error = f"Audio extraction failed: {exc}"
            _record_error(
                state,
                "audio_extraction",
                f"Audio extraction failed for {record.title}: {exc}",
                {"video": record.title, "video_path": str(record.video_path)},
            )
    return state


def _transcription(state: WorkflowState) -> WorkflowState:
    for record in state.get("queued_videos", []):
        if record.error or not record.audio_path:
            continue
        transcript_cache = state["config"].cache_dir / record.sanitized_name / "transcript.json"
        if state["reuse_cache"] and transcript_cache.exists():
            cached = _load_transcript_cache(transcript_cache)
            record.metadata["detected_language"] = cached.language
            LOGGER.info("Using cached transcript | video=%s | language=%s", record.title, cached.language)
            continue
        if state.get("whisper_model") is None:
            _emit_event(
                state,
                "transcription",
                "error",
                f"Skipping transcription for {record.title} because the Whisper model is unavailable.",
                {"video": record.title},
            )
            continue
        try:
            LOGGER.info("Transcription started | video=%s", record.title)
            transcript = transcribe_audio(record.audio_path, state["whisper_model"])
            record.transcript_path = transcript_cache
            write_cache(state["config"].cache_dir, record, "transcript.json", transcript.to_dict())
            record.metadata["detected_language"] = transcript.language
            LOGGER.info(
                "Transcription complete | video=%s | language=%s | transcript_chars=%s",
                record.title,
                transcript.language,
                len(transcript.text),
            )
            _emit_event(state, "transcription", "completed", f"Transcribed {record.title}.", {"video": record.title, "language": transcript.language})
        except Exception as exc:
            record.error = f"Transcription failed: {exc}"
            _record_error(
                state,
                "transcription",
                f"Transcription failed for {record.title}: {exc}",
                {"video": record.title, "audio_path": str(record.audio_path)},
            )
    return state


def _scene_detection(state: WorkflowState) -> WorkflowState:
    for record in state.get("queued_videos", []):
        if record.error or not record.video_path:
            continue
        try:
            transcript_cache = state["config"].cache_dir / record.sanitized_name / "transcript.json"
            transcript = _load_transcript_cache(transcript_cache) if transcript_cache.exists() else None
            boundaries_cache = state["config"].cache_dir / record.sanitized_name / "scene_boundaries.json"
            target_scene_root = Path(state["output_root"]) / record.sanitized_name / "scenes"
            if state["reuse_cache"] and boundaries_cache.exists():
                scenes = _load_scene_cache(boundaries_cache)
                if scenes and all(Path(scene.scene_dir_path).exists() for scene in scenes):
                    LOGGER.info("Using cached scene boundaries | video=%s | scenes=%s", record.title, len(scenes))
                else:
                    scenes = []
            else:
                scenes = []
            if not scenes:
                LOGGER.info(
                    "Cut detection started | video=%s | threshold=%s | min_scene_length_sec=%s",
                    record.title,
                    state["config"].scene_detector_threshold,
                    state["config"].min_scene_length_sec,
                )
                scene_spans = detect_scene_boundaries(
                    record.video_path,
                    threshold=state["config"].scene_detector_threshold,
                    min_scene_length_sec=state["config"].min_scene_length_sec,
                )
                scenes = build_scene_shells(
                    video_path=record.video_path,
                    scene_spans=scene_spans,
                    transcript=transcript,
                    output_root=target_scene_root,
                    sample_count=state["config"].frame_samples_per_scene,
                    extract_fps=state.get("extract_fps") or state["config"].analysis_fps,
                )
                write_cache(state["config"].cache_dir, record, "scene_boundaries.json", [scene.to_dict() for scene in scenes])
                LOGGER.info("Cut detection complete | video=%s | scenes=%s", record.title, len(scenes))
            record.metadata["scene_count"] = len(scenes)
            record.metadata["_scenes"] = scenes
            _emit_event(state, "scene_detection", "completed", f"Detected {len(scenes)} scenes for {record.title}.", {"video": record.title, "scene_count": len(scenes)})
        except Exception as exc:
            record.error = f"Scene detection failed: {exc}"
            _record_error(
                state,
                "scene_detection",
                f"Scene detection failed for {record.title}: {exc}",
                {"video": record.title, "video_path": str(record.video_path)},
            )
    return state


def _visual_analysis(state: WorkflowState) -> WorkflowState:
    for record in state.get("queued_videos", []):
        scenes: list[SceneBoundary] = record.metadata.get("_scenes", [])
        if record.error or not scenes:
            continue
        cache_file = state["config"].cache_dir / record.sanitized_name / "scene_analysis.json"
        if state["reuse_cache"] and cache_file.exists():
            record.metadata["_scenes"] = _load_scene_cache(cache_file)
            LOGGER.info("Using cached scene analysis | video=%s | scenes=%s", record.title, len(scenes))
            continue

        LOGGER.info("Enhanced scene analysis started | video=%s | scenes=%s", record.title, len(scenes))
        for scene in scenes:
            _emit_event(state, "scene_analysis", "running", f"Analyzing {record.title} {scene.scene_id}.", {"video": record.title, "scene_id": scene.scene_id})
            scene.raw_scene_text_path = scene.raw_scene_text_path or str(Path(scene.scene_dir_path) / f"{scene.scene_id}_raw.txt")
            scene.compact_scene_text_path = scene.compact_scene_text_path or str(Path(scene.scene_dir_path) / f"{scene.scene_id}.txt")
            scene.scene_text_path = scene.compact_scene_text_path
            scene.scene_story_json_path = str(Path(scene.scene_dir_path) / "analysis" / "scene_story.json")
            scene.scene_story_text_path = str(Path(scene.scene_dir_path) / "analysis" / "scene_story.txt")
            keyframe_paths = select_scene_keyframes(scene, state["config"], state.get("use_frame_shaving", False))
            scene.selected_frame_paths = keyframe_paths[:]
            scene.keyframe_paths = keyframe_paths[:]
            _emit_event(
                state,
                "scene_preview",
                "completed",
                f"Prepared preview for {record.title} {scene.scene_id}.",
                {
                    "video": record.title,
                    "scene_id": scene.scene_id,
                    "scene_start": scene.start_time_hms,
                    "scene_end": scene.end_time_hms,
                    "preview_image": keyframe_paths[0] if keyframe_paths else "",
                },
            )
            if not keyframe_paths:
                scene.scene_story_text = "No keyframes were extracted for this scene."
                scene.scene_compiled_text = scene.scene_story_text
                dump_text(Path(scene.raw_scene_text_path), scene.scene_story_text)
                dump_text(Path(scene.compact_scene_text_path), scene.scene_compiled_text)
                continue
            timestamp_map = estimate_scene_timestamps(scene, keyframe_paths)
            scene.keyframe_analyses = []
            scene.frame_deltas = []

            for index, frame_path in enumerate(keyframe_paths, start=1):
                frame_id = f"frame_{index:04d}"
                frame_analysis = build_frame_analysis(
                    frame_path=frame_path,
                    frame_id=frame_id,
                    timestamp_sec=timestamp_map.get(frame_path, scene.start_time_sec),
                    transcript_text=scene.transcript_text if state["use_transcript_fusion"] else "",
                    scene=scene,
                    config=state["config"],
                    visual_analyzer=state["visual_analyzer"],
                )
                scene.keyframe_analyses.append(frame_analysis)
                for warning in frame_analysis.warnings:
                    scene.confidence_notes.append(warning)
                    _emit_event(
                        state,
                        "provider_warning",
                        "warning",
                        f"{scene.scene_id} {frame_id}: {warning}",
                        {
                            "video": record.title,
                            "scene_id": scene.scene_id,
                            "frame_id": frame_id,
                            "warning": warning,
                        },
                    )
                _emit_event(
                    state,
                    "keyframe_analysis",
                    "completed",
                    f"Built full analysis for {scene.scene_id} {frame_id}.",
                    {
                        "video": record.title,
                        "scene_id": scene.scene_id,
                        "frame_id": frame_id,
                        "frame_path": frame_path,
                        "timestamp_sec": frame_analysis.timestamp_sec,
                        "summary": frame_analysis.concise_summary,
                    },
                )
                if index > 1:
                    delta = build_frame_delta(
                        previous_analysis=scene.keyframe_analyses[index - 2],
                        current_analysis=frame_analysis,
                        transcript_text=scene.transcript_text if state["use_transcript_fusion"] else "",
                        visual_analyzer=state["visual_analyzer"],
                    )
                    scene.frame_deltas.append(delta)
                    _emit_event(
                        state,
                        "frame_delta",
                        "completed",
                        f"Compared {delta.previous_frame_id} to {delta.current_frame_id} in {scene.scene_id}.",
                        {
                            "video": record.title,
                            "scene_id": scene.scene_id,
                            "pair_id": delta.pair_id,
                            "change_score": delta.change_score,
                            "delta_summary": delta.natural_language_delta,
                        },
                    )

            story = stitch_scene_story(
                scene=scene,
                structuring_generator=state["structuring_generator"],
                use_transcript_fusion=state["use_transcript_fusion"],
            )
            scene.scene_story_text = story.scene_text
            raw_scene_text = story.raw_scene_text
            scene.frame_text_chunks = [analysis.detailed_description for analysis in scene.keyframe_analyses]
            scene.scene_compiled_text = story.scene_text
            scene.visual_description = scene.keyframe_analyses[0].concise_summary if scene.keyframe_analyses else ""
            write_scene_analysis_bundle(scene)
            dump_json(Path(scene.scene_story_json_path), story.to_dict())
            dump_text(Path(scene.scene_story_text_path), story.scene_text)
            dump_text(Path(scene.raw_scene_text_path), raw_scene_text)
            if state.get("use_scene_compaction") and scene.scene_compiled_text:
                compact_prompt = (
                    "Compress this scene explanation into a practical searchable scene summary.\n"
                    "Preserve the temporal order and visible actions."
                )
                compact_text = state["compact_text_generator"].generate(
                    prompt=compact_prompt,
                    transcript_text=scene.transcript_text if state["use_transcript_fusion"] else "",
                    structured_context=scene.scene_compiled_text,
                ).strip()
                if compact_text:
                    scene.scene_compiled_text = compact_text
            dump_text(Path(scene.compact_scene_text_path), scene.scene_compiled_text)
            scene.keywords = _extract_keywords(scene.scene_compiled_text)
            LOGGER.info(
                "Scene complete | video=%s | scene=%s | keyframes=%s | deltas=%s",
                record.title,
                scene.scene_id,
                len(scene.keyframe_analyses),
                len(scene.frame_deltas),
            )

        write_cache(state["config"].cache_dir, record, "scene_analysis.json", [scene.to_dict() for scene in scenes])
        LOGGER.info("Enhanced scene analysis complete | video=%s", record.title)
        _emit_event(state, "scene_analysis", "completed", f"Finished scene analysis for {record.title}.", {"video": record.title, "scene_count": len(scenes)})
    return state


def _video_summary_generation(state: WorkflowState) -> WorkflowState:
    prompt = (
        "You are compiling a final structured summary of a video.\n"
        "You will receive metadata, scene-by-scene stitched visual text, a stitched full-video text, and an audio transcript.\n"
        "Explain the overall flow of the video clearly. Respect scene order and audio timing.\n"
        "Keep the output factual, practical, and searchable."
    )
    processed_videos: list[VideoRecord] = []
    for record in state.get("queued_videos", []):
        scenes: list[SceneBoundary] = record.metadata.get("_scenes", [])
        if record.error or not scenes:
            processed_videos.append(record)
            continue

        transcript_cache = state["config"].cache_dir / record.sanitized_name / "transcript.json"
        transcript = _load_transcript_cache(transcript_cache) if transcript_cache.exists() else None
        metadata_payload = {
            "video_title": record.title,
            "video_path": str(record.video_path) if record.video_path else None,
            "audio_path": str(record.audio_path) if record.audio_path else None,
            "scene_count": len(scenes),
            "detected_language": transcript.language if transcript else record.metadata.get("detected_language", "unknown"),
            "scenes": [
                {
                    "scene_id": scene.scene_id,
                    "start_time_sec": scene.start_time_sec,
                    "end_time_sec": scene.end_time_sec,
                    "duration_sec": scene.duration_sec,
                    "keyframe_count": len(scene.keyframe_analyses),
                    "delta_count": len(scene.frame_deltas),
                }
                for scene in scenes
            ],
        }
        video_scene_text = "\n\n".join(
            f"{scene.scene_id} [{scene.start_time_hms} - {scene.end_time_hms}]\n{scene.scene_compiled_text}".strip()
            for scene in scenes
            if scene.scene_compiled_text.strip()
        )
        video_story_text = "\n\n".join(
            f"{scene.scene_id}\n{scene.scene_story_text or scene.scene_compiled_text}".strip()
            for scene in scenes
            if (scene.scene_story_text or scene.scene_compiled_text).strip()
        )
        audio_text = _format_audio_text(transcript)
        transitions: list[SceneTransition] = record.metadata.get("_scene_transitions", [])

        try:
            LOGGER.info("Final summary generation started | video=%s | model=%s", record.title, state["config"].text_model_path)
            fused_summary = state["text_generator"].generate(
                prompt=prompt,
                transcript_text=audio_text,
                structured_context=(
                    "METADATA JSON:\n"
                    f"{json.dumps(metadata_payload, ensure_ascii=False, indent=2)}\n\n"
                    "SCENE TEXT:\n"
                    f"{video_scene_text}\n\n"
                    "VIDEO STORY TEXT:\n"
                    f"{video_story_text}\n\n"
                    "CROSS-SCENE CONTINUITY JSON:\n"
                    f"{json.dumps([item.to_dict() for item in transitions], ensure_ascii=False, indent=2)}"
                ),
            )
            summary = VideoSummary(
                source_query=record.source_query,
                source_url=record.source_url,
                downloaded_video_path_or_deleted_flag=str(record.video_path) if record.video_path else "not_downloaded",
                detected_language=metadata_payload["detected_language"],
                number_of_scenes=len(scenes),
                ordered_scene_ids=[scene.scene_id for scene in scenes],
                brief_video_summary=fused_summary[:280].strip(),
                detailed_video_summary=fused_summary,
                continuity_map=[
                    {
                        "scene_id": scene.scene_id,
                        "start_time_sec": scene.start_time_sec,
                        "end_time_sec": scene.end_time_sec,
                    }
                    for scene in scenes
                ],
                main_entities=_extract_keywords(fused_summary)[:8],
                topics=_extract_keywords(video_scene_text)[:8],
                warnings_or_uncertainties=[scene.scene_id for scene in scenes if scene.confidence_notes],
                video_story_text=video_story_text,
                video_story_json_path=str(Path(state["output_root"]) / record.sanitized_name / "video_story.json"),
                scene_transitions=transitions,
            )
            record.metadata["_video_story_text"] = video_story_text
            record.metadata["_final_summary"] = summary
            LOGGER.info("Final summary generation complete | video=%s | output_chars=%s", record.title, len(fused_summary))
            _emit_event(state, "video_summary", "completed", f"Generated final summary for {record.title}.", {"video": record.title})
        except Exception as exc:
            record.error = f"Final summary generation failed: {exc}"
            _record_error(
                state,
                "video_summary",
                f"Final summary generation failed for {record.title}: {exc}",
                {"video": record.title},
            )
        processed_videos.append(record)

    state["processed_videos"] = processed_videos
    return state


def _cross_scene_analysis(state: WorkflowState) -> WorkflowState:
    for record in state.get("queued_videos", []):
        scenes: list[SceneBoundary] = record.metadata.get("_scenes", [])
        if record.error or len(scenes) < 2:
            record.metadata["_scene_transitions"] = []
            continue
        cache_file = state["config"].cache_dir / record.sanitized_name / "cross_scene_analysis.json"
        if state["reuse_cache"] and cache_file.exists():
            payload = read_json(cache_file, default=[]) or []
            transitions = [_scene_transition_from_dict(item) for item in payload if isinstance(item, dict)]
        else:
            _emit_event(state, "cross_scene_analysis", "running", f"Analyzing continuity for {record.title}.", {"scene_count": len(scenes)})
            transitions = analyze_scene_transitions(scenes, state["structuring_generator"], state["use_transcript_fusion"])
            write_cache(state["config"].cache_dir, record, "cross_scene_analysis.json", [item.to_dict() for item in transitions])
        record.metadata["_scene_transitions"] = transitions
        _emit_event(state, "cross_scene_analysis", "completed", f"Built {len(transitions)} adjacent-scene transitions for {record.title}.", {"transition_count": len(transitions)})
    return state


def _report_writing(state: WorkflowState) -> WorkflowState:
    for record in state.get("processed_videos", []):
        scenes: list[SceneBoundary] = record.metadata.get("_scenes", [])
        summary: VideoSummary | None = record.metadata.get("_final_summary")
        if record.error or not summary:
            continue
        transcript = None
        transcript_cache = state["config"].cache_dir / record.sanitized_name / "transcript.json"
        if transcript_cache.exists():
            transcript = _load_transcript_cache(transcript_cache)
        try:
            LOGGER.info("Writing output bundle | video=%s | output_root=%s", record.title, state["output_root"])
            write_video_outputs(Path(state["output_root"]), record, transcript, scenes, summary)
            record.processed = True
        except Exception as exc:
            record.error = f"Report writing failed: {exc}"
            _record_error(
                state,
                "report_writing",
                f"Report writing failed for {record.title}: {exc}",
                {"video": record.title, "output_root": str(state["output_root"])},
            )
    return state


def _cleanup(state: WorkflowState) -> WorkflowState:
    for record in state.get("processed_videos", []):
        if record.error or not record.processed or state["keep_downloaded_videos"] or not record.video_path:
            continue
        safe_delete(record.video_path)
        record.deleted_video = True
        summary = record.metadata.get("_final_summary")
        if summary:
            summary.downloaded_video_path_or_deleted_flag = "deleted_after_success"
            final_summary_path = Path(state["output_root"]) / record.sanitized_name / "summary_video.json"
            dump_json(final_summary_path, summary.to_dict())
    if state.get("delete_frame_images"):
        for record in state.get("processed_videos", []):
            if record.error or not record.processed:
                continue
            scenes: list[SceneBoundary] = record.metadata.get("_scenes", [])
            for scene in scenes:
                scene_dir = Path(scene.scene_dir_path)
                if not scene_dir.exists():
                    continue
                for image_path in scene_dir.glob("*.jpg"):
                    safe_delete(image_path)
    return state


def _collect_local_video_records(
    input_dir: Path,
    output_root: Path,
    source_query: str,
    skip_existing: bool,
) -> tuple[list[VideoRecord], list[str]]:
    queued: list[VideoRecord] = []
    skipped: list[str] = []
    for video_path in sorted(input_dir.iterdir()):
        if not video_path.is_file() or video_path.suffix.lower() not in VIDEO_EXTS:
            continue
        sanitized_name = sanitize_name(video_path.stem)
        if skip_existing and _analysis_output_exists(output_root, sanitized_name):
            skipped.append(video_path.name)
            continue
        queued.append(
            VideoRecord(
                source_query=source_query,
                source_url=video_path.resolve().as_uri(),
                video_id=sanitized_name,
                title=video_path.stem,
                sanitized_name=sanitized_name,
                video_path=video_path,
                metadata={"local_video": True},
            )
        )
    return queued, skipped


def _analysis_output_exists(output_root: Path, sanitized_name: str) -> bool:
    return (output_root / sanitized_name / "summary_video.txt").exists()


def _format_audio_text(transcript: TranscriptResult | None) -> str:
    if not transcript:
        return ""
    segments_text = "\n".join(f"[{segment.start:.2f}-{segment.end:.2f}] {segment.text}" for segment in transcript.segments)
    return (
        f"Language: {transcript.language}\n\n"
        "Full Transcript:\n"
        f"{transcript.text}\n\n"
        "Timestamped Segments:\n"
        f"{segments_text}"
    ).strip()


def _extract_keywords(text: str) -> list[str]:
    words = [word.strip(".,:;!?()[]{}").lower() for word in text.split()]
    filtered = [word for word in words if len(word) > 4 and word.isascii()]
    seen: set[str] = set()
    result: list[str] = []
    for word in filtered:
        if word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result[:10]


def _load_transcript_cache(path: Path) -> TranscriptResult:
    cached = read_json(path, default={}) or {}
    return TranscriptResult(
        language=cached.get("language", "unknown"),
        text=cached.get("text", ""),
        segments=[
            TranscriptSegment(
                start=float(segment.get("start", 0.0)),
                end=float(segment.get("end", 0.0)),
                text=segment.get("text", ""),
            )
            for segment in cached.get("segments", [])
        ],
    )


def _load_scene_cache(path: Path) -> list[SceneBoundary]:
    payload = read_json(path, default=[]) or []
    scenes: list[SceneBoundary] = []
    for item in payload:
        scenes.append(_scene_from_dict(item))
    return scenes


def _scene_from_dict(item: dict[str, Any]) -> SceneBoundary:
    scene = SceneBoundary(
        scene_id=item["scene_id"],
        scene_number=int(item.get("scene_number", 0) or 0),
        start_time_sec=float(item["start_time_sec"]),
        end_time_sec=float(item["end_time_sec"]),
        duration_sec=float(item.get("duration_sec", float(item["end_time_sec"]) - float(item["start_time_sec"]))),
        start_time_hms=item["start_time_hms"],
        end_time_hms=item["end_time_hms"],
        representative_frame_paths=item.get("representative_frame_paths", []),
        selected_frame_paths=item.get("selected_frame_paths", item.get("representative_frame_paths", [])),
        keyframe_paths=item.get("keyframe_paths", item.get("selected_frame_paths", [])),
        frame_count=int(item.get("frame_count", 0)),
        scene_dir_path=item.get("scene_dir_path", ""),
        scene_text_path=item.get("scene_text_path", ""),
        raw_scene_text_path=item.get("raw_scene_text_path", ""),
        compact_scene_text_path=item.get("compact_scene_text_path", item.get("scene_text_path", "")),
        scene_story_json_path=item.get("scene_story_json_path", ""),
        scene_story_text_path=item.get("scene_story_text_path", ""),
        previous_scene_overlap_frame_path=item.get("previous_scene_overlap_frame_path", ""),
        scene_compiled_text=item.get("scene_compiled_text", ""),
        scene_story_text=item.get("scene_story_text", ""),
        frame_text_chunks=item.get("frame_text_chunks", []),
        transcript_text=item.get("transcript_text", ""),
        transcript_language=item.get("transcript_language", "unknown"),
        visual_description=item.get("visual_description", ""),
        previous_scene_context=item.get("previous_scene_context", ""),
        keywords=item.get("keywords", []),
        confidence_notes=item.get("confidence_notes", []),
        keyframe_analyses=[_frame_analysis_from_dict(entry) for entry in item.get("keyframe_analyses", []) if isinstance(entry, dict)],
        frame_deltas=[_frame_delta_from_dict(entry) for entry in item.get("frame_deltas", []) if isinstance(entry, dict)],
    )
    return scene


def _frame_analysis_from_dict(item: dict[str, Any]) -> FrameAnalysis:
    return FrameAnalysis(
        frame_id=item.get("frame_id", ""),
        frame_path=item.get("frame_path", ""),
        timestamp_sec=float(item.get("timestamp_sec", 0.0)),
        width=int(item.get("width", 0)),
        height=int(item.get("height", 0)),
        transcript_context=item.get("transcript_context", ""),
        overview_caption=item.get("overview_caption", ""),
        detailed_description=item.get("detailed_description", ""),
        concise_summary=item.get("concise_summary", ""),
        dominant_colors=item.get("dominant_colors", []),
        object_detections=[
            _object_detection_from_dict(entry)
            for entry in item.get("object_detections", [])
            if isinstance(entry, dict)
        ],
        florence_caption=item.get("florence_caption", ""),
        ocr_text=item.get("ocr_text", ""),
        support_signals=item.get("support_signals", {}),
        warnings=item.get("warnings", []),
        full_json_path=item.get("full_json_path", ""),
        full_text_path=item.get("full_text_path", ""),
    )


def _frame_delta_from_dict(item: dict[str, Any]) -> FrameDelta:
    return FrameDelta(
        pair_id=item.get("pair_id", ""),
        previous_frame_id=item.get("previous_frame_id", ""),
        current_frame_id=item.get("current_frame_id", ""),
        previous_frame_path=item.get("previous_frame_path", ""),
        current_frame_path=item.get("current_frame_path", ""),
        previous_timestamp_sec=float(item.get("previous_timestamp_sec", 0.0)),
        current_timestamp_sec=float(item.get("current_timestamp_sec", 0.0)),
        delta_time_sec=float(item.get("delta_time_sec", 0.0)),
        change_score=float(item.get("change_score", 0.0)),
        transcript_context=item.get("transcript_context", ""),
        natural_language_delta=item.get("natural_language_delta", ""),
        main_action=item.get("main_action", ""),
        secondary_motion=item.get("secondary_motion", []),
        camera_change=item.get("camera_change", ""),
        lighting_change=item.get("lighting_change", ""),
        new_objects=item.get("new_objects", []),
        removed_objects=item.get("removed_objects", []),
        object_changes=[_object_delta_from_dict(entry) for entry in item.get("object_changes", []) if isinstance(entry, dict)],
        uncertainty_notes=item.get("uncertainty_notes", []),
        delta_json_path=item.get("delta_json_path", ""),
        delta_text_path=item.get("delta_text_path", ""),
    )


def _scene_transition_from_dict(item: dict[str, Any]) -> SceneTransition:
    return SceneTransition(
        from_scene_id=str(item.get("from_scene_id", "")),
        to_scene_id=str(item.get("to_scene_id", "")),
        from_time_sec=float(item.get("from_time_sec", 0.0)),
        to_time_sec=float(item.get("to_time_sec", 0.0)),
        persistent_entities=[str(value) for value in item.get("persistent_entities", [])],
        appearing_entities=[str(value) for value in item.get("appearing_entities", [])],
        disappearing_entities=[str(value) for value in item.get("disappearing_entities", [])],
        location_change=str(item.get("location_change", "")),
        time_change=str(item.get("time_change", "")),
        visual_transition=str(item.get("visual_transition", "")),
        activity_change=str(item.get("activity_change", "")),
        narrative_connection=str(item.get("narrative_connection", "")),
        transcript_connection=str(item.get("transcript_connection", "")),
        evidence=[str(value) for value in item.get("evidence", [])],
        confidence=str(item.get("confidence", "unknown")),
        uncertainty_notes=[str(value) for value in item.get("uncertainty_notes", [])],
    )


def _object_detection_from_dict(item: dict[str, Any]) -> ObjectDetection:
    bbox = item.get("bbox_px", {})
    return ObjectDetection(
        label=item.get("label", ""),
        confidence=float(item.get("confidence", 0.0)),
        bbox_px=BoundingBox(
            x1=int(bbox.get("x1", 0)),
            y1=int(bbox.get("y1", 0)),
            x2=int(bbox.get("x2", 0)),
            y2=int(bbox.get("y2", 0)),
        ),
        provenance=item.get("provenance", ""),
    )


def _object_delta_from_dict(item: dict[str, Any]) -> ObjectDelta:
    previous_bbox = item.get("previous_bbox")
    current_bbox = item.get("current_bbox")
    return ObjectDelta(
        label=item.get("label", ""),
        previous_bbox=_bbox_from_dict(previous_bbox) if isinstance(previous_bbox, dict) else None,
        current_bbox=_bbox_from_dict(current_bbox) if isinstance(current_bbox, dict) else None,
        shift_px=tuple(item.get("shift_px", [0.0, 0.0])),
        confidence_delta=float(item.get("confidence_delta", 0.0)),
        semantic_change=item.get("semantic_change", ""),
    )


def _bbox_from_dict(item: dict[str, Any]) -> BoundingBox:
    return BoundingBox(
        x1=int(item.get("x1", 0)),
        y1=int(item.get("y1", 0)),
        x2=int(item.get("x2", 0)),
        y2=int(item.get("y2", 0)),
    )


def _emit_event(state: WorkflowState, stage: str, status: str, message: str, payload: dict[str, Any]) -> None:
    callback = state.get("event_callback")
    if callback is None:
        return
    callback(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "status": status,
            "message": message,
            "payload": payload,
        }
    )


def _record_error(state: WorkflowState, stage: str, message: str, payload: dict[str, Any]) -> None:
    LOGGER.error(message)
    state.setdefault("errors", []).append(message)
    _emit_event(state, stage, "error", message, payload)
