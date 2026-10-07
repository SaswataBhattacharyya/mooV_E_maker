"""Versioned contracts shared by image and video visual intelligence."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalysisRun(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    input_sha256: str
    source_type: str
    model: str
    mode: str
    status: str = "queued"
    created_at: str
    updated_at: str
    progress: int = 0
    stage: str = "queued"
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class VisualEvidencePacket(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    input: dict[str, Any]
    analysis: dict[str, Any]
    frame_card: dict[str, Any]
    specialist_evidence: dict[str, Any] = Field(default_factory=dict)
    continuity: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    uncertainties: list[Any] = Field(default_factory=list)


class GenerationBrief(BaseModel):
    schema_version: str = "1.0"
    source_run_id: str
    approved_facts: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    camera: Any = None
    lighting: Any = None
    unresolved_questions: list[Any] = Field(default_factory=list)


def generation_brief(packet: dict[str, Any], run_id: str) -> dict[str, Any]:
    analysis = packet.get("analysis") or {}
    card = packet.get("frame_card") or {}
    facts: list[str] = []
    for key in ("summary", "composition", "camera", "lighting", "mood"):
        value = analysis.get(key) or card.get(key)
        if isinstance(value, str) and value.strip():
            facts.append(value.strip())
    return GenerationBrief(
        source_run_id=run_id,
        approved_facts=facts,
        references=[],
        negative_constraints=[],
        camera=analysis.get("camera") or card.get("camera"),
        lighting=analysis.get("lighting") or card.get("lighting"),
        unresolved_questions=analysis.get("uncertainties") or card.get("uncertainties") or [],
    ).model_dump()
