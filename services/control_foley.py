"""Typed Control-Foley jobs backed by fixed ComfyUI API workflows."""

from __future__ import annotations

import json
import shutil
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .media_jobs import MediaJobError, collect_outputs, submit_and_wait


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_ROOT = ROOT / "workflows" / "api" / "audio" / "control_foley"
WORKFLOWS = {
    "text_audio": WORKFLOW_ROOT / "text_audio_api.json",
    "text_video_audio": WORKFLOW_ROOT / "text_video_audio_api.json",
    "reference_video_audio": WORKFLOW_ROOT / "reference_video_audio_api.json",
}
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}
REQUIRED_NODES = {"LoadControlFoleyModel", "ControlFoleyGenerate", "SaveControlFoleyAudio"}


class ControlFoleyError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def schema() -> dict[str, Any]:
    shared = {
        "duration": {"type": "number", "minimum": 0.7, "maximum": 30, "default": 8},
        "seed": {"type": "integer", "minimum": 0, "maximum": 4294967295, "default": 42},
        "steps": {"type": ["integer", "string"], "minimum": 1, "maximum": 100, "default": "fixed"},
        "guidance": {"type": "number", "minimum": 0, "maximum": 20, "default": 4.5},
        "fps": {"type": "number", "minimum": 1, "maximum": 120, "default": 24},
    }
    return {"modes": [
        {"id": "text_audio", "label": "Text → Audio", "requires": ["prompt"], "properties": shared},
        {"id": "text_video_audio", "label": "Text + Video → Audio", "requires": ["prompt", "video"], "properties": shared},
        {"id": "reference_video_audio", "label": "Reference Audio + Video → Audio", "requires": ["reference_audio", "video"], "properties": shared},
    ]}


def capabilities(comfy_url: str, comfy_root: Path) -> dict[str, Any]:
    model = comfy_root / "models" / "controlfoley" / "weights" / "controlfoley.pth"
    try:
        with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/object_info", timeout=10) as response:
            nodes = json.loads(response.read().decode("utf-8"))
        online = True
    except Exception:
        nodes, online = {}, False
    missing = sorted(REQUIRED_NODES - set(nodes))
    return {
        "status": "available" if online and model.is_file() and not missing else "blocked",
        "comfyui_online": online, "model": str(model), "model_ready": model.is_file(),
        "missing_nodes": missing, "schema": schema(),
    }


