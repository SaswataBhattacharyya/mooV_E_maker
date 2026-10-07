from __future__ import annotations

from pathlib import Path

from video_scene_summarizer.config.settings import load_settings
from video_scene_summarizer.graph.workflow import run_full_pipeline
from video_scene_summarizer.utils.logging_utils import configure_logging


def _ask_bool(prompt: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "true", "1"}


def configure_models_interactively(config) -> None:
    print(f"Default visual model: {config.visual_model_name}")
    print(f"Default structuring model: {config.structuring_model_name}")
    print(f"Default compact scene model: {config.compact_text_model_name}")
    print(f"Default text model: {config.text_model_name}")
    print(f"Default Whisper model: {config.whisper_model}")
    use_defaults = _ask_bool("Use default model choices?", True)
    if not use_defaults:
        visual_model = input(f"Visual model path [{config.visual_model_path}]: ").strip()
        structuring_model = input(f"Structuring model path [{config.structuring_model_path}]: ").strip()
        compact_model = input(f"Compact scene model path [{config.compact_text_model_path}]: ").strip()
        text_model = input(f"Text model path [{config.text_model_path}]: ").strip()
        whisper_model = input(f"Whisper model [{config.whisper_model}]: ").strip()
        if visual_model:
            config.visual_model_path = visual_model
        if structuring_model:
            config.structuring_model_path = structuring_model
        if compact_model:
            config.compact_text_model_path = compact_model
        if text_model:
            config.text_model_path = text_model
        if whisper_model:
            config.whisper_model = whisper_model


def _ask_optional_float(prompt: str, default: float | None) -> float | None:
    if default is None:
        value = input(f"{prompt} [source fps]: ").strip()
    else:
        value = input(f"{prompt} [{default}]: ").strip()
    if not value:
        return default
    return float(value)


def print_result_summary(result: dict) -> None:
    print("\nProcessing complete.")
    print(f"Processed videos: {len(result.get('processed_videos', []))}")
    if result.get("skipped_videos"):
        print(f"Skipped videos: {len(result['skipped_videos'])}")
        for item in result["skipped_videos"]:
            print(f"- skipped: {item}")
    if result.get("errors"):
        print("Errors:")
        for err in result["errors"]:
            print(f"- {err}")


def run_interactive(project_root: Path) -> None:
    config = load_settings(project_root)
    configure_logging(config.log_dir, "combined_pipeline.log")
    query = input("Text query: ").strip()
    count = int(input("Number of videos to process: ").strip())
    output_root = input(f"Output root directory [{config.output_dir}]: ").strip() or str(config.output_dir)
    keep_downloaded = _ask_bool("Keep downloaded videos after successful processing?", True)
    use_fusion = _ask_bool("Use transcript fusion?", config.transcript_fusion_default)
    reuse_cache = _ask_bool("Reuse cached scene/frame/transcript data?", True)
    use_frame_shaving = _ask_bool("Use frame shaving to drop repetitive frames?", config.use_frame_shaving_default)
    extract_fps = _ask_optional_float("Target extracted frame rate per scene", config.extract_fps or config.analysis_fps)
    use_scene_compaction = _ask_bool("Use small LLM to compact each scene report?", config.use_compaction_default)
    delete_frame_images = _ask_bool("Delete saved frame images after all analysis is complete?", config.delete_frames_after_analysis_default)
    configure_models_interactively(config)

    result = run_full_pipeline(
        config,
        {
            "source_query": query,
            "requested_video_count": count,
            "output_root": output_root,
            "keep_downloaded_videos": keep_downloaded,
            "use_transcript_fusion": use_fusion,
            "reuse_cache": reuse_cache,
            "use_frame_shaving": use_frame_shaving,
            "extract_fps": extract_fps,
            "use_scene_compaction": use_scene_compaction,
            "delete_frame_images": delete_frame_images,
        }
    )
    print_result_summary(result)
