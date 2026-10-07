from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoundingBox(SchemaModel):
    x1: int
    y1: int
    x2: int
    y2: int


class NormalizedBoundingBox(SchemaModel):
    x1: float
    y1: float
    x2: float
    y2: float


class MeasuredField(SchemaModel):
    value: Any
    provenance: str
    confidence: float


class ImageMetadata(SchemaModel):
    source_path: str
    file_name: str
    sha256: str
    width: int
    height: int


class ImageSummary(SchemaModel):
    short_caption: str
    long_description: str


class ObjectRecord(SchemaModel):
    label: str
    bbox_px: BoundingBox
    bbox_norm: NormalizedBoundingBox
    confidence: float
    attributes: dict[str, MeasuredField] = Field(default_factory=dict)


class PersonRecord(SchemaModel):
    id: str
    bbox_px: BoundingBox
    bbox_norm: NormalizedBoundingBox
    pose_angles_deg: dict[str, float] = Field(default_factory=dict)
    landmarks: dict[str, Any] = Field(default_factory=dict)
    facing_direction: MeasuredField | None = None
    gesture_hints: list[str] = Field(default_factory=list)


class FaceRecord(SchemaModel):
    id: str
    bbox_px: BoundingBox
    bbox_norm: NormalizedBoundingBox
    landmarks: dict[str, Any] = Field(default_factory=dict)
    blendshapes: dict[str, Any] = Field(default_factory=dict)
    inferred_expression: MeasuredField | None = None


class TextRegion(SchemaModel):
    text: str
    bbox_px: BoundingBox
    bbox_norm: NormalizedBoundingBox
    confidence: float
    provenance: str


class RegionRecord(SchemaModel):
    id: str
    label: str
    bbox_px: BoundingBox
    bbox_norm: NormalizedBoundingBox
    dominant_colors: list[MeasuredField] = Field(default_factory=list)


class SceneSummary(SchemaModel):
    category: str
    confidence: float
    provenance: str


class UncertaintyRecord(SchemaModel):
    source: str
    message: str


class DescriptionLayer(SchemaModel):
    key: str
    title: str
    text: str
    file_name: str


class AnalysisEvent(SchemaModel):
    timestamp: datetime
    stage: str
    status: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(SchemaModel):
    image: ImageMetadata
    summary: ImageSummary
    objects: list[ObjectRecord] = Field(default_factory=list)
    people: list[PersonRecord] = Field(default_factory=list)
    faces: list[FaceRecord] = Field(default_factory=list)
    regions: list[RegionRecord] = Field(default_factory=list)
    text_regions: list[TextRegion] = Field(default_factory=list)
    scene: SceneSummary
    provenance: dict[str, list[str]] = Field(default_factory=dict)
    uncertainty: list[UncertaintyRecord] = Field(default_factory=list)
    description_layers: list[DescriptionLayer] = Field(default_factory=list)
    orchestration_events: list[AnalysisEvent] = Field(default_factory=list)


class RunConfig(SchemaModel):
    project_name: str
    reference_image: str
    vlm_model: str
    llm_model: str
    generator_backend: str | None = None
    comparison_model: str | None = None
    iterations: int = 0
    aspect_ratio: str
    enable_generation: bool = False
    enable_comparison: bool = False
    target_score: float = 0.95
    max_iterations: int = 5
    scene_weight: float = 0.65
    perceptual_weight: float = 0.35
    created_at: datetime


class CanvasSpec(SchemaModel):
    aspect_ratio: str
    orientation: str
    camera_angle: str
    lens_feel: str
    horizon_y_percent_from_top: float
    vanishing_or_radiation_center: dict[str, float] = Field(default_factory=dict)


class SceneObject(SchemaModel):
    name: str
    role: str
    center_x_percent: float | None = None
    center_y_percent: float | None = None
    width_percent: float | None = None
    height_percent: float | None = None
    shape: str = ""
    color: str = ""
    surface: str = ""
    importance: str = "medium"
    must_preserve: bool = False


class RegionSpec(SchemaModel):
    region_y_percent: str
    summary: str
    texture: list[str] = Field(default_factory=list)
    dominant_colors: list[str] = Field(default_factory=list)


class SkySpec(SchemaModel):
    region_y_percent: str
    cloud_direction: str
    upper_left: str
    upper_right: str
    center: str
    motion: str
    sharpness: str


