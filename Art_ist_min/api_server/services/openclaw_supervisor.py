"""Native OpenClaw-backed supervision for automated project runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api_server.services.native_openclaw_client import (
    NativeOpenClawError,
    generate_json as generate_openclaw_json,
    generate_text as generate_openclaw_text,
    generate_vision_json as generate_openclaw_vision_json,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DOC_PATHS = [
    PROJECT_ROOT / "openclaw" / "DUTY.md",
    PROJECT_ROOT / "openclaw" / "KNOWLEDGE.md",
    PROJECT_ROOT / "openclaw" / "PIPELINE.md",
    PROJECT_ROOT / "openclaw" / "SOUL.md",
    PROJECT_ROOT / "openclaw" / "STYLE.md",
    PROJECT_ROOT / "openclaw" / "RUNTIME.md",
]


class SupervisorError(RuntimeError):
    """Raised when the selected supervision provider cannot complete a review step."""


def _read_doc_pack() -> str:
    blocks: list[str] = []
    for path in DOC_PATHS:
        if path.exists():
            blocks.append(f"# {path.name}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(blocks)


DOC_PACK = _read_doc_pack()


def _project_context(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": {
            "id": project.get("id"),
            "title": project.get("title"),
            "story_input": project.get("story_input"),
            "current_stage": project.get("current_stage"),
        },
        "artifacts": {
            name: artifact.get("content")
            for name, artifact in project.get("artifacts", {}).items()
            if artifact.get("content") is not None
        },
    }


def generate_supervisor_text(*, prompt: str, project: dict[str, Any] | None = None, temperature: float = 0.2) -> str:
    try:
        user = project.get("id") if isinstance(project, dict) else None
        return generate_openclaw_text(prompt=prompt, temperature=temperature, user=user)
    except NativeOpenClawError as exc:
        raise SupervisorError(str(exc)) from exc


def review_artifact(
    *,
    project: dict[str, Any],
    artifact_type: str,
    artifact_content: dict[str, Any],
) -> dict[str, Any]:
    prompt = f"""
You are the OpenClaw supervisor for an automated story-to-image pipeline.
Your job is to review one generated artifact and decide whether it is coherent enough to continue.
Be practical, not perfectionist.

Rules:
- return valid JSON only
- check coherence with the original story input and approved upstream artifacts
- reject only if the result is absurd, contradictory, seriously incoherent, or not useful for the next stage
- if a small correction is enough, choose "revise" and rewrite the artifact content directly
- use "pause" if human intervention is required before continuing
- do not invent new workflow stages

Instruction pack:
{DOC_PACK}

Project context:
{json.dumps(_project_context(project), indent=2, ensure_ascii=True)}

Artifact type under review:
{artifact_type}

Artifact content under review:
{json.dumps(artifact_content, indent=2, ensure_ascii=True)}

Output schema:
{{
  "action": "approve | revise | pause",
  "rationale": "short explanation",
  "revised_content": {{}}
}}
""".strip()
    try:
        result = generate_openclaw_json(prompt=prompt, temperature=0.2, user=project.get("id"))
    except NativeOpenClawError as exc:
        raise SupervisorError(str(exc)) from exc
    action = str(result.get("action", "approve")).strip().lower()
    if action not in {"approve", "revise", "pause"}:
        action = "approve"
    return {
        "action": action,
        "rationale": str(result.get("rationale", "")).strip() or f"{artifact_type} reviewed",
        "revised_content": result.get("revised_content"),
    }


def inspect_image_candidate(
    *,
    project: dict[str, Any],
    job: dict[str, Any],
    candidate: dict[str, Any],
    image_path: str,
) -> dict[str, Any]:
    prompt = f"""
You are reviewing one AI-generated image candidate for an automated story-to-image pipeline.
Check:
- whether it matches the prompt and story context
- whether the subject is coherent with the job title
- whether there are obvious visual defects such as extra fingers, duplicate heads, broken anatomy, malformed limbs, or absurd objects

Be practical. Minor imperfections are acceptable. Reject only for clear mismatch or obvious defects.
Return valid JSON only.

Project context:
{json.dumps(_project_context(project), indent=2, ensure_ascii=True)}

Image job:
{json.dumps(job, indent=2, ensure_ascii=True)}

Candidate metadata:
{json.dumps(candidate, indent=2, ensure_ascii=True)}

Output schema:
{{
  "passes": true,
  "score": 0,
  "coherence_score": 0,
  "defect_score": 0,
  "issues": ["string"],
  "summary": "short explanation"
}}
""".strip()
    try:
        result = generate_openclaw_vision_json(
            prompt=prompt,
            image_paths=[image_path],
            temperature=0.1,
            user=project.get("id"),
        )
    except NativeOpenClawError as exc:
        raise SupervisorError(str(exc)) from exc
    return {
        "candidate_id": candidate["candidate_id"],
        "passes": bool(result.get("passes", False)),
        "score": int(result.get("score", 0) or 0),
        "coherence_score": int(result.get("coherence_score", 0) or 0),
        "defect_score": int(result.get("defect_score", 0) or 0),
        "issues": result.get("issues") if isinstance(result.get("issues"), list) else [],
        "summary": str(result.get("summary", "")).strip(),
    }


def choose_image_candidate(
    *,
    project: dict[str, Any],
    job: dict[str, Any],
    batch: dict[str, Any],
    inspections: list[dict[str, Any]],
    image_paths: list[str],
) -> dict[str, Any]:
    option_map = [
        {
            "option": index + 1,
            "candidate_id": candidate.get("candidate_id"),
            "seed": candidate.get("seed"),
            "relative_path": candidate.get("relative_path"),
        }
        for index, candidate in enumerate(batch.get("candidates", []))
    ]
    prompt = f"""
You are the OpenClaw supervisor choosing one final image from 4 candidates for an automated story-to-image pipeline.
You are seeing the actual 4 images, along with inspection results and full story context.
Be practical. If one candidate is coherent and free from obvious major defects, select it.
If all candidates are weak or visibly broken, choose redo.
If you need a human decision, choose pause.
Return valid JSON only.

Instruction pack:
{DOC_PACK}

Project context:
{json.dumps(_project_context(project), indent=2, ensure_ascii=True)}

Image job:
{json.dumps(job, indent=2, ensure_ascii=True)}

Batch:
{json.dumps(batch, indent=2, ensure_ascii=True)}

Option mapping for the images you are seeing, in order:
{json.dumps(option_map, indent=2, ensure_ascii=True)}

VLM inspection results:
{json.dumps(inspections, indent=2, ensure_ascii=True)}

Output schema:
{{
  "action": "select | redo | pause",
  "selected_option": 0,
  "rationale": "short explanation"
}}
""".strip()
    try:
        result = generate_openclaw_vision_json(
            prompt=prompt,
            image_paths=image_paths,
            temperature=0.2,
            user=project.get("id"),
        )
    except NativeOpenClawError as exc:
        raise SupervisorError(str(exc)) from exc
    action = str(result.get("action", "redo")).strip().lower()
    if action not in {"select", "redo", "pause"}:
        action = "redo"
    selected_option = int(result.get("selected_option", 0) or 0)
    if not 1 <= selected_option <= len(batch.get("candidates", [])):
        selected_option = 0
    candidate_id = ""
    if selected_option:
        candidate_id = str(batch["candidates"][selected_option - 1]["candidate_id"])
    return {
        "action": action,
        "selected_option": selected_option,
        "candidate_id": candidate_id,
        "rationale": str(result.get("rationale", "")).strip() or "Image batch reviewed",
    }
