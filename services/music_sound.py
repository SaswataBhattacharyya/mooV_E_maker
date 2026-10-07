"""Fixed ACE-Step music jobs and fine-tuning capability contracts."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .media_jobs import MediaJobError, collect_outputs, submit_and_wait


ROOT = Path(__file__).resolve().parent.parent
ACE_WORKFLOW = ROOT / "workflows" / "api" / "audio" / "ace_step_music_api.json"
COMFY_ROOT = Path(os.environ.get("COMFYUI_ROOT", "/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI"))
ACE_CHECKPOINT = COMFY_ROOT / "models" / "checkpoints" / "ace_step_v1_3.5b.safetensors"
ACE_SOURCE = ROOT / "audio" / "song_gen" / "ACE-Step"


class MusicSoundError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capabilities(comfy_online: bool) -> dict[str, Any]:
    return {
        "comfyui_online": comfy_online,
        "ace": {"status": "available" if comfy_online and ACE_CHECKPOINT.is_file() else "blocked", "checkpoint": str(ACE_CHECKPOINT), "checkpoint_size": ACE_CHECKPOINT.stat().st_size if ACE_CHECKPOINT.exists() else 0},
        "finetune": ace_finetune_preflight(),
    }


def ace_finetune_preflight() -> dict[str, Any]:
    checks = [
        {"name": "source", "ok": ACE_SOURCE.is_dir(), "detail": str(ACE_SOURCE)},
        {"name": "triplet_converter", "ok": (ACE_SOURCE / "convert2hf_dataset.py").is_file(), "detail": "Strict MP3/prompt/lyrics converter"},
        {"name": "trainer", "ok": (ACE_SOURCE / "trainer.py").is_file(), "detail": "LoRA trainer source"},
        {"name": "standalone_checkpoints", "ok": (ACE_SOURCE / "checkpoints").is_dir(), "detail": "Required for bounded training smoke test"},
        {"name": "docker", "ok": bool(shutil.which("docker")), "detail": shutil.which("docker") or "not installed"},
        {"name": "architecture", "ok": os.uname().machine == "aarch64", "detail": os.uname().machine},
    ]
    return {"status": "preparation_ready" if all(row["ok"] for row in checks[:3]) else "blocked", "smoke_ready": all(row["ok"] for row in checks), "full_training_enabled": False, "checks": checks}


def validate_music_settings(settings: dict[str, Any]) -> dict[str, Any]:
    mode = str(settings.get("mode", "instrumental"))
    if mode not in {"instrumental", "song"}: raise MusicSoundError("mode must be instrumental or song")
    tags = str(settings.get("tags", "")).strip()
    if not tags: raise MusicSoundError("Music tags are required")
    lyrics = str(settings.get("lyrics", "")).strip()
    if mode == "song" and not lyrics: raise MusicSoundError("Structured lyrics are required for song mode")
    duration = float(settings.get("duration", 30))
    if not 5 <= duration <= 240: raise MusicSoundError("duration must be between 5 and 240 seconds")
    return {"mode": mode, "tags": tags, "lyrics": lyrics or "[instrumental]", "duration": duration,
            "seed": int(settings.get("seed", 1)), "steps": max(1, min(100, int(settings.get("steps", 50)))),
            "cfg": max(1.0, min(20.0, float(settings.get("cfg", 5)))), "shift": max(1.0, min(10.0, float(settings.get("shift", 5)))),
            "lyrics_strength": max(0.0, min(1.0, float(settings.get("lyrics_strength", .99)))),
            "sampler": str(settings.get("sampler", "euler")), "scheduler": str(settings.get("scheduler", "simple"))}


def new_music_job(settings: dict[str, Any]) -> dict[str, Any]:
    validated = validate_music_settings(settings)
    return {"job_id": f"music-ace-{uuid.uuid4().hex[:10]}", "kind": "ace_music", "status": "queued", "created_at": utc_now(), "settings": validated, "outputs": [], "error": None}


def build_ace_workflow(job: dict[str, Any]) -> dict[str, Any]:
    workflow = json.loads(ACE_WORKFLOW.read_text(encoding="utf-8")); settings = job["settings"]
    workflow["2"]["inputs"]["seconds"] = settings["duration"]
    workflow["3"]["inputs"].update(tags=settings["tags"], lyrics=settings["lyrics"], lyrics_strength=settings["lyrics_strength"])
    workflow["5"]["inputs"]["shift"] = settings["shift"]
    workflow["8"]["inputs"].update(seed=settings["seed"], steps=settings["steps"], cfg=settings["cfg"], sampler_name=settings["sampler"], scheduler=settings["scheduler"])
    workflow["10"]["inputs"]["filename_prefix"] = f"story_builder/music/{job['job_id']}"
    return workflow


def run_music_job(job: dict[str, Any], *, project_dir: Path, output_root: Path, comfy_url: str, progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    job.update(status="running", started_at=utc_now()); progress(job)
    run_dir = project_dir / "music" / "runs" / job["job_id"]; run_dir.mkdir(parents=True, exist_ok=True)
    if job.get("prompt_id"):
        job.update(status="recovery_required", error="Reconcile the saved prompt before retrying."); progress(job); return job
    job["prompt_id"] = str(uuid.uuid4())
    progress(job)  # Durable reservation before POST; a crash must not create a duplicate.
    try:
        workflow = build_ace_workflow(job); (run_dir / "request.json").write_text(json.dumps(job["settings"], indent=2), encoding="utf-8"); (run_dir / "workflow.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        prompt_id, history = submit_and_wait(workflow, comfy_url=comfy_url, timeout_seconds=1800, prompt_id=job["prompt_id"])
        media_dir = output_root / project_dir.name / "audio" / job["job_id"] if job.get("production_sidecar") else run_dir
        outputs = collect_outputs(history, destination_dir=media_dir, comfy_url=comfy_url)
        if not outputs: raise MusicSoundError("ComfyUI completed without a collectible audio output")
        for output in outputs: output["relative_path"] = str((media_dir / output["filename"]).relative_to(output_root / project_dir.name if job.get("production_sidecar") else project_dir))
        job.update(status="completed", prompt_id=prompt_id, outputs=outputs, primary_output=next((row for row in outputs if row["kind"] == "audio"), outputs[0]))
        export_dir = output_root / project_dir.name / "audio"; export_dir.mkdir(parents=True, exist_ok=True)
        source = media_dir / job["primary_output"]["filename"]; export = source if job.get("production_sidecar") else export_dir / f"{job['job_id']}{source.suffix}"
        if export != source: shutil.copy2(source, export)
        job["export_path"] = str(export)
    except Exception as exc:
        job.update(status="recovery_required" if isinstance(exc, MediaJobError) and exc.remote_state_unknown else "failed", error=str(exc))
    job["completed_at"] = utc_now(); progress(job); return job
