from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AppConfig:
    project_root: Path
    data_dir: Path
    output_dir: Path
    artifact_dir: Path
    log_dir: Path
    cache_dir: Path
    prompt_dir: Path
    downloads_dir: Path
    transcripts_dir: Path
    scenes_dir: Path
    url_list_path: Path
    down_url_list_path: Path
    scene_detector_threshold: float
    min_scene_length_sec: float
    frame_samples_per_scene: int
    frame_change_threshold: float
    large_change_threshold: float
    max_keyframes_per_scene: int
    min_keyframes_per_scene: int
    analysis_fps: float
    max_frames_per_vlm_call: int
    batch_overlap_frames: int
    extract_fps: float | None
    delete_frames_after_analysis_default: bool
    use_compaction_default: bool
    use_frame_shaving_default: bool
    transcript_fusion_default: bool
    whisper_model: str
    compact_text_model_name: str
    compact_text_model_path: str
    structuring_model_name: str
    structuring_model_path: str
    text_model_name: str
    text_model_path: str
    model_provider: str
    ollama_base_url: str
    ollama_timeout_sec: int
    ollama_max_loaded_models: int
    ollama_num_parallel: int
    ollama_keep_alive: str
    visual_model_name: str
    visual_model_path: str
    use_quantization: bool
    llm_max_new_tokens: int
    ui_host: str
    ui_port: int


def load_settings(project_root: Path) -> AppConfig:
    config_path = project_root / "configs" / "settings.yaml"
    payload: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    models = payload["models"]
    analysis_model = str(
        os.environ.get("VIDEO_SUMMARIZER_ANALYSIS_MODEL")
        or models.get("analysis_model_path")
        or models.get("visual_model_path")
        or models.get("text_model_path")
        or "qwen3.6:35b"
    )

    data_dir = project_root / payload["paths"]["data_dir"]
    output_dir = project_root / payload["paths"]["output_dir"]
    artifact_dir = project_root / payload["paths"].get("artifact_dir", "artifacts")
    log_dir = project_root / payload["paths"]["log_dir"]
    cache_dir = data_dir / "cache"
    downloads_dir = project_root / payload["paths"].get("downloads_dir", "data/downloads")
    transcripts_dir = project_root / payload["paths"].get("transcripts_dir", "data/transcripts")
    scenes_dir = project_root / payload["paths"].get("scenes_dir", "data/scenes")

    return AppConfig(
        project_root=project_root,
        data_dir=data_dir,
        output_dir=output_dir,
        artifact_dir=artifact_dir,
        log_dir=log_dir,
        cache_dir=cache_dir,
        prompt_dir=project_root / "configs" / "prompts",
        downloads_dir=downloads_dir,
        transcripts_dir=transcripts_dir,
        scenes_dir=scenes_dir,
        url_list_path=data_dir / "url_list.txt",
        down_url_list_path=data_dir / "down_url_list.txt",
        scene_detector_threshold=float(payload["scene"]["threshold"]),
        min_scene_length_sec=float(payload["scene"]["min_scene_length_sec"]),
        frame_samples_per_scene=int(payload["scene"]["frame_samples_per_scene"]),
        frame_change_threshold=float(payload["scene"].get("frame_change_threshold", 0.08)),
        large_change_threshold=float(payload["scene"].get("large_change_threshold", 0.16)),
        max_keyframes_per_scene=int(payload["scene"].get("max_keyframes_per_scene", 12)),
        min_keyframes_per_scene=int(payload["scene"].get("min_keyframes_per_scene", 3)),
        analysis_fps=float(payload["scene"].get("analysis_fps", 4.0)),
        max_frames_per_vlm_call=int(payload["scene"].get("max_frames_per_vlm_call", 6)),
        batch_overlap_frames=int(payload["scene"].get("batch_overlap_frames", 1)),
        extract_fps=(float(payload["scene"]["extract_fps"]) if payload["scene"].get("extract_fps") is not None else None),
        delete_frames_after_analysis_default=bool(payload["scene"].get("delete_frames_after_analysis_default", False)),
        use_compaction_default=bool(payload["scene"].get("use_compaction_default", False)),
        use_frame_shaving_default=bool(payload["scene"].get("use_frame_shaving_default", False)),
        transcript_fusion_default=bool(payload["pipeline"]["transcript_fusion_default"]),
        whisper_model=str(payload["models"]["whisper_model"]),
        compact_text_model_name=analysis_model,
        compact_text_model_path=analysis_model,
        structuring_model_name=analysis_model,
        structuring_model_path=analysis_model,
        text_model_name=analysis_model,
        text_model_path=analysis_model,
        model_provider="ollama",
        ollama_base_url=str(models.get("ollama_base_url", "http://127.0.0.1:11434")),
        ollama_timeout_sec=int(models.get("ollama_timeout_sec", models.get("timeout_sec", 1800))),
        ollama_max_loaded_models=int(models.get("ollama_max_loaded_models", models.get("max_loaded_models", 1))),
        ollama_num_parallel=int(models.get("ollama_num_parallel", models.get("parallel", 1))),
        ollama_keep_alive=str(models.get("ollama_keep_alive", "30m")),
        visual_model_name=analysis_model,
        visual_model_path=analysis_model,
        use_quantization=bool(models.get("use_quantization", False)),
        llm_max_new_tokens=int(models.get("llm_max_new_tokens", 2048)),
        ui_host=str(payload.get("ui", {}).get("host", "0.0.0.0")),
        ui_port=int(payload.get("ui", {}).get("port", 3020)),
    )
