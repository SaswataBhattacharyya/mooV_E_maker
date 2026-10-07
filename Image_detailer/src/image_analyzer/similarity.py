from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from image_analyzer.models.schemas import (
    HybridSimilarityScore,
    PerceptualScoreBreakdown,
    SemanticScoreBreakdown,
)


def compute_hybrid_similarity(
    reference_path: Path,
    generated_path: Path,
    *,
    semantic_similarity_score: float,
    scene_weight: float,
    perceptual_weight: float,
    issue_severities: list[str] | None = None,
) -> HybridSimilarityScore:
    perceptual = compute_perceptual_similarity(reference_path, generated_path)
    semantic = _semantic_breakdown(semantic_similarity_score, issue_severities or [])
    weighted = _clamp(
        scene_weight * semantic.semantic_similarity_score
        + perceptual_weight * perceptual.perceptual_similarity_score
    )
    return HybridSimilarityScore(
        weighted_score=weighted,
        semantic=semantic,
        perceptual=perceptual,
        scene_weight=scene_weight,
        perceptual_weight=perceptual_weight,
    )


def compute_perceptual_similarity(reference_path: Path, generated_path: Path) -> PerceptualScoreBreakdown:
    reference = _prepare_image(reference_path)
    generated = _prepare_image(generated_path, size=reference.shape[:2][::-1])

    mse = np.mean((reference - generated) ** 2)
    mse_score = _clamp(1.0 - (mse / (255.0**2)))

    histogram_score = _histogram_intersection(reference, generated)
    edge_score = _edge_similarity(reference, generated)
    perceptual_similarity_score = _clamp(0.45 * mse_score + 0.30 * histogram_score + 0.25 * edge_score)
    return PerceptualScoreBreakdown(
        mse_score=round(mse_score, 6),
        histogram_score=round(histogram_score, 6),
        edge_score=round(edge_score, 6),
        perceptual_similarity_score=round(perceptual_similarity_score, 6),
    )


def _semantic_breakdown(base_score: float, issue_severities: list[str]) -> SemanticScoreBreakdown:
    high = sum(1 for item in issue_severities if item == "high")
    medium = sum(1 for item in issue_severities if item == "medium")
    low = sum(1 for item in issue_severities if item == "low")
    penalty = min(0.6, high * 0.12 + medium * 0.06 + low * 0.02)
    semantic_score = _clamp(base_score - penalty)
    composition_score = _clamp(semantic_score - high * 0.05)
    object_score = _clamp(semantic_score - (high + medium) * 0.03)
    lighting_score = _clamp(semantic_score - medium * 0.02)
    constraint_score = _clamp(semantic_score - low * 0.01)
    return SemanticScoreBreakdown(
        composition_score=round(composition_score, 6),
        object_score=round(object_score, 6),
        lighting_score=round(lighting_score, 6),
        constraint_score=round(constraint_score, 6),
        semantic_similarity_score=round(semantic_score, 6),
    )


def _prepare_image(path: Path, *, size: tuple[int, int] | None = None) -> np.ndarray:
    with Image.open(path).convert("RGB") as image:
        if size is not None:
            image = image.resize(size)
        else:
            image = image.resize((512, 512))
        return np.asarray(image, dtype=np.float32)


def _histogram_intersection(reference: np.ndarray, generated: np.ndarray) -> float:
    ref_hist, _ = np.histogram(reference.flatten(), bins=32, range=(0, 255), density=False)
    gen_hist, _ = np.histogram(generated.flatten(), bins=32, range=(0, 255), density=False)
    total = float(max(ref_hist.sum(), 1))
    return _clamp(float(np.minimum(ref_hist, gen_hist).sum() / total))


def _edge_similarity(reference: np.ndarray, generated: np.ndarray) -> float:
    ref_edges = _edges(reference)
    gen_edges = _edges(generated)
    mse = np.mean((ref_edges - gen_edges) ** 2)
    return _clamp(1.0 - (mse / (255.0**2)))


def _edges(image_array: np.ndarray) -> np.ndarray:
    image = Image.fromarray(image_array.astype(np.uint8), mode="RGB").convert("L")
    edged = image.filter(ImageFilter.FIND_EDGES)
    return np.asarray(edged, dtype=np.float32)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