class ColorPaletteSpec(SchemaModel):
    dominant: list[str] = Field(default_factory=list)
    saturation: str
    contrast: str


class SceneMap(SchemaModel):
    canvas: CanvasSpec
    main_objects: list[SceneObject] = Field(default_factory=list)
    foreground: RegionSpec
    middle_ground: RegionSpec
    background: RegionSpec
    sky: SkySpec
    color_palette: ColorPaletteSpec
    negative_constraints: list[str] = Field(default_factory=list)
    support_signals: dict[str, Any] = Field(default_factory=dict)


class VisualHierarchy(SchemaModel):
    must_match: list[str] = Field(default_factory=list)
    should_match: list[str] = Field(default_factory=list)
    can_vary_slightly: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)


class ScenePassResult(SchemaModel):
    pass_key: str
    title: str
    prompt: str
    raw_response: str
    structured: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class GapRecord(SchemaModel):
    topic: str
    reason: str
    priority: int


class QuestionRecord(SchemaModel):
    iteration: int
    question: str
    answer: str
    topic: str


class SceneMemory(SchemaModel):
    version: int
    scene_type: str
    composition: dict[str, Any] = Field(default_factory=dict)
    major_elements: list[str] = Field(default_factory=list)
    known: list[str] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    high_priority_gaps: list[GapRecord] = Field(default_factory=list)
    scene_map: dict[str, Any] = Field(default_factory=dict)


class PromptPackage(SchemaModel):
    base_prompt: str
    precision_prompt: str
    negative_prompt: str
    generator_prompt: str
    final_prompt: str
    notes: list[str] = Field(default_factory=list)


class GenerationConfig(SchemaModel):
    backend: str
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    seed: int
    model: str
    command_template: str = ""


class GenerationResult(SchemaModel):
    enabled: bool
    status: str
    message: str
    output_image: str | None = None
    metadata_path: str | None = None
    seed: int | None = None


class ComparisonIssue(SchemaModel):
    category: str
    issue: str
    severity: str
    reference: str
    generated: str
    prompt_fix: str


class ComparisonReport(SchemaModel):
    overall_similarity_score: float
    semantic_similarity_score: float = 0.0
    perceptual_similarity_score: float = 0.0
    issues: list[ComparisonIssue] = Field(default_factory=list)
    negative_prompt_additions: list[str] = Field(default_factory=list)


class PerceptualScoreBreakdown(SchemaModel):
    mse_score: float
    histogram_score: float
    edge_score: float
    perceptual_similarity_score: float


class SemanticScoreBreakdown(SchemaModel):
    composition_score: float
    object_score: float
    lighting_score: float
    constraint_score: float
    semantic_similarity_score: float


class HybridSimilarityScore(SchemaModel):
    weighted_score: float
    semantic: SemanticScoreBreakdown
    perceptual: PerceptualScoreBreakdown
    scene_weight: float
    perceptual_weight: float


class PromptCorrection(SchemaModel):
    changes_to_prompt: list[dict[str, str]] = Field(default_factory=list)
    changes_to_negative_prompt: list[str] = Field(default_factory=list)


class IterationResult(SchemaModel):
    iteration: int
    prompt_package: PromptPackage
    generation: GenerationResult
    comparison: ComparisonReport | None = None
    hybrid_score: HybridSimilarityScore | None = None
    correction: PromptCorrection | None = None
    accepted: bool = False


class LoopTermination(SchemaModel):
    reason: str
    best_iteration: int | None = None
    best_score: float = 0.0
    threshold_reached: bool = False


class RunReport(SchemaModel):
    run_id: str
    run_dir: str
    reference_image: str
    scene_map: SceneMap
    final_scene_memory: SceneMemory | None = None
    visual_hierarchy: VisualHierarchy
    prompt_package: PromptPackage
    passes: list[ScenePassResult] = Field(default_factory=list)
    question_history: list[QuestionRecord] = Field(default_factory=list)
    gap_history: list[list[GapRecord]] = Field(default_factory=list)
    generation: GenerationResult
    comparison: ComparisonReport | None = None
    correction: PromptCorrection | None = None
    iterations: list[IterationResult] = Field(default_factory=list)
    termination: LoopTermination | None = None
    warnings: list[str] = Field(default_factory=list)
