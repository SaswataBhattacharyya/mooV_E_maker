"""Run-bound multi-speaker dialogue TTS over the durable production queue."""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .media_jobs import MediaJobError, collect_outputs, release_comfyui_models_if_idle, submit_and_wait
from .minimax_h3_media import cleanup_owned_media, stage_audio_reference


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "workflows" / "api" / "audio" / "production_vibevoice_dialogue_api.json"
MODEL = "local:vibevoice-1.5B"
MODEL_FOLDER = "vibevoice/vibevoice-1.5B"
MODEL_REQUIRED_FILES = frozenset({
    f"{MODEL_FOLDER}/config.json",
    f"{MODEL_FOLDER}/preprocessor_config.json",
    f"{MODEL_FOLDER}/model.safetensors.index.json",
    f"{MODEL_FOLDER}/model-00001-of-00003.safetensors",
    f"{MODEL_FOLDER}/model-00002-of-00003.safetensors",
    f"{MODEL_FOLDER}/model-00003-of-00003.safetensors",
    f"{MODEL_FOLDER}/tokenizer.json",
})
LOGGER = logging.getLogger(__name__)


class ProductionDialogueTTSError(ValueError):
    pass


def _timecode(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def build_srt(lines: list[dict[str, Any]], speaker_map: dict[str, str]) -> str:
    """Validate and render exact supplied dialogue into ordered VibeVoice SRT."""
    if not lines or len(lines) > 100:
        raise ProductionDialogueTTSError("Dialogue needs between 1 and 100 lines.")
    result: list[str] = []
    previous_end = -1.0
    for index, line in enumerate(lines, 1):
        character_id = str(line.get("character_id") or "")
        text = line.get("text")
        start = line.get("start_seconds")
        end = line.get("end_seconds")
        if character_id not in speaker_map:
            raise ProductionDialogueTTSError("Every dialogue line must use a bound speaker.")
        if (not isinstance(text, str) or not text.strip() or len(text) > 2000
                or "\x00" in text or "\n" in text or "\r" in text):
            raise ProductionDialogueTTSError("Each dialogue line must contain 1–2,000 characters.")
        if (not isinstance(start, (int, float)) or isinstance(start, bool)
                or not isinstance(end, (int, float)) or isinstance(end, bool)
                or not math.isfinite(float(start)) or not math.isfinite(float(end))):
            raise ProductionDialogueTTSError("Dialogue line times must be finite numbers.")
        start, end = float(start), float(end)
        if start < previous_end or end <= start or end - start > 60:
            raise ProductionDialogueTTSError("Dialogue intervals must be ordered, non-overlapping and at most 60 seconds.")
        previous_end = end
        speaker_number = speaker_map[character_id]
        # The text itself is kept verbatim; only a stable engine speaker tag is
        # prefixed for VibeVoice's documented native multi-speaker format.
        result.append(f"{index}\n{_timecode(start)} --> {_timecode(end)}\nSpeaker {speaker_number}: {text}\n")
    return "\n".join(result)


def build_workflow(*, srt_content: str, voice_files: list[dict[str, str]], seed: int,
                   filename_prefix: str) -> dict[str, Any]:
    if not 2 <= len(voice_files) <= 4:
        raise ProductionDialogueTTSError("VibeVoice production dialogue requires 2–4 bound speakers.")
    if not 0 <= int(seed) <= 0xFFFFFFFF:
        raise ProductionDialogueTTSError("Dialogue seed must be an unsigned 32-bit integer.")
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    workflow["1"]["inputs"].update({"model": MODEL, "device": "cuda", "multi_speaker_mode": "Native Multi-Speaker",
        "quantize_llm_4bit": False, "attention_mode": "auto", "cfg_scale": 3.0,
        "inference_steps": 3, "use_sampling": False, "temperature": 0.95, "top_p": 0.95,
        "chunk_minutes": 0, "max_new_tokens": 0})
    workflow["3"]["inputs"].update({"srt_content": srt_content, "seed": int(seed),
        "narrator_voice": "none", "timing_mode": "smart_natural", "batch_size": 0})
    workflow["4"]["inputs"]["filename_prefix"] = filename_prefix
    workflow["2"]["inputs"]["opt_audio_input"] = ["5", 0]
    for index, voice in enumerate(voice_files, 1):
        node_id = str(4 + index)
        workflow[node_id]["inputs"]["audio"] = voice["filename"]
        if index > 1:
            workflow["1"]["inputs"][f"speaker{index}_voice"] = [node_id, 0]
    for index in range(len(voice_files) + 1, 5):
        node_id = str(4 + index)
        workflow.pop(node_id, None)
    return workflow


def validate_live_nodes(comfy_url: str, workflow: dict[str, Any]) -> None:
    from urllib.request import urlopen

    try:
        with urlopen(f"{comfy_url.rstrip('/')}/object_info", timeout=8) as response:
            info = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{comfy_url.rstrip('/')}/models/TTS", timeout=8) as response:
            model_files = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ProductionDialogueTTSError(f"Could not inspect ComfyUI for dialogue TTS: {exc}") from exc
    if not isinstance(model_files, list) or any(not isinstance(path, str) for path in model_files):
        raise ProductionDialogueTTSError("ComfyUI returned an invalid local TTS model listing; dialogue TTS is withheld.")
    missing_model_files = sorted(MODEL_REQUIRED_FILES - set(model_files))
    if missing_model_files:
        raise ProductionDialogueTTSError(
            "Local VibeVoice 1.5B model is incomplete; no prompt was submitted and no download was attempted. "
            f"Missing ComfyUI TTS files: {', '.join(missing_model_files)}")
    missing = sorted({row["class_type"] for row in workflow.values()} - set(info))
    if missing:
        raise ProductionDialogueTTSError(f"ComfyUI is missing dialogue TTS nodes: {', '.join(missing)}")
    engine = info.get("VibeVoiceEngineNode", {}).get("input", {}).get("required", {})
    model_options = engine.get("model", [[]])[0]
    device_options = engine.get("device", [[]])[0]
    modes = engine.get("multi_speaker_mode", [[]])[0]
    if MODEL not in model_options or "cuda" not in device_options or "Native Multi-Speaker" not in modes:
        raise ProductionDialogueTTSError("Installed VibeVoice does not expose the required local 1.5B CUDA multi-speaker mode.")
    for node_id, node in workflow.items():
        schema = info[node["class_type"]].get("input", {})
        available = set(schema.get("required", {})) | set(schema.get("optional", {})) | set(schema.get("hidden", {}))
        unsupported = sorted(set(node.get("inputs", {})) - available)
        if unsupported:
            raise ProductionDialogueTTSError(
                f"Workflow node {node_id} has inputs missing from the installed "
                f"{node['class_type']} schema: {', '.join(unsupported)}")


def cleanup_staging(*, owner_id: str, comfy_input_dir: Path, owner_root: Path) -> dict[str, Any]:
    return cleanup_owned_media(owner_id, comfy_input_dir=comfy_input_dir, owner_root=owner_root)


def run_job(*, project_dir: Path, output_root: Path, comfy_url: str, job: dict[str, Any],
            voice_sources: list[dict[str, Any]], comfy_input_dir: Path, owner_root: Path,
            update: Callable[[dict[str, Any]], None]) -> None:
    """Stage bound excerpts, submit their single durable prompt, and collect audio."""
    job_id = str(job["job_id"])
    owner_id = f"dialogue-{job_id}"
    job_dir = Path(project_dir) / "audio" / "production_dialogue" / job_id
    output_dir = Path(output_root) / job["project_id"] / "audio" / "dialogue" / job_id
    state = dict(job)

    def report(changes: dict[str, Any]) -> None:
        state.update(changes)
        update(changes)

    job_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    report({"status": "preparing", "stage_owner_id": owner_id})
    staged: list[dict[str, str]] = []
    try:
        for voice in voice_sources:
            result = stage_audio_reference(Path(voice["source_path"]), asset_id=voice["excerpt_asset_id"],
                owner_id=owner_id, comfy_input_dir=comfy_input_dir, owner_root=owner_root)
            staged.append({**voice, "filename": result.filename, "staged_sha256": result.sha256})
        speaker_map = {row["character_id"]: str(index) for index, row in enumerate(staged, 1)}
        srt = build_srt(job["dialogue_lines"], speaker_map)
        workflow = build_workflow(srt_content=srt, voice_files=staged, seed=job["seed"],
            filename_prefix=f"story_builder/{job['project_id']}/production_dialogue/{job_id}")
        validate_live_nodes(comfy_url, workflow)
        (job_dir / "submitted.srt").write_text(srt, encoding="utf-8")
        (job_dir / "voice_manifest.json").write_text(json.dumps([
            {key: value for key, value in row.items() if key != "source_path"} for row in staged
        ], indent=2), encoding="utf-8")
        report({"status": "submitting", "voice_references": [
            {key: row[key] for key in ("character_id", "speaker_id", "master_asset_id", "excerpt_asset_id", "excerpt_sha256", "filename", "staged_sha256")}
            for row in staged]})
        from story_builder.services.production_job_worker import ensure_prompt_watchdog
        ensure_prompt_watchdog(comfy_url=comfy_url, prompt_id=job["prompt_id"])
        _prompt_id, history = submit_and_wait(workflow, comfy_url=comfy_url,
            timeout_seconds=1800, prompt_id=job["prompt_id"])
        outputs = collect_outputs(history, destination_dir=output_dir, comfy_url=comfy_url)
        audio = next((item for item in outputs if item.get("kind") == "audio"), None)
        if audio is None:
            raise ProductionDialogueTTSError("VibeVoice completed without a collectible audio output.")
        report({"status": "completed", "outputs": outputs,
            "export_path": str(output_dir / audio["filename"]), "srt_path": str(job_dir / "submitted.srt"),
            "completed_at": datetime.now(timezone.utc).isoformat()})
    except MediaJobError as exc:
        # submit_and_wait preserves the reserved prompt ID; keep its owned
        # staging inputs for exact-ID recovery if remote state is ambiguous.
        report({"status": "recovery_required" if exc.remote_state_unknown else "failed",
            "error": str(exc), "prompt_id": job["prompt_id"]})
    except Exception as exc:
        status = "recovery_required" if state.get("status") == "submitting" else "failed"
        report({"status": status, "error": f"{type(exc).__name__}: {exc}"[:1200]})
    finally:
        if state.get("status") in {"completed", "failed", "cancelled"}:
            try:
                cleanup_staging(owner_id=owner_id, comfy_input_dir=comfy_input_dir, owner_root=owner_root)
            except Exception:
                LOGGER.warning("Could not clean settled dialogue TTS staging owner=%s", owner_id, exc_info=True)
            try:
                release = release_comfyui_models_if_idle(comfy_url=comfy_url)
                LOGGER.info("Dialogue TTS idle model release job_id=%s result=%s", job_id, release)
            except Exception:
                # Cleanup is best effort and must not rewrite a settled job.
                LOGGER.warning("Could not request idle ComfyUI model release job_id=%s", job_id, exc_info=True)