def _number(settings: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    try: value = float(settings.get(key, default))
    except (TypeError, ValueError) as exc: raise ControlFoleyError(f"{key} must be numeric") from exc
    if not low <= value <= high: raise ControlFoleyError(f"{key} must be between {low} and {high}")
    return value


def validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    mode = str(settings.get("mode", "text_audio"))
    if mode not in WORKFLOWS: raise ControlFoleyError("Unknown Control-Foley mode")
    prompt = str(settings.get("prompt", "")).strip()
    if mode in {"text_audio", "text_video_audio"} and not prompt:
        raise ControlFoleyError("A sound description is required for this mode")
    raw_steps = settings.get("steps", "fixed")
    if str(raw_steps).strip().lower() != "fixed":
        try: steps: str | int = int(raw_steps)
        except (TypeError, ValueError) as exc: raise ControlFoleyError("steps must be fixed or an integer") from exc
        if not 1 <= steps <= 100: raise ControlFoleyError("steps must be between 1 and 100")
    else: steps = "fixed"
    seed = int(settings.get("seed", 42))
    if not 0 <= seed <= 4294967295: raise ControlFoleyError("seed is out of range")
    return {"mode": mode, "prompt": prompt, "negative_prompt": str(settings.get("negative_prompt", "")).strip(),
            "duration": _number(settings, "duration", 8, .7, 30), "seed": seed, "steps": steps,
            "guidance": _number(settings, "guidance", 4.5, 0, 20), "fps": _number(settings, "fps", 24, 1, 120),
            "device": str(settings.get("device", "auto")), "precision": str(settings.get("precision", "bf16"))}


def new_job(settings: dict[str, Any]) -> dict[str, Any]:
    return {"job_id": f"control-foley-{uuid.uuid4().hex[:10]}", "kind": "control_foley", "status": "queued",
            "created_at": utc_now(), "settings": validate_settings(settings), "inputs": {}, "outputs": [], "error": None}


def stage_inputs(*, project_dir: Path, comfy_input_dir: Path, job: dict[str, Any],
                 video: tuple[str, bytes] | None, reference_audio: tuple[str, bytes] | None) -> dict[str, str]:
    mode = job["settings"]["mode"]
    if mode != "text_audio" and video is None: raise ControlFoleyError("A video file is required for this mode")
    if mode == "text_audio" and video is not None: raise ControlFoleyError("Text → Audio does not accept video")
    if mode == "reference_video_audio" and reference_audio is None: raise ControlFoleyError("Reference audio is required")
    if mode != "reference_video_audio" and reference_audio is not None: raise ControlFoleyError("Reference audio is not accepted for this mode")
    project_stage = project_dir / "music" / "control_foley" / "inputs" / job["job_id"]
    comfy_stage = comfy_input_dir / "story_builder_control_foley" / job["job_id"]
    project_stage.mkdir(parents=True, exist_ok=True); comfy_stage.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for key, item, allowed in (("video", video, VIDEO_SUFFIXES), ("reference_audio", reference_audio, AUDIO_SUFFIXES)):
        if item is None: continue
        name, content = item; suffix = Path(name).suffix.lower()
        if suffix not in allowed or not content: raise ControlFoleyError(f"Unsupported or empty {key.replace('_', ' ')}")
        project_path = project_stage / f"{key}{suffix}"; project_path.write_bytes(content)
        comfy_path = comfy_stage / project_path.name; shutil.copy2(project_path, comfy_path)
        result[key] = str(Path("story_builder_control_foley") / job["job_id"] / comfy_path.name)
    job["inputs"] = result
    return result


def build_workflow(job: dict[str, Any]) -> dict[str, Any]:
    settings, inputs = job["settings"], job["inputs"]
    workflow = json.loads(WORKFLOWS[settings["mode"]].read_text(encoding="utf-8"))
    workflow["1"]["inputs"].update(device=settings["device"], precision=settings["precision"])
    generator = "2" if settings["mode"] == "text_audio" else "3"
    save = "3" if settings["mode"] == "text_audio" else "4"
    workflow[generator]["inputs"].update(prompt=settings["prompt"], negative_prompt=settings["negative_prompt"], duration=settings["duration"], seed=settings["seed"], num_inference_steps=str(settings["steps"]), guidance_scale=settings["guidance"], image_fps=settings["fps"])
    if settings["mode"] != "text_audio":
        workflow["2"]["inputs"].update(video_path=inputs["video"], duration=settings["duration"])
    if settings["mode"] == "reference_video_audio": workflow[generator]["inputs"]["reference_audio_path"] = inputs["reference_audio"]
    workflow[save]["inputs"]["filename_prefix"] = f"story_builder/control_foley/{job['job_id']}"
    return workflow


def run_job(job: dict[str, Any], *, project_dir: Path, output_root: Path, comfy_url: str, progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    run_dir = project_dir / "music" / "control_foley" / "runs" / job["job_id"]
    run_dir.mkdir(parents=True, exist_ok=True); job.update(status="running", started_at=utc_now()); progress(job)
    if job.get("prompt_id"):
        job.update(status="recovery_required", error="Reconcile the saved prompt before retrying."); progress(job); return job
    job["prompt_id"] = str(uuid.uuid4())
    progress(job)  # Durable reservation before POST; a crash must not create a duplicate.
    try:
        workflow = build_workflow(job)
        (run_dir / "request.json").write_text(json.dumps(job["settings"], indent=2), encoding="utf-8")
        (run_dir / "workflow.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        prompt_id, history = submit_and_wait(workflow, comfy_url=comfy_url, timeout_seconds=1800, prompt_id=job["prompt_id"])
        media_dir = output_root / project_dir.name / "audio" / job["job_id"] if job.get("production_sidecar") else run_dir
        outputs = collect_outputs(history, destination_dir=media_dir, comfy_url=comfy_url)
        for output in outputs: output["relative_path"] = str((media_dir / output["filename"]).relative_to(output_root / project_dir.name if job.get("production_sidecar") else project_dir))
        primary = next((item for item in outputs if item["kind"] == "audio"), None)
        if primary is None: raise ControlFoleyError("Control-Foley completed without a collectible audio output")
        export_dir = output_root / project_dir.name / "audio"; export_dir.mkdir(parents=True, exist_ok=True)
        source = media_dir / primary["filename"]; export = source if job.get("production_sidecar") else export_dir / f"{job['job_id']}{source.suffix}"
        if export != source: shutil.copy2(source, export)
        job.update(status="completed", completed_at=utc_now(), prompt_id=prompt_id, outputs=outputs, primary_output=primary, export_path=str(export))
    except Exception as exc: job.update(status="recovery_required" if isinstance(exc, MediaJobError) and exc.remote_state_unknown else "failed", completed_at=utc_now(), error=str(exc))
    progress(job); return job
