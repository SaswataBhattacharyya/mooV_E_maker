"""Revision-backed story canvas persistence and screenplay planning."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from story_builder.services.reasoning_provider import generate_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def revisions_root(project_dir: Path) -> Path:
    return project_dir / "revisions"


def _path(project_dir: Path, kind: str, revision_id: str) -> Path:
    if kind not in {"novel", "analysis", "screenplay"}:
        raise ValueError("Unsupported revision kind")
    return revisions_root(project_dir) / kind / f"{revision_id}.json"


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def create_revision(project_dir: Path, kind: str, content: Any, *, parent_revision_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    revision_id = f"{kind}-{uuid.uuid4().hex[:12]}"
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True)
    revision = {
        "revision_id": revision_id,
        "kind": kind,
        "parent_revision_id": parent_revision_id,
        "created_at": utc_now(),
        "content_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "metadata": metadata or {},
        "content": content,
    }
    _write(_path(project_dir, kind, revision_id), revision)
    return revision


def get_revision(project_dir: Path, kind: str, revision_id: str) -> dict[str, Any]:
    path = _path(project_dir, kind, revision_id)
    if not path.exists():
        raise FileNotFoundError(revision_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_revisions(project_dir: Path, kind: str) -> list[dict[str, Any]]:
    root = revisions_root(project_dir) / kind
    if not root.exists():
        return []
    result = []
    for path in root.glob("*.json"):
        try:
            result.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return sorted(result, key=lambda item: item.get("created_at", ""), reverse=True)


def build_analysis_prompt(novel: str) -> str:
    return f"""You are a story continuity analyst. Return valid JSON only. Identify loose ends, contradictions, unclear motivations, chronology issues, and production risks. Distinguish intentional mysteries from accidental gaps. Do not rewrite the novel.\n\nOutput schema:\n{{\"summary\":\"string\",\"issues\":[{{\"issue_id\":\"slug\",\"category\":\"loose_end|contradiction|motivation|chronology|continuity|pacing|clarity|production_risk\",\"severity\":\"note|warning|blocking\",\"location_anchor\":\"string\",\"observation\":\"string\",\"possible_resolutions\":[\"string\"],\"status\":\"open\"}}],\"strengths_to_preserve\":[\"string\"],\"questions_for_author\":[\"string\"]}}\n\nNOVEL:\n{novel}""".strip()


def build_outline_prompt(novel: str, narrator: bool) -> str:
    return f"""Convert the approved novel into a screenplay outline. Return valid JSON only. Narrator mode: {'narrator' if narrator else 'no narrator'}. Create every scene in order with stable IDs, purpose, characters, summary, handoff, and estimated duration. Do not write dialogue yet.\n\nSchema:\n{{\"narrator_mode\":\"{'narrator' if narrator else 'none'}\",\"estimated_total_seconds\":0,\"scenes\":[{{\"scene_id\":\"scene_001\",\"scene_number\":1,\"slugline\":\"string\",\"purpose\":\"string\",\"characters_present\":[\"string\"],\"summary\":\"string\",\"estimated_seconds\":0}}],\"coverage_warnings\":[\"string\"]}}\n\nNOVEL:\n{novel}""".strip()


def analyze(novel: str) -> dict[str, Any]:
    return generate_json(prompt=build_analysis_prompt(novel), temperature=0.2)


def outline(novel: str, narrator: bool) -> dict[str, Any]:
    return generate_json(prompt=build_outline_prompt(novel, narrator), temperature=0.25)
