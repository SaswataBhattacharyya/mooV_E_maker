"""Fixed ComfyUI audio-effect workflows for Audio Studio and Hermes."""

from __future__ import annotations

import json
import os
import shutil
import uuid
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import soundfile as sf

from .audio_catalog import comfy_voice_key, discover_voices
from .media_jobs import collect_outputs, submit_and_wait


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_ROOT = ROOT / "workflows" / "api" / "audio"
OPERATION_WORKFLOWS = {
    "noise_cleanup": WORKFLOW_ROOT / "noise_cleanup_api.json",
    "voice_repair": WORKFLOW_ROOT / "voice_repair_api.json",
    "voice_changer": WORKFLOW_ROOT / "voice_changer_api.json",
    "rvc": WORKFLOW_ROOT / "rvc_voice_api.json",
    "emotion": WORKFLOW_ROOT / "emotion_edit_api.json",
    "style": WORKFLOW_ROOT / "style_edit_api.json",
}
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}
EMOTIONS = {"happy", "sad", "angry", "excited", "calm", "fearful", "surprised", "disgusted", "confusion", "empathy", "embarrass", "depressed", "coldness", "admiration", "remove"}
STYLES = {"whisper", "serious", "child", "older", "girl", "pure", "sister", "sweet", "exaggerated", "ethereal", "generous", "recite", "act_coy", "warm", "shy", "comfort", "authority", "chat", "radio", "soulful", "gentle", "story", "vivid", "program", "news", "advertising", "roar", "murmur", "shout", "deeply", "loudly", "arrogant", "friendly", "remove"}
RVC_ROOT = Path(os.environ.get("COMFYUI_ROOT", "/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI")) / "models" / "TTS" / "RVC"


class AudioEffectError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def effect_capabilities() -> list[dict[str, Any]]:
    return [
        {"id": "voice_repair", "phase": 6, "label": "Voice Repair", "status": "available", "requires": ["VoiceFixerNode"]},
        {"id": "voice_changer", "phase": 7, "label": "Voice Changer", "status": "available", "requires": ["UnifiedVoiceChangerNode", "ChatterBoxEngineNode"]},
        {"id": "rvc", "phase": 7, "label": "RVC Voice/Pitch", "status": "available", "requires": ["RVCEngineNode", "LoadRVCModelNode", "UnifiedVoiceChangerNode"]},
        {"id": "emotion", "phase": 8, "label": "Emotion Change", "status": "available", "requires": ["StepAudioEditXEngineNode", "StepAudioEditXAudioEditorNode"]},
        {"id": "style", "phase": 8, "label": "Style Change", "status": "available", "requires": ["StepAudioEditXEngineNode", "StepAudioEditXAudioEditorNode"]},
    ]


def discover_rvc_models() -> list[dict[str, Any]]:
    if not RVC_ROOT.is_dir():
        return []
    indexes = sorted((RVC_ROOT / ".index").glob("*.index")) if (RVC_ROOT / ".index").is_dir() else []
    rows: list[dict[str, Any]] = []
    for model in sorted(RVC_ROOT.glob("*.pth")):
        stem = model.stem.casefold()
        matched = [path for path in indexes if stem.split("_v")[0] in path.stem.casefold()]
        rows.append({
            "id": model.name, "name": model.stem, "path": str(model), "size": model.stat().st_size,
            "indexes": [{"id": path.name, "path": str(path), "size": path.stat().st_size} for path in matched],
        })
    return rows


def safe_project_source(project_dir: Path, relative_path: str) -> Path:
    target = (project_dir / relative_path).resolve()
    root = project_dir.resolve()
    if target != root and root not in target.parents:
        raise AudioEffectError("Project audio path escapes the project directory")
    if not target.is_file() or target.suffix.lower() not in AUDIO_SUFFIXES:
        raise AudioEffectError("Project audio source is missing or unsupported")
    return target


def stage_source(*, project_dir: Path, operation: str, source_name: str, source_bytes: bytes) -> Path:
    suffix = Path(source_name).suffix.lower()
    if suffix not in AUDIO_SUFFIXES or not source_bytes:
        raise AudioEffectError("A non-empty supported audio source is required")
    staging = project_dir / "audio" / "effect_inputs"
    staging.mkdir(parents=True, exist_ok=True)
    target = staging / f"{operation}-{uuid.uuid4().hex[:12]}{suffix}"
    target.write_bytes(source_bytes)
    return target


