"""Backend for the local website, Ollama planning flow, and TTS helper tools."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api_server.services.tts_assets import (
    build_srt_analysis_report,
    discover_voice_options,
    ensure_alias_map_file,
    ensure_storage_dirs,
    get_alias_map_path,
    load_alias_map,
    save_story_text,
    save_voice_like_asset,
    set_core_aliases,
)
from api_server.services.comfyui_bridge import ComfyUIError, submit_image_batch
from api_server.services.local_vision_recovery import run_local_vision_recovery
from api_server.services.ollama_client import OllamaError
from api_server.services.native_openclaw_client import gateway_summary as native_openclaw_gateway_summary
from api_server.services.openclaw_supervisor import (
    SupervisorError,
    choose_image_candidate,
    inspect_image_candidate,
    review_artifact,
)
from api_server.services.openclaw_projects import (
    ARTIFACT_TYPES,
    ProjectStore,
)
from api_server.services.story_pipeline import (
    generate_characters_artifact,
    generate_dialogue_artifact,
    generate_image_jobs_artifact,
    generate_scenes_artifact,
    generate_story_artifact,
    generate_subscenes_artifact,
)
from app_config import load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FRONTEND_DIST = PROJECT_ROOT / "ai-art-generator-hub" / "dist"
CONFIG = load_config(PROJECT_ROOT)
PROJECTS_DIR = ASSETS_DIR / "projects"
PROJECT_STORE = ProjectStore(PROJECTS_DIR)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
ensure_storage_dirs()
ensure_alias_map_file()

app = FastAPI(title="Agentic Art Builder Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTOMATION_TASKS: dict[str, asyncio.Task[None]] = {}


class ActionResponse(BaseModel):
    action_id: str
    response: str


class UploadResponse(BaseModel):
    asset_id: str
    path: str


class AliasUpdateRequest(BaseModel):
    alice: str
    bob: str
    narrator: str


class ProjectCreateRequest(BaseModel):
    title: str
    story_input: str
    automation_mode: bool = False


class ProjectDraftUpdateRequest(BaseModel):
    title: str
    story_input: str
    automation_mode: bool = False


class ArtifactSaveRequest(BaseModel):
    content: Any


class ArtifactGenerateRequest(BaseModel):
    extra_instructions: str | None = None


class ImageBatchRequest(BaseModel):
    count: int = 4


class CandidateAcceptRequest(BaseModel):
    candidate_id: str


class SupervisorOperatorRequest(BaseModel):
    message: str


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _idle_status() -> dict[str, Any]:
    return {
        "job_id": None,
        "state": "DISABLED",
        "current_task": "Generation pipeline is in placeholder mode",
        "progress": 0,
        "logs": [
            {
                "id": "integration-disabled",
                "timestamp": _timestamp(),
                "level": "warning",
                "message": "No jobs are sent to ComfyUI yet. Upload and status endpoints are active.",
            }
        ],
        "completed_tasks": [],
    }


def _service_reachable(url: str) -> bool:
    try:
        with urlopen(url, timeout=3):
            return True
    except URLError:
        return False


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "website-ollama-comfyui",
        "comfyui_enabled": True,
        "project": "agentic-art-bare-minimum",
        "website_host": os.environ.get("WEBSITE_HOST", "127.0.0.1"),
        "website_port": os.environ.get("WEBSITE_PORT", "3010"),
        "comfyui_host": CONFIG.comfyui_host,
        "comfyui_port": CONFIG.comfyui_port,
        "ollama_host": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "model_roles": {
            "reasoning": os.environ.get("OLLAMA_REASONING_MODEL", "gemma4:latest"),
            "coder": os.environ.get("OLLAMA_CODER_MODEL", "qwen2.5-coder:14b"),
            "vision": os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"),
        },
        "supervision": {
            "adapter": "native_openclaw_gateway",
            "gateway": native_openclaw_gateway_summary(),
        },
        "optional_layers": {
            "graphify": False,
            "openclaw_supervisor": True,
            "autoresearch": False,
        },
        "dependencies": {
            "ollama": _service_reachable(f"{os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')}/api/tags"),
            "comfyui": _service_reachable(f"http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}/system_stats"),
        },
    }


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return {
        "website": "running",
        "generation": "enabled",
        "project": "agentic-art-bare-minimum",
        "message": "Website is running with local artifact generation, native OpenClaw supervision, ComfyUI image execution, TTS asset management, and SRT analysis.",
    }


@app.post("/api/generate")
async def generate(request: Request) -> dict[str, Any]:
    form = await request.form()
    metadata = form.get("metadata")
    parsed_metadata: Any = None
    if isinstance(metadata, str):
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            parsed_metadata = metadata

    return {
        "status": "redirected",
        "message": "Use /api/projects for the structured generation pipeline.",
        "received_metadata": parsed_metadata,
    }


def _load_required_artifact(project: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    artifact = project["artifacts"][artifact_type]
    content = artifact.get("content")
    if not isinstance(content, dict):
        raise HTTPException(status_code=400, detail=f"Generate or save the {artifact_type} artifact first")
    return content


def _artifact_progress(artifact_type: str) -> int:
    order = list(ARTIFACT_TYPES)
    if artifact_type not in order:
        return 0
    return int(((order.index(artifact_type) + 1) / len(order)) * 100)


AUTOMATION_TEXT_RETRY_LIMIT = 3
AUTOMATION_IMAGE_RETRY_LIMIT = 3
VISION_RETRY_LIMIT = 2
SUPERVISOR_RETRY_LIMIT = 2
VISION_RECOVERY_RETRY_LIMIT = 1


def _artifact_runtime_state(artifact_type: str) -> str:
    return f"{artifact_type}_generating"


def _run_supervisor_call(
    *,
    project_id: str,
    project: dict[str, Any],
    stage: str,
    kind: str,
    call,
    retry_limit: int = SUPERVISOR_RETRY_LIMIT,
) -> Any:
    last_error: SupervisorError | None = None
    for attempt in range(1, retry_limit + 1):
        try:
            return call()
        except SupervisorError as exc:
            last_error = exc
            _write_supervisor_event(
                project_id,
                kind="supervisor_retry",
                message=f"{kind} failed on native OpenClaw attempt {attempt}/{retry_limit} for {stage}: {exc}",
                level="warning",
                details={
                    "stage": stage,
                    "adapter": "native_openclaw_gateway",
                    "attempt": attempt,
                },
            )
            if attempt < retry_limit:
                time.sleep(1)
    if last_error is None:
        raise RuntimeError(f"{kind} failed without a captured supervisor error for {stage}")
    raise last_error


async def _automation_worker(project_id: str, task_id: str) -> None:
    try:
        await asyncio.to_thread(_run_supervised_automation, project_id)
    except Exception as exc:
        try:
            _write_supervisor_event(
                project_id,
                kind="automation_worker_failed",
                message=f"Background automation worker stopped: {exc}",
                level="error",
            )
        except Exception:
            pass
    finally:
        AUTOMATION_TASKS.pop(project_id, None)
        try:
            PROJECT_STORE.set_automation_task_id(project_id, None)
        except FileNotFoundError:
            pass


def _schedule_supervised_automation(project_id: str) -> None:
    existing_task = AUTOMATION_TASKS.get(project_id)
    if existing_task is not None and not existing_task.done():
        return

    task_id = f"{project_id}:{datetime.now(timezone.utc).timestamp()}"
    PROJECT_STORE.set_status(project_id, "automating")
    PROJECT_STORE.set_runtime(
        project_id,
        state_value="RUNNING",
        current_task="Automation queued. Ripa will start shortly.",
        progress=0,
        job_id=f"{project_id}:automation",
        last_error=None,
    )
    PROJECT_STORE.set_automation_active(project_id, True)
    PROJECT_STORE.set_automation_task_id(project_id, task_id)
    PROJECT_STORE.set_supervisor_state(
        project_id,
        mode="queued",
        waiting_for_user=False,
        actionable_diagnosis=None,
    )
    _write_supervisor_event(
        project_id,
        kind="automation_queued",
        message="Ripa queued the automation run and will begin shortly.",
    )
    AUTOMATION_TASKS[project_id] = asyncio.create_task(_automation_worker(project_id, task_id))


def _write_supervisor_event(
    project_id: str,
    *,
    kind: str,
    message: str,
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    PROJECT_STORE.add_supervisor_event(
        project_id,
        kind=kind,
        message=message,
        level=level,
        details=details,
    )


def _set_actionable_diagnosis(
    project_id: str,
    *,
    layer: str,
    stage: str,
    reason: str,
    next_action: str,
    waiting_for_user: bool = False,
) -> None:
    PROJECT_STORE.set_supervisor_state(
        project_id,
        mode="waiting_for_user" if waiting_for_user else "blocked",
        waiting_for_user=waiting_for_user,
        actionable_diagnosis={
            "layer": layer,
            "stage": stage,
            "reason": reason,
            "next_action": next_action,
        },
    )


def _classify_ollama_layer(error_text: str, default_layer: str = "ollama") -> str:
    if "HTTP 500" in error_text or "returned HTTP" in error_text:
        return f"{default_layer}_internal"
    if "Could not reach Ollama" in error_text:
        return f"{default_layer}_unreachable"
    return default_layer


def _classify_supervision_layer(project: dict[str, Any], error_text: str, local_default_layer: str) -> str:
    if "Could not reach native OpenClaw Gateway" in error_text:
        return "native_openclaw_unreachable"
    if "requires auth" in error_text or "token" in error_text:
        return "native_openclaw_auth"
    if "returned HTTP" in error_text:
        return "native_openclaw_internal"
    return local_default_layer


def _create_and_record_image_batch(
    *,
    project_id: str,
    job: dict[str, Any],
    count: int,
    runtime_task: str,
    log_message: str,
    completed_task: str,
) -> dict[str, Any]:
    project = PROJECT_STORE.read_project(project_id)
    existing_batches = [batch for batch in project["image_queue"]["batches"] if batch["job_id"] == job["job_id"]]
    batch_index = len(existing_batches) + 1
    destination_dir = PROJECTS_DIR / project_id / "images" / job["job_id"] / f"batch-{batch_index:03d}"
    PROJECT_STORE.set_runtime(
        project_id,
        state_value="RUNNING",
        current_task=runtime_task,
        progress=100,
        job_id=f"{project_id}:{job['job_id']}:batch:{batch_index}",
    )
    PROJECT_STORE.add_log(project_id, "info", log_message)
    batch = submit_image_batch(
        project_id=project_id,
        job=job,
        batch_index=batch_index,
        batch_size=max(1, count),
        destination_dir=destination_dir,
    )
    PROJECT_STORE.append_image_batch(project_id, batch)
    PROJECT_STORE.set_runtime(
        project_id,
        state_value="COMPLETED",
        current_task=f"Image batch ready for review: {job['title']}",
        progress=100,
        job_id=f"{project_id}:{job['job_id']}:batch:{batch_index}",
        completed_task=completed_task,
    )
    return batch


def _vision_recovery_event_details(
    *,
    job: dict[str, Any],
    candidate: dict[str, Any],
    recovery: dict[str, Any],
) -> dict[str, Any]:
    snapshot_before = recovery.get("snapshot_before", {})
    snapshot_after = recovery.get("snapshot_after", {})
    return {
        "job_id": job["job_id"],
        "candidate_id": candidate["candidate_id"],
        "contention_class": recovery.get("contention_class"),
        "cleanup_actions": recovery.get("cleanup_actions", []),
        "retry_recommended": recovery.get("retry_recommended", False),
        "snapshot_before": {
            "gpu": snapshot_before.get("gpu"),
            "ollama": snapshot_before.get("ollama"),
            "comfyui": snapshot_before.get("comfyui"),
        },
        "snapshot_after": {
            "gpu": snapshot_after.get("gpu") if snapshot_after else None,
            "ollama": snapshot_after.get("ollama") if snapshot_after else None,
            "comfyui": snapshot_after.get("comfyui") if snapshot_after else None,
        },
    }


def _summarize_recovery_for_user(recovery: dict[str, Any] | None) -> str:
    if not recovery:
        return ""
    contention = str(recovery.get("contention_class") or "").strip()
    successful_actions: list[str] = []
    for action in recovery.get("cleanup_actions", []):
        if action.get("status") != "succeeded":
            continue
        if action.get("kind") == "ollama_stop_model":
            successful_actions.append(f"stopped {action.get('target')}")
        elif action.get("kind") == "comfyui_memory_release":
            successful_actions.append("requested ComfyUI memory release")

    summary_parts = []
    if contention:
        summary_parts.append(f"Recovery detected {contention}.")
    if successful_actions:
        summary_parts.append(f"Tried: {', '.join(successful_actions)}.")
    return f" {' '.join(summary_parts)}" if summary_parts else ""


def _inspect_image_candidate_with_recovery(
    *,
    project_id: str,
    project: dict[str, Any],
    job: dict[str, Any],
    candidate: dict[str, Any],
    image_path: str,
) -> dict[str, Any]:
    last_vision_error: SupervisorError | None = None
    for vision_attempt in range(1, VISION_RETRY_LIMIT + 1):
        try:
            return inspect_image_candidate(
                project=project,
                job=job,
                candidate=candidate,
                image_path=image_path,
            )
        except SupervisorError as exc:
            last_vision_error = exc
            _write_supervisor_event(
                project_id,
                kind="vision_retry",
                message=(
                    f"Vision review failed for {job['title']} candidate {candidate['candidate_id']} "
                    f"on attempt {vision_attempt}/{VISION_RETRY_LIMIT}: {exc}"
                ),
                level="warning",
                details={
                    "job_id": job["job_id"],
                    "candidate_id": candidate["candidate_id"],
                    "attempt": vision_attempt,
                },
            )
            if vision_attempt < VISION_RETRY_LIMIT:
                time.sleep(1)

    if last_vision_error is None:
        raise RuntimeError(f"Vision review failed without a captured supervisor error for {candidate['candidate_id']}")

    recovery = run_local_vision_recovery(
        error_text=str(last_vision_error),
        vision_model=os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"),
        reasoning_model=os.environ.get("OLLAMA_REASONING_MODEL", "gemma4:latest"),
        coder_model=os.environ.get("OLLAMA_CODER_MODEL", "qwen2.5-coder:14b"),
    )
    if recovery.get("eligible"):
        event_details = _vision_recovery_event_details(job=job, candidate=candidate, recovery=recovery)
        _write_supervisor_event(
            project_id,
            kind="vision_resource_diagnosis",
            message=(
                f"Diagnosed local vision contention for {job['title']} candidate {candidate['candidate_id']}: "
                f"{recovery.get('contention_class')}"
            ),
            level="warning",
            details=event_details,
        )
        _write_supervisor_event(
            project_id,
            kind="vision_resource_cleanup",
            message=f"Ran bounded local cleanup before retrying vision review for {job['title']}.",
            level="warning",
            details=event_details,
        )
        for retry_attempt in range(1, VISION_RECOVERY_RETRY_LIMIT + 1):
            _write_supervisor_event(
                project_id,
                kind="vision_resource_retry",
                message=f"Retrying vision review after local cleanup for {job['title']} candidate {candidate['candidate_id']}.",
                level="warning",
                details={**event_details, "attempt": retry_attempt},
            )
            try:
                inspection = inspect_image_candidate(
                    project=project,
                    job=job,
                    candidate=candidate,
                    image_path=image_path,
                )
            except SupervisorError as retry_exc:
                last_vision_error = retry_exc
                setattr(last_vision_error, "recovery_result", recovery)
                _write_supervisor_event(
                    project_id,
                    kind="vision_resource_retry_failed",
                    message=(
                        f"Local cleanup retry still failed for {job['title']} candidate {candidate['candidate_id']}: "
                        f"{retry_exc}"
                    ),
                    level="error",
                    details={**event_details, "attempt": retry_attempt},
                )
            else:
                _write_supervisor_event(
                    project_id,
                    kind="vision_resource_retry_succeeded",
                    message=f"Local cleanup recovered vision review for {job['title']} candidate {candidate['candidate_id']}.",
                    level="success",
                    details={**event_details, "attempt": retry_attempt},
                )
                return inspection

    raise last_vision_error


def _choose_fallback_candidate(batch: dict[str, Any], inspections: list[dict[str, Any]]) -> str | None:
    valid_ids = {candidate["candidate_id"] for candidate in batch["candidates"]}
    passing = [item for item in inspections if item["candidate_id"] in valid_ids and item.get("passes")]
    if not passing:
        return None
    passing.sort(
        key=lambda item: (
            int(item.get("score", 0)),
            int(item.get("coherence_score", 0)),
            -int(item.get("defect_score", 0)),
        ),
        reverse=True,
    )
    return str(passing[0]["candidate_id"])


def _run_supervised_automation(project_id: str) -> dict[str, Any]:
    stage_retry_counts: dict[str, int] = {}
    image_retry_counts: dict[str, int] = {}

    PROJECT_STORE.set_status(project_id, "automating")
    PROJECT_STORE.set_automation_active(project_id, True)
    PROJECT_STORE.set_supervisor_state(
        project_id,
        current_review="automation_start",
        last_decision="running",
        last_rationale="OpenClaw automation started",
        mode="running",
        waiting_for_user=False,
        actionable_diagnosis=None,
        stage_retry_counts=stage_retry_counts,
        image_retry_counts=image_retry_counts,
    )
    _write_supervisor_event(
        project_id,
        kind="automation_started",
        message="Ripa is online. Full automation has started for this project.",
        details={"emoji": "🤖🦞"},
    )

    try:
        for artifact_type in ARTIFACT_TYPES:
            while True:
                project = PROJECT_STORE.read_project(project_id)
                current_content = project["artifacts"][artifact_type].get("content")
                if not isinstance(current_content, dict):
                    _write_supervisor_event(
                        project_id,
                        kind="stage_start",
                        message=f"Starting {artifact_type} generation with Ollama.",
                        details={"stage": artifact_type, "layer": "ollama"},
                    )
                    PROJECT_STORE.set_runtime(
                        project_id,
                        state_value="RUNNING",
                        current_task=f"Generating {artifact_type} with Ollama",
                        progress=_artifact_progress(artifact_type),
                        job_id=f"{project_id}:{artifact_type}",
                    )
                    PROJECT_STORE.set_artifact_status(project_id, artifact_type, "generating")
                    PROJECT_STORE.add_log(project_id, "info", f"Automation started {artifact_type} generation")
                    current_content = _generate_artifact(project, artifact_type)
                    PROJECT_STORE.save_artifact(project_id, artifact_type, current_content, status="generated")
                    PROJECT_STORE.set_artifact_status(project_id, artifact_type, "reviewing")
                    _write_supervisor_event(
                        project_id,
                        kind="artifact_generated",
                        message=f"{artifact_type} generated. The editor on 3010 can show it now.",
                        details={"stage": artifact_type},
                    )

                PROJECT_STORE.set_supervisor_state(
                    project_id,
                    current_review=f"{artifact_type}_review",
                    mode="reviewing",
                    stage_retry_counts=stage_retry_counts,
                    image_retry_counts=image_retry_counts,
                )
                _write_supervisor_event(
                    project_id,
                    kind="review_start",
                    message=f"Reviewing {artifact_type} for coherence and downstream usefulness.",
                    details={"stage": artifact_type},
                )
                review = _run_supervisor_call(
                    project_id=project_id,
                    project=PROJECT_STORE.read_project(project_id),
                    stage=artifact_type,
                    kind=f"{artifact_type} review",
                    call=lambda: review_artifact(
                        project=PROJECT_STORE.read_project(project_id),
                        artifact_type=artifact_type,
                        artifact_content=current_content,
                    ),
                )
                PROJECT_STORE.set_supervisor_state(
                    project_id,
                    current_review=f"{artifact_type}_review",
                    last_decision=review["action"],
                    last_rationale=review["rationale"],
                    mode="reviewing",
                    stage_retry_counts=stage_retry_counts,
                    image_retry_counts=image_retry_counts,
                )
                PROJECT_STORE.add_log(
                    project_id,
                    "info",
                    f"OpenClaw {review['action']} for {artifact_type}: {review['rationale']}",
                )
                _write_supervisor_event(
                    project_id,
                    kind="review_decision",
                    message=f"Ripa chose {review['action']} for {artifact_type}. {review['rationale']}",
                    level="success" if review["action"] == "approve" else "warning",
                    details={"stage": artifact_type, "action": review["action"]},
                )

                if review["action"] == "approve":
                    PROJECT_STORE.save_artifact(project_id, artifact_type, current_content, status="ready")
                    PROJECT_STORE.set_runtime(
                        project_id,
                        state_value="COMPLETED",
                        current_task=f"{artifact_type} approved by OpenClaw",
                        progress=_artifact_progress(artifact_type),
                        job_id=f"{project_id}:{artifact_type}",
                        completed_task=f"{artifact_type} approved by OpenClaw",
                    )
                    _write_supervisor_event(
                        project_id,
                        kind="stage_complete",
                        message=f"{artifact_type} approved. Moving forward.",
                        level="success",
                        details={"stage": artifact_type},
                    )
                    break

                if review["action"] == "revise" and isinstance(review.get("revised_content"), dict):
                    PROJECT_STORE.set_supervisor_state(project_id, mode="revising")
                    PROJECT_STORE.save_artifact(project_id, artifact_type, review["revised_content"], status="ready")
                    PROJECT_STORE.set_runtime(
                        project_id,
                        state_value="COMPLETED",
                        current_task=f"{artifact_type} revised by OpenClaw and approved",
                        progress=_artifact_progress(artifact_type),
                        job_id=f"{project_id}:{artifact_type}",
                        completed_task=f"{artifact_type} revised by OpenClaw",
                    )
                    _write_supervisor_event(
                        project_id,
                        kind="artifact_revised",
                        message=f"Ripa revised {artifact_type} and accepted the revision.",
                        level="success",
                        details={"stage": artifact_type},
                    )
                    break

                if review["action"] == "pause":
                    _set_actionable_diagnosis(
                        project_id,
                        layer="native_openclaw",
                        stage=artifact_type,
                        reason=review["rationale"],
                        next_action=f"Open the {artifact_type} artifact in the website, apply the requested edit or review, then continue automation.",
                        waiting_for_user=True,
                    )
                    _write_supervisor_event(
                        project_id,
                        kind="needs_user",
                        message=f"OpenClaw paused on {artifact_type}. {review['rationale']}",
                        level="error",
                        details={"stage": artifact_type, "action": "pause"},
                    )
                    raise RuntimeError(f"OpenClaw paused {artifact_type}: {review['rationale']}")

                stage_retry_counts[artifact_type] = stage_retry_counts.get(artifact_type, 0) + 1
                PROJECT_STORE.set_supervisor_state(
                    project_id,
                    current_review=f"{artifact_type}_review",
                    last_decision="retry",
                    last_rationale=review["rationale"],
                    mode="retrying",
                    stage_retry_counts=stage_retry_counts,
                    image_retry_counts=image_retry_counts,
                )
                if stage_retry_counts[artifact_type] >= AUTOMATION_TEXT_RETRY_LIMIT:
                    _set_actionable_diagnosis(
                        project_id,
                        layer="ollama",
                        stage=artifact_type,
                        reason=f"Ripa could not approve {artifact_type} after {AUTOMATION_TEXT_RETRY_LIMIT} tries.",
                        next_action=f"Open the {artifact_type} artifact in the website, inspect the last generated JSON, and either save a manual revision or resume automation.",
                        waiting_for_user=True,
                    )
                    _write_supervisor_event(
                        project_id,
                        kind="needs_user",
                        message=f"{artifact_type} is blocked. I need you to review or edit it before we continue.",
                        level="error",
                        details={"stage": artifact_type, "retry_count": stage_retry_counts[artifact_type]},
                    )
                    raise RuntimeError(f"OpenClaw could not approve {artifact_type} after {AUTOMATION_TEXT_RETRY_LIMIT} tries")
                PROJECT_STORE.add_log(
                    project_id,
                    "warning",
                    f"OpenClaw requested regeneration for {artifact_type} (attempt {stage_retry_counts[artifact_type] + 1})",
                )
                _write_supervisor_event(
                    project_id,
                    kind="retry",
                    message=f"Regenerating {artifact_type}. Attempt {stage_retry_counts[artifact_type] + 1} is next.",
                    level="warning",
                    details={"stage": artifact_type, "retry_count": stage_retry_counts[artifact_type]},
                )
                PROJECT_STORE.update_project(
                    project_id,
                    lambda state, artifact=artifact_type: state["artifacts"][artifact].update({"content": None}),
                )
                PROJECT_STORE.set_artifact_status(project_id, artifact_type, "pending")

        while True:
            project = PROJECT_STORE.read_project(project_id)
            image_jobs = _load_required_artifact(project, "image_jobs").get("jobs", [])
            current_index = int(project["image_queue"].get("current_index", 0))
            if current_index >= len(image_jobs):
                break
            job = image_jobs[current_index]
            accepted = False

            while image_retry_counts.get(job["job_id"], 0) < AUTOMATION_IMAGE_RETRY_LIMIT:
                attempt = image_retry_counts.get(job["job_id"], 0) + 1
                PROJECT_STORE.set_supervisor_state(project_id, mode="running")
                _write_supervisor_event(
                    project_id,
                    kind="image_batch_start",
                    message=f"Generating automated image batch {attempt} for {job['title']}.",
                    details={"job_id": job["job_id"], "attempt": attempt},
                )
                batch = _create_and_record_image_batch(
                    project_id=project_id,
                    job=job,
                    count=4,
                    runtime_task=f"Generating automated image batch for {job['title']}",
                    log_message=f"Automation requested image batch {attempt} for {job['title']}",
                    completed_task=f"automated image batch generated for {job['title']}",
                )
                project = PROJECT_STORE.read_project(project_id)
                inspections = []
                for candidate in batch["candidates"]:
                    image_path = str(PROJECTS_DIR / project_id / candidate["relative_path"])
                    try:
                        inspection = _inspect_image_candidate_with_recovery(
                            project_id=project_id,
                            project=project,
                            job=job,
                            candidate=candidate,
                            image_path=image_path,
                        )
                    except SupervisorError as last_vision_error:
                        recovery = getattr(last_vision_error, "recovery_result", None)
                        layer = _classify_supervision_layer(project, str(last_vision_error), "ollama_vision_review")
                        reason = (
                            f"Image generation worked, but vision review failed after recovery attempts. "
                            f"{last_vision_error}"
                            f"{_summarize_recovery_for_user(recovery)}"
                        ).strip()
                        _set_actionable_diagnosis(
                            project_id,
                            layer=layer,
                            stage=f"image_review:{job['job_id']}",
                            reason=reason,
                            next_action="Review the generated 4 images manually on the website, accept one or request 4 more, then continue automation.",
                            waiting_for_user=True,
                        )
                        PROJECT_STORE.set_status(project_id, "paused")
                        PROJECT_STORE.set_runtime(
                            project_id,
                            state_value="PAUSED",
                            current_task=f"Vision review paused for {job['title']}",
                            progress=100,
                            job_id=f"{project_id}:{job['job_id']}:vision-review",
                            last_error=str(last_vision_error),
                        )
                        _write_supervisor_event(
                            project_id,
                            kind="needs_user",
                            message=(
                                f"Image generation succeeded for {job['title']}, but vision review failed. "
                                f"Choose an image manually or request 4 more."
                            ),
                            level="error",
                            details={
                                "job_id": job["job_id"],
                                "candidate_id": candidate["candidate_id"],
                                "recovery": recovery,
                            },
                        )
                        return PROJECT_STORE.read_project(project_id)
                    inspections.append(inspection)

                PROJECT_STORE.set_supervisor_state(
                    project_id,
                    current_review=f"image_review:{job['job_id']}",
                    mode="reviewing",
                    stage_retry_counts=stage_retry_counts,
                    image_retry_counts=image_retry_counts,
                )
                image_paths = [str(PROJECTS_DIR / project_id / candidate["relative_path"]) for candidate in batch["candidates"]]
                decision = _run_supervisor_call(
                    project_id=project_id,
                    project=project,
                    stage=f"image_review:{job['job_id']}",
                    kind="image selection",
                    call=lambda: choose_image_candidate(
                        project=project,
                        job=job,
                        batch=batch,
                        inspections=inspections,
                        image_paths=image_paths,
                    ),
                )
                candidate_ids = {candidate["candidate_id"] for candidate in batch["candidates"]}
                chosen_candidate_id = decision["candidate_id"] if decision["candidate_id"] in candidate_ids else None
                if decision["action"] == "select" and not chosen_candidate_id:
                    chosen_candidate_id = _choose_fallback_candidate(batch, inspections)

                PROJECT_STORE.set_supervisor_state(
                    project_id,
                    current_review=f"image_review:{job['job_id']}",
                    last_decision=decision["action"],
                    last_rationale=decision["rationale"],
                    mode="reviewing",
                    stage_retry_counts=stage_retry_counts,
                    image_retry_counts=image_retry_counts,
                )
                _write_supervisor_event(
                    project_id,
                    kind="image_review_decision",
                    message=f"Ripa chose {decision['action']} for {job['title']}. {decision['rationale']}",
                    level="success" if decision["action"] == "select" else "warning",
                    details={"job_id": job["job_id"], "action": decision["action"]},
                )

                if decision["action"] == "pause":
                    _set_actionable_diagnosis(
                        project_id,
                        layer="native_openclaw",
                        stage=f"image_review:{job['job_id']}",
                        reason=decision["rationale"],
                        next_action="Open the latest image batch in the website, inspect the candidates, and continue after adjusting the project if needed.",
                        waiting_for_user=True,
                    )
                    _write_supervisor_event(
                        project_id,
                        kind="needs_user",
                        message=f"OpenClaw paused image review for {job['title']}. {decision['rationale']}",
                        level="error",
                        details={"job_id": job["job_id"], "action": "pause"},
                    )
                    return PROJECT_STORE.read_project(project_id)

                if decision["action"] == "select" and chosen_candidate_id:
                    PROJECT_STORE.accept_candidate(project_id, batch["batch_id"], chosen_candidate_id)
                    PROJECT_STORE.set_runtime(
                        project_id,
                        state_value="COMPLETED",
                        current_task=f"OpenClaw accepted image option for {job['title']}",
                        progress=100,
                        completed_task=f"OpenClaw accepted image for {job['title']}",
                    )
                    PROJECT_STORE.add_log(
                        project_id,
                        "success",
                        f"OpenClaw accepted {chosen_candidate_id} for {job['title']}: {decision['rationale']}",
                    )
                    _write_supervisor_event(
                        project_id,
                        kind="image_batch_complete",
                        message=f"Accepted candidate {chosen_candidate_id} for {job['title']}.",
                        level="success",
                        details={"job_id": job["job_id"], "candidate_id": chosen_candidate_id},
                    )
                    accepted = True
                    break

                image_retry_counts[job["job_id"]] = attempt
                PROJECT_STORE.set_supervisor_state(
                    project_id,
                    current_review=f"image_review:{job['job_id']}",
                    last_decision="redo",
                    last_rationale=decision["rationale"],
                    mode="retrying",
                    stage_retry_counts=stage_retry_counts,
                    image_retry_counts=image_retry_counts,
                )
                PROJECT_STORE.add_log(
                    project_id,
                    "warning",
                    f"OpenClaw requested redo for {job['title']} after batch {attempt}: {decision['rationale']}",
                )
                _write_supervisor_event(
                    project_id,
                    kind="retry",
                    message=f"Redoing image batch for {job['title']} after batch {attempt}.",
                    level="warning",
                    details={"job_id": job["job_id"], "retry_count": attempt},
                )

            if not accepted:
                _set_actionable_diagnosis(
                    project_id,
                    layer="comfyui",
                    stage=f"image_review:{job['job_id']}",
                    reason=f"Ripa could not approve an image for {job['title']} after {AUTOMATION_IMAGE_RETRY_LIMIT} batches.",
                    next_action="Open the latest image batch in the website, accept one manually or request more candidates, then resume automation.",
                    waiting_for_user=True,
                )
                _write_supervisor_event(
                    project_id,
                    kind="needs_user",
                    message=f"Image review is blocked for {job['title']}. I need a manual choice or edit.",
                    level="error",
                    details={"job_id": job["job_id"]},
                )
                raise RuntimeError(f"OpenClaw could not approve an image for {job['title']} after {AUTOMATION_IMAGE_RETRY_LIMIT} batches")

        PROJECT_STORE.set_status(project_id, "ready")
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="COMPLETED",
            current_task="Automation completed",
            progress=100,
            job_id=f"{project_id}:automation",
            completed_task="automation completed",
        )
        PROJECT_STORE.set_supervisor_state(
            project_id,
            mode="idle",
            waiting_for_user=False,
            actionable_diagnosis=None,
        )
        _write_supervisor_event(
            project_id,
            kind="automation_complete",
            message="Automation completed. Ripa is idle and watching.",
            level="success",
        )
        return PROJECT_STORE.add_log(project_id, "success", "OpenClaw automation completed")
    except Exception as exc:
        PROJECT_STORE.set_status(project_id, "failed")
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="FAILED",
            current_task="Automation failed",
            progress=100,
            job_id=f"{project_id}:automation",
            last_error=str(exc),
        )
        supervisor = PROJECT_STORE.read_project(project_id)["runtime"]["supervisor"]
        if not supervisor.get("actionable_diagnosis"):
            _set_actionable_diagnosis(
                project_id,
                layer="automation",
                stage=PROJECT_STORE.read_project(project_id).get("current_stage", "unknown"),
                reason=str(exc),
                next_action="Open the project status, inspect the latest logs, and decide whether to retry, revise, or fix the service dependency.",
                waiting_for_user=True,
            )
        _write_supervisor_event(
            project_id,
            kind="automation_failed",
            message=f"Automation stopped. {exc}",
            level="error",
        )
        PROJECT_STORE.add_log(project_id, "error", f"Automation failed: {exc}")
        raise
    finally:
        PROJECT_STORE.set_automation_active(project_id, False)
        current_project = PROJECT_STORE.read_project(project_id)
        waiting = current_project["runtime"]["supervisor"].get("waiting_for_user", False)
        mode = current_project["runtime"]["supervisor"].get("mode")
        PROJECT_STORE.set_supervisor_state(
            project_id,
            current_review=None,
            mode=mode if waiting else ("idle" if current_project["status"] == "ready" else mode),
        )


def _generate_artifact(project: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    story = _load_required_artifact(project, "story") if artifact_type != "story" else None
    characters = _load_required_artifact(project, "characters") if artifact_type in {"scenes", "subscenes", "dialogue", "image_jobs"} else None
    scenes = _load_required_artifact(project, "scenes") if artifact_type in {"subscenes", "dialogue", "image_jobs"} else None
    subscenes = _load_required_artifact(project, "subscenes") if artifact_type in {"dialogue", "image_jobs"} else None
    dialogue = _load_required_artifact(project, "dialogue") if artifact_type == "image_jobs" else None

    if artifact_type == "story":
        return generate_story_artifact(project["story_input"])
    if artifact_type == "characters":
        return generate_characters_artifact(story)
    if artifact_type == "scenes":
        return generate_scenes_artifact(story, characters)
    if artifact_type == "subscenes":
        return generate_subscenes_artifact(story, characters, scenes)
    if artifact_type == "dialogue":
        return generate_dialogue_artifact(story, characters, scenes, subscenes)
    if artifact_type == "image_jobs":
        return generate_image_jobs_artifact(story, characters, scenes, subscenes, dialogue)
    raise HTTPException(status_code=400, detail=f"Unsupported artifact type: {artifact_type}")


@app.post("/api/projects")
async def create_project(payload: ProjectCreateRequest) -> dict[str, Any]:
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Project title is required")
    if not payload.story_input.strip():
        raise HTTPException(status_code=400, detail="Story input is required")
    project = PROJECT_STORE.create_project(
        title=payload.title.strip(),
        story_input=payload.story_input.strip(),
        automation_mode=payload.automation_mode,
    )
    if payload.automation_mode:
        _schedule_supervised_automation(project["id"])
        return PROJECT_STORE.read_project(project["id"])
    return project


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    try:
        return PROJECT_STORE.read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.get("/api/projects/{project_id}/status")
async def get_project_status(project_id: str) -> dict[str, Any]:
    try:
        project = PROJECT_STORE.read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc

    return {
        "project_id": project["id"],
        "title": project["title"],
        "runtime": project["runtime"],
        "status": project["status"],
        "current_stage": project["current_stage"],
        "logs": project["logs"],
        "dependencies": {
            "ollama": _service_reachable(f"{os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')}/api/tags"),
            "comfyui": _service_reachable(f"http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}/system_stats"),
        },
        "supervisor": project["runtime"].get("supervisor", {}),
        "artifacts": project["artifacts"],
        "accepted_images": project["image_queue"]["accepted"],
    }


@app.post("/api/projects/{project_id}/supervisor/operator-note")
async def add_supervisor_operator_note(project_id: str, payload: SupervisorOperatorRequest) -> dict[str, Any]:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    try:
        PROJECT_STORE.add_supervisor_event(
            project_id,
            kind="operator_note",
            level="info",
            message=payload.message.strip(),
            details={"source": "operator"},
        )
        PROJECT_STORE.add_log(project_id, "info", f"Operator note: {payload.message.strip()}")
        return PROJECT_STORE.read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.put("/api/projects/{project_id}/draft")
async def update_project_draft(project_id: str, payload: ProjectDraftUpdateRequest) -> dict[str, Any]:
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Project title is required")
    if not payload.story_input.strip():
        raise HTTPException(status_code=400, detail="Story input is required")
    try:
        project = PROJECT_STORE.update_draft(
            project_id,
            title=payload.title.strip(),
            story_input=payload.story_input.strip(),
            automation_mode=payload.automation_mode,
        )
        PROJECT_STORE.add_log(project_id, "info", "Draft updated")
        if payload.automation_mode:
            _schedule_supervised_automation(project_id)
            return PROJECT_STORE.read_project(project_id)
        return PROJECT_STORE.read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.post("/api/projects/{project_id}/artifacts/{artifact_type}/generate")
async def generate_project_artifact(
    project_id: str,
    artifact_type: str,
    payload: ArtifactGenerateRequest,
) -> dict[str, Any]:
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported artifact type")

    try:
        project = PROJECT_STORE.read_project(project_id)
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="RUNNING",
            current_task=f"Generating {artifact_type} with Ollama",
            progress=_artifact_progress(artifact_type),
            job_id=f"{project_id}:{artifact_type}",
        )
        PROJECT_STORE.add_log(project_id, "info", f"Started {artifact_type} generation with Ollama")
        result = _generate_artifact(project, artifact_type)
        PROJECT_STORE.save_artifact(project_id, artifact_type, result)
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="COMPLETED",
            current_task=f"{artifact_type} generation completed",
            progress=_artifact_progress(artifact_type),
            job_id=f"{project_id}:{artifact_type}",
            completed_task=f"{artifact_type} generated",
        )
        return PROJECT_STORE.add_log(project_id, "success", f"Generated {artifact_type} artifact")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except OllamaError as exc:
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="FAILED",
            current_task=f"{artifact_type} generation failed",
            progress=_artifact_progress(artifact_type),
            job_id=f"{project_id}:{artifact_type}",
            last_error=str(exc),
        )
        PROJECT_STORE.add_log(project_id, "error", f"Ollama failed while generating {artifact_type}: {exc}")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/artifacts/{artifact_type}/save")
async def save_project_artifact(project_id: str, artifact_type: str, payload: ArtifactSaveRequest) -> dict[str, Any]:
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported artifact type")
    try:
        PROJECT_STORE.save_artifact(project_id, artifact_type, payload.content)
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="IDLE",
            current_task=f"{artifact_type} saved manually",
            progress=_artifact_progress(artifact_type),
            completed_task=f"{artifact_type} saved manually",
        )
        return PROJECT_STORE.add_log(project_id, "info", f"Saved manual edits for {artifact_type}")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/image-batches/next")
async def create_next_image_batch(project_id: str, payload: ImageBatchRequest) -> dict[str, Any]:
    try:
        project = PROJECT_STORE.read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc

    image_jobs = _load_required_artifact(project, "image_jobs").get("jobs", [])
    if not image_jobs:
        raise HTTPException(status_code=400, detail="Generate image_jobs before creating image batches")

    current_index = int(project["image_queue"].get("current_index", 0))
    if current_index >= len(image_jobs):
        raise HTTPException(status_code=400, detail="All image jobs have already been reviewed")

    job = image_jobs[current_index]
    try:
        _create_and_record_image_batch(
            project_id=project_id,
            job=job,
            count=payload.count,
            runtime_task=f"Generating image batch for {job['title']} with ComfyUI",
            log_message=f"Submitted image batch for {job['title']} to ComfyUI",
            completed_task=f"image batch generated for {job['title']}",
        )
        return PROJECT_STORE.add_log(project_id, "success", f"Generated image batch for {job['title']}")
    except ComfyUIError as exc:
        existing_batches = [batch for batch in project["image_queue"]["batches"] if batch["job_id"] == job["job_id"]]
        batch_index = len(existing_batches) + 1
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="FAILED",
            current_task=f"Image batch failed for {job['title']}",
            progress=100,
            job_id=f"{project_id}:{job['job_id']}:batch:{batch_index}",
            last_error=str(exc),
        )
        PROJECT_STORE.add_log(project_id, "error", f"ComfyUI failed for {job['title']}: {exc}")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/image-batches/{batch_id}/accept")
async def accept_image_batch_candidate(
    project_id: str,
    batch_id: str,
    payload: CandidateAcceptRequest,
) -> dict[str, Any]:
    try:
        PROJECT_STORE.accept_candidate(project_id, batch_id, payload.candidate_id)
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="IDLE",
            current_task=f"Accepted image candidate {payload.candidate_id}",
            progress=100,
            completed_task=f"accepted image candidate {payload.candidate_id}",
        )
        return PROJECT_STORE.add_log(project_id, "success", f"Accepted candidate {payload.candidate_id}")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/image-batches/{batch_id}/more")
async def generate_more_image_candidates(project_id: str, batch_id: str, payload: ImageBatchRequest) -> dict[str, Any]:
    try:
        project = PROJECT_STORE.read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc

    matching_batch = next((batch for batch in project["image_queue"]["batches"] if batch["batch_id"] == batch_id), None)
    if matching_batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    if matching_batch.get("status") == "accepted":
        raise HTTPException(status_code=400, detail="Cannot regenerate more candidates after acceptance")

    image_jobs = _load_required_artifact(project, "image_jobs").get("jobs", [])
    job = next((item for item in image_jobs if item["job_id"] == matching_batch["job_id"]), None)
    if job is None:
        raise HTTPException(status_code=400, detail="Image job not found for this batch")

    try:
        _create_and_record_image_batch(
            project_id=project_id,
            job=job,
            count=payload.count,
            runtime_task=f"Generating another image batch for {job['title']}",
            log_message=f"Requested another image batch for {job['title']}",
            completed_task=f"additional image batch generated for {job['title']}",
        )
        return PROJECT_STORE.add_log(project_id, "info", f"Generated another image batch for {job['title']}")
    except ComfyUIError as exc:
        existing_batches = [batch for batch in project["image_queue"]["batches"] if batch["job_id"] == job["job_id"]]
        batch_index = len(existing_batches) + 1
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="FAILED",
            current_task=f"Additional image batch failed for {job['title']}",
            progress=100,
            job_id=f"{project_id}:{job['job_id']}:batch:{batch_index}",
            last_error=str(exc),
        )
        PROJECT_STORE.add_log(project_id, "error", f"ComfyUI failed on additional batch for {job['title']}: {exc}")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/stop")
async def stop_project(project_id: str) -> dict[str, Any]:
    try:
        PROJECT_STORE.set_status(project_id, "paused")
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="PAUSED",
            current_task="Project paused by user",
        )
        return PROJECT_STORE.add_log(project_id, "warning", "Project paused")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.post("/api/projects/{project_id}/continue")
async def continue_project(project_id: str) -> dict[str, Any]:
    try:
        project = PROJECT_STORE.read_project(project_id)
        PROJECT_STORE.set_status(project_id, "draft")
        PROJECT_STORE.set_runtime(
            project_id,
            state_value="IDLE",
            current_task="Project resumed and waiting for the next action",
        )
        PROJECT_STORE.add_log(project_id, "info", "Project resumed")
        if project.get("automation_mode"):
            _schedule_supervised_automation(project_id)
            return PROJECT_STORE.read_project(project_id)
        return PROJECT_STORE.read_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.post("/api/projects/{project_id}/reset")
async def reset_project(project_id: str) -> dict[str, Any]:
    try:
        return PROJECT_STORE.reset_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.get("/api/tts/voices")
async def list_tts_voices() -> dict[str, Any]:
    return {
        "voices": discover_voice_options(),
        "alias_file": str(get_alias_map_path().resolve()),
    }


@app.get("/api/tts/aliases")
async def get_tts_aliases() -> dict[str, Any]:
    aliases = load_alias_map()
    return {
        "alice": aliases.get("alice"),
        "bob": aliases.get("bob"),
        "narrator": aliases.get("narrator"),
        "alias_file": str(get_alias_map_path().resolve()),
    }


@app.post("/api/tts/aliases")
async def set_tts_aliases(payload: AliasUpdateRequest) -> dict[str, Any]:
    try:
        return set_core_aliases(alice=payload.alice, bob=payload.bob, narrator=payload.narrator)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/story/save")
async def save_story(
    name: str = Form(...),
    mode: str = Form(...),
    story_text: str = Form(""),
    story_file: UploadFile | None = File(None),
) -> dict[str, Any]:
    if story_file is not None:
        try:
            uploaded_text = (await story_file.read()).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Story file must be valid UTF-8 text") from exc
        story_text = uploaded_text

    try:
        result = save_story_text(name=name, mode=mode, story_text=story_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "saved",
        **result,
    }


async def _read_companion_text(
    text_content: str,
    text_file: UploadFile | None,
) -> str:
    if text_file is not None:
        try:
            return (await text_file.read()).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Companion text file must be valid UTF-8 text") from exc
    return text_content


@app.post("/api/tts/assets/voice")
async def upload_voice_asset(
    asset_name: str = Form(...),
    audio_file: UploadFile = File(...),
    text_content: str = Form(""),
    text_file: UploadFile | None = File(None),
    overwrite: bool = Form(False),
) -> dict[str, Any]:
    reference_text = await _read_companion_text(text_content, text_file)
    try:
        result = save_voice_like_asset(
            category="voice",
            asset_name=asset_name,
            audio_filename=audio_file.filename or "upload.wav",
            audio_bytes=await audio_file.read(),
            reference_text=reference_text,
            overwrite=overwrite,
        )
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "saved",
        **result,
    }


@app.post("/api/tts/assets/reference")
async def upload_reference_asset(
    asset_name: str = Form(...),
    reference_kind: str = Form("emotion"),
    audio_file: UploadFile = File(...),
    text_content: str = Form(""),
    text_file: UploadFile | None = File(None),
    overwrite: bool = Form(False),
) -> dict[str, Any]:
    reference_text = await _read_companion_text(text_content, text_file)
    try:
        result = save_voice_like_asset(
            category=reference_kind,
            asset_name=asset_name,
            audio_filename=audio_file.filename or "upload.wav",
            audio_bytes=await audio_file.read(),
            reference_text=reference_text,
            overwrite=overwrite,
        )
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "saved",
        **result,
    }


@app.post("/api/tts/srt/report")
async def create_srt_report(
    input_label: str = Form("srt"),
    timing_mode: str = Form("pad_with_silence"),
    srt_text: str = Form(""),
    srt_file: UploadFile | None = File(None),
) -> dict[str, Any]:
    if srt_file is not None:
        try:
            srt_text = (await srt_file.read()).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="SRT upload must be valid UTF-8 text") from exc

    if not srt_text.strip():
        raise HTTPException(status_code=400, detail="Provide pasted SRT text or upload a text/SRT file")

    try:
        return build_srt_analysis_report(srt_text, input_label=input_label, timing_mode=timing_mode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs")
async def create_job(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": None,
        "status": "redirected",
        "message": "Use /api/projects instead of the legacy /api/jobs endpoint.",
        "received": payload,
    }


@app.post("/api/upload", response_model=UploadResponse)
async def upload_asset(file: UploadFile = File(...), asset_type: str = Form("unknown")) -> UploadResponse:
    suffix = Path(file.filename or "upload.bin").suffix
    asset_id = str(uuid.uuid4())
    filename = f"{asset_id}{suffix}"
    destination = ASSETS_DIR / filename
    destination.write_bytes(await file.read())
    return UploadResponse(asset_id=asset_id, path=f"assets/{filename}")


@app.get("/api/agent/status")
async def get_agent_status() -> dict[str, Any]:
    return _idle_status()


@app.get("/api/agent/pending_action")
async def get_pending_action() -> dict[str, Any]:
    return {"action": None}


@app.post("/api/agent/response")
async def submit_response(response: ActionResponse) -> dict[str, Any]:
    return {
        "status": "ignored",
        "message": "No interactive backend actions are waiting in placeholder mode.",
        "action_id": response.action_id,
    }


@app.get("/api/agent/artifacts/{job_id}")
async def get_artifacts(job_id: str) -> list[dict[str, Any]]:
    return []


@app.get("/api/media/{filename}")
async def get_media(filename: str) -> FileResponse:
    target = ASSETS_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.get("/api/projects/{project_id}/files/{file_path:path}")
async def get_project_file(project_id: str, file_path: str) -> FileResponse:
    project_root = (PROJECTS_DIR / project_id).resolve()
    target = (project_root / file_path).resolve()
    if project_root not in target.parents and target != project_root:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
