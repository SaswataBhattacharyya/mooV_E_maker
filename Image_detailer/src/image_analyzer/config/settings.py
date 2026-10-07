from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PathConfig:
    artifact_dir: Path
    log_dir: Path


@dataclass(frozen=True)
class PipelineConfig:
    save_debug_by_default: bool
    dense_caption_first: bool
    enable_ocr: bool
    enable_pose: bool
    enable_face: bool
    enable_segmentation: bool


@dataclass(frozen=True)
class ModelConfig:
    ollama_base_url: str
    synthesis_model: str
    analysis_model: str
    structuring_model: str
    comparison_model: str
    ollama_timeout_sec: int
    ollama_max_loaded_models: int
    ollama_num_parallel: int


@dataclass(frozen=True)
class DetailedPipelineConfig:
    run_root_dir: Path
    default_project_name: str
    default_aspect_ratio: str
    enable_generation_by_default: bool
    target_score: float
    max_full_restarts: int
    max_question_rounds: int
    prompt_word_limit: int
    scene_memory_fact_limit: int
    support_signal_word_limit: int
    scene_weight: float
    perceptual_weight: float
    visual_passes: tuple[str, ...]


@dataclass(frozen=True)
class GenerationBackendConfig:
    backend: str
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    seed: int
    model: str
    command_template: str


@dataclass(frozen=True)
class ProviderConfig:
    detector: str
    region_captioner: str
    pose: str
    face: str
    segmentation: str
    ocr: str
    color: str


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    paths: PathConfig
    pipeline: PipelineConfig
    models: ModelConfig
    detailed: DetailedPipelineConfig
    generation: GenerationBackendConfig
    providers: ProviderConfig


def load_settings(project_root: Path) -> AppConfig:
    payload = _read_yaml(project_root / "configs" / "settings.yaml")
    return AppConfig(
        project_root=project_root,
        paths=PathConfig(
            artifact_dir=project_root / payload["paths"]["artifact_dir"],
            log_dir=project_root / payload["paths"]["log_dir"],
        ),
        pipeline=PipelineConfig(
            save_debug_by_default=bool(payload["pipeline"]["save_debug_by_default"]),
            dense_caption_first=bool(payload["pipeline"]["dense_caption_first"]),
            enable_ocr=bool(payload["pipeline"]["enable_ocr"]),
            enable_pose=bool(payload["pipeline"]["enable_pose"]),
            enable_face=bool(payload["pipeline"]["enable_face"]),
            enable_segmentation=bool(payload["pipeline"]["enable_segmentation"]),
        ),
        models=ModelConfig(
            ollama_base_url=str(payload["models"]["ollama_base_url"]),
            synthesis_model=str(payload["models"]["synthesis_model"]),
            analysis_model=str(payload["models"].get("analysis_model", payload["models"]["synthesis_model"])),
            structuring_model=str(payload["models"].get("structuring_model", payload["models"]["synthesis_model"])),
            comparison_model=str(payload["models"].get("comparison_model", payload["models"]["synthesis_model"])),
            ollama_timeout_sec=int(payload["models"]["ollama_timeout_sec"]),
            ollama_max_loaded_models=int(payload["models"]["ollama_max_loaded_models"]),
            ollama_num_parallel=int(payload["models"]["ollama_num_parallel"]),
        ),
        detailed=DetailedPipelineConfig(
            run_root_dir=project_root / payload["detailed"]["run_root_dir"],
            default_project_name=str(payload["detailed"]["default_project_name"]),
            default_aspect_ratio=str(payload["detailed"]["default_aspect_ratio"]),
            enable_generation_by_default=bool(payload["detailed"]["enable_generation_by_default"]),
            target_score=float(payload["detailed"].get("target_score", 0.95)),
            max_full_restarts=int(payload["detailed"].get("max_full_restarts", 3)),
            max_question_rounds=int(payload["detailed"].get("max_question_rounds", 6)),
            prompt_word_limit=int(payload["detailed"].get("prompt_word_limit", 360)),
            scene_memory_fact_limit=int(payload["detailed"].get("scene_memory_fact_limit", 6)),
            support_signal_word_limit=int(payload["detailed"].get("support_signal_word_limit", 120)),
            scene_weight=float(payload["detailed"].get("scene_weight", 0.65)),
            perceptual_weight=float(payload["detailed"].get("perceptual_weight", 0.35)),
            visual_passes=tuple(str(item) for item in payload["detailed"]["visual_passes"]),
        ),
        generation=GenerationBackendConfig(
            backend=str(payload["generation"]["backend"]),
            width=int(payload["generation"]["width"]),
            height=int(payload["generation"]["height"]),
            steps=int(payload["generation"]["steps"]),
            cfg=float(payload["generation"]["cfg"]),
            sampler=str(payload["generation"]["sampler"]),
            seed=int(payload["generation"]["seed"]),
            model=str(payload["generation"]["model"]),
            command_template=str(payload["generation"].get("command_template", "")),
        ),
        providers=ProviderConfig(
            detector=str(payload["providers"]["detector"]),
            region_captioner=str(payload["providers"]["region_captioner"]),
            pose=str(payload["providers"]["pose"]),
            face=str(payload["providers"]["face"]),
            segmentation=str(payload["providers"]["segmentation"]),
            ocr=str(payload["providers"]["ocr"]),
            color=str(payload["providers"]["color"]),
        ),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