def _number(settings: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    value = settings.get(key, default)
    if not isinstance(value, (int, float)) or not low <= float(value) <= high:
        raise AudioEffectError(f"{key} must be between {low} and {high}")
    return float(value)


def _integer(settings: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = settings.get(key, default)
    if not isinstance(value, int) or not low <= value <= high:
        raise AudioEffectError(f"{key} must be between {low} and {high}")
    return value


def build_workflow(*, operation: str, settings: dict[str, Any], comfy_input_name: str, filename_prefix: str) -> dict[str, Any]:
    path = OPERATION_WORKFLOWS.get(operation)
    if path is None:
        raise AudioEffectError(f"Unknown audio effect operation: {operation}")
    workflow = json.loads(path.read_text(encoding="utf-8"))
    workflow["1"]["inputs"]["audio"] = comfy_input_name
    save_id = {"noise_cleanup": "3", "voice_repair": "3", "voice_changer": "5", "rvc": "6", "emotion": "4", "style": "4"}[operation]
    workflow[save_id]["inputs"]["filename_prefix"] = filename_prefix
    if operation == "noise_cleanup":
        models = {"UVR/UVR-DeNoise.pth", "UVR/UVR-DeEcho-DeReverb.pth", "MELBAND/denoise_mel_band_roformer_sdr_27.99.ckpt", "MELBAND/denoise_mel_band_roformer_aggressive_sdr_27.97.ckpt"}
        model = str(settings.get("model", "UVR/UVR-DeNoise.pth"))
        if model not in models:
            raise AudioEffectError("Unsupported cleanup model")
        workflow["2"]["inputs"].update({"model": model, "use_cache": bool(settings.get("use_cache", True)), "aggressiveness": _integer(settings, "aggressiveness", 10, 0, 20)})
        workflow["4"]["inputs"]["filename_prefix"] = f"{filename_prefix}_removed"
    elif operation == "voice_repair":
        modes = {0: "0 - Original (Default)", 1: "1 - With High-Freq Removal", 2: "2 - Train Mode (Seriously Degraded)"}
        mode = _integer(settings, "restoration_mode", 0, 0, 2)
        workflow["2"]["inputs"].update({"restoration_mode": modes[mode], "use_cuda": bool(settings.get("use_cuda", True))})
    elif operation == "voice_changer":
        voice_id = str(settings.get("target_voice_id", ""))
        voice = next((item for item in discover_voices() if item["id"] == voice_id and item.get("discoverable")), None)
        if voice is None:
            raise AudioEffectError("Choose a discoverable target reference voice")
        workflow["2"]["inputs"]["language"] = str(settings.get("language", "local:English"))
        workflow["3"]["inputs"]["voice_name"] = comfy_voice_key(voice)
        workflow["4"]["inputs"].update({"refinement_passes": _integer(settings, "refinement_passes", 1, 1, 5), "max_chunk_duration": _integer(settings, "max_chunk_duration", 30, 0, 300), "chunk_method": str(settings.get("chunk_method", "smart"))})
        if workflow["4"]["inputs"]["chunk_method"] not in {"smart", "fixed"}:
            raise AudioEffectError("chunk_method must be smart or fixed")
    elif operation == "rvc":
        catalog = {item["id"]: item for item in discover_rvc_models()}
        model_id = str(settings.get("model", "Sayano.pth"))
        if model_id not in catalog:
            raise AudioEffectError("Unknown local RVC model")
        available_indexes = {item["id"] for item in catalog[model_id]["indexes"]}
        index_id = str(settings.get("index_file", ""))
        if index_id and index_id not in available_indexes:
            raise AudioEffectError("Unknown or incompatible local RVC index")
        workflow["2"]["inputs"]["pitch_detection"] = str(settings.get("pitch_detection", "rmvpe"))
        workflow["3"]["inputs"].update({"pitch": _integer(settings, "pitch", 0, -14, 14), "index_ratio": _number(settings, "index_ratio", .75, 0, 1), "consonant_protection": _number(settings, "consonant_protection", .25, 0, .5), "volume_envelope": _number(settings, "volume_envelope", .25, 0, 1)})
        workflow["4"]["inputs"].update({"model": f"local:{model_id}", "index_file": f"local:{index_id}" if index_id else "", "auto_download": False})
        workflow["5"]["inputs"].update({"refinement_passes": _integer(settings, "refinement_passes", 1, 1, 5), "max_chunk_duration": _integer(settings, "max_chunk_duration", 30, 0, 300), "chunk_method": str(settings.get("chunk_method", "smart"))})
    else:
        transcript = str(settings.get("transcript", "")).strip()
        if not transcript:
            raise AudioEffectError("An exact transcript is required for emotion/style editing")
        iterations = _integer(settings, "iterations", 1, 1, 5)
        workflow["3"]["inputs"].update({"audio_text": transcript, "n_edit_iterations": iterations})
        if operation == "emotion":
            emotion = str(settings.get("emotion", "happy"))
            if emotion not in EMOTIONS:
                raise AudioEffectError("Unsupported emotion")
            workflow["3"]["inputs"]["emotion"] = emotion
        else:
            style = str(settings.get("style", "whisper"))
            if style not in STYLES:
                raise AudioEffectError("Unsupported style")
            workflow["3"]["inputs"]["style"] = style
    return workflow


def validate_duration(operation: str, source: Path) -> dict[str, Any]:
    try:
        info = sf.info(source)
    except Exception as exc:
        raise AudioEffectError(f"Could not inspect source audio: {exc}") from exc
    duration = info.frames / info.samplerate
    if operation in {"emotion", "style"} and not 0.5 <= duration <= 30:
        raise AudioEffectError("Step Audio EditX requires source audio between 0.5 and 30 seconds")
    return {"duration": round(duration, 4), "sample_rate": info.samplerate, "channels": info.channels}


def validate_live_nodes(comfy_url: str, workflow: dict[str, Any]) -> None:
    try:
        with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/object_info", timeout=30) as response:
            info = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not validate live ComfyUI effect nodes") from exc
    missing = sorted({node["class_type"] for node in workflow.values()} - set(info))
    if missing:
        raise RuntimeError(f"ComfyUI is missing required effect nodes: {', '.join(missing)}")


def extract_text(history: dict[str, Any]) -> str:
    values: list[str] = []
    for output in history.get("outputs", {}).values():
        for key in ("text", "string", "value"):
            item = output.get(key)
            if isinstance(item, list):
                values.extend(str(value) for value in item)
            elif item:
                values.append(str(item))
    return "\n".join(values)


def run_effect_job(*, project_id: str, project_dir: Path, output_root: Path, comfy_input_dir: Path, comfy_url: str, job: dict[str, Any], source: Path, update: Callable[[dict[str, Any]], None]) -> None:
    run_dir = project_dir / "audio" / "effects" / job["job_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    comfy_staged: Path | None = None
    remote_uncertain = False
    try:
        update({"status": "preparing" if job.get("prompt_id") else "running", "started_at": utc_now()})
        source_info = validate_duration(job["operation"], source)
        comfy_subdir = comfy_input_dir / "story_builder_effects"
        comfy_subdir.mkdir(parents=True, exist_ok=True)
        comfy_staged = comfy_subdir / f"{job['job_id']}{source.suffix.lower()}"
        shutil.copy2(source, comfy_staged)
        workflow = build_workflow(operation=job["operation"], settings=job["settings"], comfy_input_name=f"story_builder_effects/{comfy_staged.name}", filename_prefix=f"story_builder/{project_id}/{job['job_id']}")
        (run_dir / "request.json").write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
        (run_dir / "workflow.json").write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
        validate_live_nodes(comfy_url, workflow)
        # Production callers persist this reserved ID before entering the
        # submit helper. The helper holds the shared cross-process GPU lock.
        if job.get("prompt_id"):
            update({"status": "submitting", "prompt_id": job["prompt_id"]})
        prompt_id, history = submit_and_wait(workflow, comfy_url=comfy_url,
            timeout_seconds=3600, prompt_id=job.get("prompt_id"),
            workload_id=job.get("job_id"))
        outputs = collect_outputs(history, destination_dir=run_dir, comfy_url=comfy_url)
        audio_outputs = [item for item in outputs if item["kind"] == "audio"]
        if not audio_outputs:
            raise RuntimeError("ComfyUI completed without a saved audio output")
        primary = next((item for item in audio_outputs if "removed" not in item["filename"]), audio_outputs[0])
        export_dir = output_root / project_id / "audio"
        export_dir.mkdir(parents=True, exist_ok=True)
        export = export_dir / f"{job['job_id']}.flac"
        shutil.copy2(run_dir / primary["filename"], export)
        report = extract_text(history)
        (run_dir / "effect_info.txt").write_text(report, encoding="utf-8")
        registered = [{**item, "relative_path": str(Path("audio") / "effects" / job["job_id"] / item["filename"])} for item in outputs]
        update({"status": "completed", "completed_at": utc_now(), "prompt_id": prompt_id, "source_info": source_info, "outputs": registered, "primary_output": next(item for item in registered if item["filename"] == primary["filename"]), "export_path": str(export), "report_path": str(Path("audio") / "effects" / job["job_id"] / "effect_info.txt")})
    except Exception as exc:
        unknown = bool(getattr(exc, "remote_state_unknown", False))
        remote_uncertain = unknown
        update({"status": "recovery_required" if unknown else "failed",
                "completed_at": None if unknown else utc_now(),
                "prompt_id": getattr(exc, "prompt_id", None) or job.get("prompt_id"),
                "error": str(exc)})
    finally:
        # A submitted/ambiguous prompt may still read its input after this
        # function exits. Recovery owns cleanup once the exact prompt settles.
        if comfy_staged is not None and not remote_uncertain:
            comfy_staged.unlink(missing_ok=True)


def new_effect_job(operation: str, settings: dict[str, Any], source: Path) -> dict[str, Any]:
    if operation not in OPERATION_WORKFLOWS:
        raise AudioEffectError(f"Unknown audio effect operation: {operation}")
    return {"job_id": f"effect-{operation}-{uuid.uuid4().hex[:10]}", "operation": operation, "status": "queued", "created_at": utc_now(), "source_path": str(source), "settings": deepcopy(settings), "outputs": [], "primary_output": None, "error": None}
