from __future__ import annotations

from pathlib import Path

from video_scene_summarizer.cli.interactive import _ask_bool, _ask_optional_float, configure_models_interactively, print_result_summary
from video_scene_summarizer.config.settings import load_settings
from video_scene_summarizer.graph.workflow import run_analysis_stage
from video_scene_summarizer.utils.logging_utils import configure_logging


def run_analysis_only_interactive(project_root: Path) -> None:
    config = load_settings(project_root)
    configure_logging(config.log_dir, "analysis_stage.log")

    input_dir = input(f"Input video folder [{config.downloads_dir}]: ").strip() or str(config.downloads_dir)
    output_root = input(f"Analysis output folder [{config.output_dir}]: ").strip() or str(config.output_dir)
    keep_downloaded = _ask_bool("Keep original videos after successful analysis?", True)
    use_fusion = _ask_bool("Use transcript fusion?", config.transcript_fusion_default)
    reuse_cache = _ask_bool("Reuse cached scene/frame/transcript data?", True)
    skip_existing = _ask_bool("Skip videos that already have final outputs?", True)
    use_frame_shaving = _ask_bool("Use frame shaving to drop repetitive frames?", config.use_frame_shaving_default)
    extract_fps = _ask_optional_float("Target extracted frame rate per scene", config.extract_fps or config.analysis_fps)
    use_scene_compaction = _ask_bool("Use small LLM to compact each scene report?", config.use_compaction_default)
    delete_frame_images = _ask_bool("Delete saved frame images after all analysis is complete?", config.delete_frames_after_analysis_default)
    configure_models_interactively(config)

    result = run_analysis_stage(
        config=config,
        input_dir=Path(input_dir),
        output_root=Path(output_root),
        keep_downloaded_videos=keep_downloaded,
        use_transcript_fusion=use_fusion,
        reuse_cache=reuse_cache,
        skip_existing=skip_existing,
        use_frame_shaving=use_frame_shaving,
        extract_fps=extract_fps,
        use_scene_compaction=use_scene_compaction,
        delete_frame_images=delete_frame_images,
    )
    print_result_summary(result)
