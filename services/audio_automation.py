"""Typed, ordered audio automation registry and runner."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .audio_catalog import discover_voices
from .audio_effects import new_effect_job, run_effect_job
from .audio_scene import new_scene_job, run_split, run_stitch, validate_edits
from .audio_tts import build_workflow, new_job as new_tts_job, prepare_srt, run_timed_job
from .music_sound import new_music_job, run_music_job
from .control_foley import new_job as new_foley_job, run_job as run_foley_job


class AutomationError(ValueError): pass


def utc_now() -> str: return datetime.now(timezone.utc).isoformat()


BLOCKS: dict[str, dict[str, Any]] = {
    "timed_tts": {"label": "Timed Multi-Character TTS", "inputs": {}, "outputs": {"audio": "audio", "srt": "srt"}, "parameters": {"required": ["srt_content"], "fields": {"srt_content": "srt", "language": "string", "seed": "integer", "timing_mode": "string"}}},
    "split_audio": {"label": "Split Audio", "inputs": {"source_audio": "audio"}, "outputs": {"clips": "audio_collection", "manifest": "json", "split_job": "split_job"}, "parameters": {"required": ["edits"], "fields": {"edits": "json", "transcript": "string"}}},
    "emotion": {"label": "Emotion Change", "inputs": {"source_audio": "audio"}, "outputs": {"audio": "audio"}, "parameters": {"required": ["transcript", "emotion"], "fields": {"transcript": "string", "emotion": "string", "iterations": "integer"}}},
    "style": {"label": "Style Change", "inputs": {"source_audio": "audio"}, "outputs": {"audio": "audio"}, "parameters": {"required": ["transcript", "style"], "fields": {"transcript": "string", "style": "string", "iterations": "integer"}}},
    "voice_repair": {"label": "Voice Repair", "inputs": {"source_audio": "audio"}, "outputs": {"audio": "audio"}, "parameters": {"fields": {"restoration_mode": "integer"}}},
    "voice_changer": {"label": "Voice Changer", "inputs": {"source_audio": "audio"}, "outputs": {"audio": "audio"}, "parameters": {"required": ["target_voice_id"], "fields": {"target_voice_id": "string"}}},
    "rvc": {"label": "RVC Voice/Pitch", "inputs": {"source_audio": "audio"}, "outputs": {"audio": "audio"}, "parameters": {"required": ["model"], "fields": {"model": "string", "pitch": "integer"}}},
    "stitch_audio": {"label": "Stitch Audio", "inputs": {"split": "split_job", "replacements": "audio_map"}, "outputs": {"audio": "audio"}, "parameters": {"fields": {"mode": "string", "gaps": "json"}}},
    "noise_cleanup": {"label": "Noise Cleanup", "inputs": {"source_audio": "audio"}, "outputs": {"audio": "audio"}, "parameters": {"fields": {"model": "string", "dry": "number"}}, "executor": "audio_utilities"},
    "demucs_stems": {"label": "Demucs Stems", "inputs": {"source_audio": "audio"}, "outputs": {"clips": "audio_collection"}, "parameters": {"fields": {"stems": "integer", "device": "string"}}, "executor": "audio_utilities"},
    "ace_music": {"label": "ACE-Step Music", "inputs": {}, "outputs": {"audio": "audio"}, "parameters": {"required": ["tags"], "fields": {"tags": "string", "lyrics": "string", "duration": "number"}}, "executor": "music"},
    "control_foley": {"label": "Control-Foley", "inputs": {}, "outputs": {"audio": "audio"}, "parameters": {"required": ["mode"], "fields": {"mode": "string", "prompt": "string"}}, "executor": "control_foley"},
}


def registry() -> list[dict[str, Any]]:
    return [{"id": key, "executor": value.get("executor", "audio"), **copy.deepcopy(value)} for key, value in BLOCKS.items()]


def validate_pipeline(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []; steps = payload.get("steps")
    if not isinstance(steps, list) or not steps: return ["Pipeline must contain at least one step"]
    seen: dict[str, str] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict): errors.append(f"Step {index + 1} must be an object"); continue
        step_id, operation = str(step.get("id", "")).strip(), str(step.get("operation", ""))
        if not step_id: errors.append(f"Step {index + 1} needs an id")
        elif step_id in seen: errors.append(f"Duplicate step id: {step_id}")
        if operation not in BLOCKS: errors.append(f"Unknown operation: {operation}"); continue
        parameters = step.get("parameters", {})
        if not isinstance(parameters, dict): errors.append(f"{step_id}: parameters must be an object"); parameters = {}
        for required in BLOCKS[operation].get("parameters", {}).get("required", []):
            if parameters.get(required) in (None, "", []): errors.append(f"{step_id}: missing parameter {required}")
        inputs = step.get("inputs", {})
        if not isinstance(inputs, dict): errors.append(f"{step_id}: inputs must be an object"); inputs = {}
        for name in BLOCKS[operation].get("inputs", {}):
            if name not in inputs and not (operation == "stitch_audio" and name == "replacements"):
                errors.append(f"{step_id}: missing input {name}")
        for name, binding in inputs.items():
            if isinstance(binding, dict) and "step" in binding:
                source = str(binding["step"])
                if source not in seen: errors.append(f"{step_id}.{name}: source step must appear earlier")
                elif str(binding.get("output", "audio")) not in BLOCKS[seen[source]].get("outputs", {}): errors.append(f"{step_id}.{name}: unknown source output")
        if step_id: seen[step_id] = operation
    return errors


def new_pipeline(payload: dict[str, Any], creator: str = "user") -> dict[str, Any]:
    errors = validate_pipeline(payload)
    return {"pipeline_id": f"audio-pipeline-{uuid.uuid4().hex[:10]}", "version": 1, "name": str(payload.get("name", "Audio pipeline")).strip() or "Audio pipeline", "creator": creator, "steps": payload.get("steps", []), "validation_errors": errors, "valid": not errors, "created_at": utc_now(), "updated_at": utc_now()}


def new_run(pipeline: dict[str, Any]) -> dict[str, Any]:
    errors = validate_pipeline(pipeline)
    if errors: raise AutomationError("; ".join(errors))
    return {"run_id": f"audio-run-{uuid.uuid4().hex[:10]}", "pipeline_id": pipeline["pipeline_id"], "pipeline_version": pipeline["version"], "status": "queued", "created_at": utc_now(), "steps": [{"step_id": step["id"], "operation": step["operation"], "status": "pending", "job": None, "outputs": {}} for step in pipeline["steps"]], "error": None}


def _binding_path(binding: dict[str, Any], completed: dict[str, dict[str, Any]], project_dir: Path) -> Path:
    source = completed.get(str(binding.get("step")))
    if source is None: raise AutomationError("Bound source step has no completed output")
    output = str(binding.get("output", "audio")); value = source["outputs"].get(output)
    if output == "clips":
        index = int(binding.get("clip_index", 0)); clips = value or []
        match = next((item for item in clips if int(item.get("clip_index", -1)) == index), None)
        if match is None: raise AutomationError(f"Clip index {index} was not produced")
        value = match["relative_path"]
    if not isinstance(value, str): raise AutomationError("Binding does not resolve to one file")
    path = (project_dir / value).resolve()
    if project_dir.resolve() not in path.parents or not path.is_file(): raise AutomationError("Resolved artifact is missing or unsafe")
    return path


def run_pipeline(*, pipeline: dict[str, Any], run: dict[str, Any], project_id: str, project_dir: Path, output_root: Path, comfy_input_dir: Path, comfy_url: str, character_map: dict[str, Any], update: Callable[[dict[str, Any]], None], start_index: int = 0) -> None:
    completed = {item["step_id"]: item for item in run["steps"] if item["status"] == "completed"}
    run.update(status="running", started_at=run.get("started_at") or utc_now(), error=None); update(run)
    try:
        for index, definition in enumerate(pipeline["steps"]):
            if index < start_index and definition["id"] in completed: continue
            state = run["steps"][index]; state.update(status="running", error=None); update(run)
            operation, params, inputs = definition["operation"], copy.deepcopy(definition.get("parameters", {})), definition.get("inputs", {})
            current: dict[str, Any]
            if operation == "timed_tts":
                srt = str(params.pop("srt_content")); rewritten, resolved = prepare_srt(srt, character_map.get("characters", []), discover_voices())
                defaults = {"language": "English", "seed": 1, "timing_mode": "smart_natural", "exaggeration": .5, "temperature": .8, "cfg_weight": .5, "enable_audio_cache": True, "fade": .01, "max_stretch_ratio": 1, "min_stretch_ratio": .5, "timing_tolerance": 2, "batch_size": 0}; defaults.update(params)
                current = new_tts_job(defaults, resolved, srt.strip() + "\n", rewritten)
                workflow = build_workflow(rewritten_srt=rewritten, narrator=resolved["narrator"], settings=defaults, filename_prefix=f"story_builder/{project_id}/{current['job_id']}")
                run_timed_job(project_id=project_id, project_dir=project_dir, output_root=output_root, job=current, workflow=workflow, comfy_url=comfy_url, update=lambda changes: current.update(changes))
                audio = next(item["relative_path"] for item in current.get("outputs", []) if item["kind"] == "audio")
                outputs = {"audio": audio, "srt": current.get("reports", {}).get("adjusted.srt")}
            elif operation == "split_audio":
                source = _binding_path(inputs["source_audio"], completed, project_dir); edits = validate_edits(params.get("edits")); current = new_scene_job("split")
                run_split(job=current, project_dir=project_dir, source=source, edits=edits, transcript=params.get("transcript"), update=lambda changes: current.update(changes))
                outputs = {"clips": current.get("manifest", {}).get("clips", []), "manifest": current.get("manifest_path"), "split_job": current}
            elif operation in {"emotion", "style", "voice_repair", "voice_changer", "rvc"}:
                source = _binding_path(inputs["source_audio"], completed, project_dir); current = new_effect_job(operation, params, source)
                run_effect_job(project_id=project_id, project_dir=project_dir, output_root=output_root, comfy_input_dir=comfy_input_dir, comfy_url=comfy_url, job=current, source=source, update=lambda changes: current.update(changes))
                outputs = {"audio": current.get("primary_output", {}).get("relative_path")}
            elif operation == "stitch_audio":
                split_source = completed[str(inputs["split"]["step"])]; split_job = split_source["outputs"].get("split_job")
                if not split_job: raise AutomationError("Stitch requires a Split Audio step")
                replacements: dict[int, Path] = {}
                for row in inputs.get("replacements", []): replacements[int(row["clip_index"])] = _binding_path(row, completed, project_dir)
                current = new_scene_job("stitch", parent_job_id=split_job["job_id"], mode=params.get("mode", "simple"))
                run_stitch(job=current, project_dir=project_dir, split_job=split_job, replacements=replacements, gaps={int(k): float(v) for k, v in params.get("gaps", {}).items()}, mode=params.get("mode", "simple"), output_root=output_root, update=lambda changes: current.update(changes))
                outputs = {"audio": current.get("output_path")}
            elif operation == "ace_music":
                current = new_music_job(params)
                run_music_job(current, project_dir=project_dir, output_root=output_root, comfy_url=comfy_url, progress=lambda changes: None)
                outputs = {"audio": current.get("primary_output", {}).get("relative_path")}
            elif operation == "control_foley":
                current = new_foley_job(params)
                # Text→audio requires no uploaded inputs.  Input-bearing modes
                # can be supplied by a future explicit binding; fail clearly
                # rather than silently running with the wrong source.
                if current["settings"]["mode"] != "text_audio":
                    raise AutomationError("Control-Foley video/reference modes require explicit file inputs")
                run_foley_job(current, project_dir=project_dir, output_root=output_root, comfy_url=comfy_url, progress=lambda changes: None)
                outputs = {"audio": current.get("primary_output", {}).get("relative_path")}
            else: raise AutomationError(f"{operation} is registered for composition but its pipeline adapter is not enabled yet")
            if current.get("status") != "completed": raise AutomationError(current.get("error") or f"{operation} failed")
            state.update(status="completed", job=current, outputs=outputs, completed_at=utc_now()); completed[definition["id"]] = state; update(run)
        run.update(status="completed", completed_at=utc_now(), final_output=run["steps"][-1]["outputs"].get("audio")); update(run)
    except Exception as exc:
        state.update(status="failed", error=str(exc), completed_at=utc_now()); run.update(status="failed", error=str(exc), completed_at=utc_now()); update(run)
