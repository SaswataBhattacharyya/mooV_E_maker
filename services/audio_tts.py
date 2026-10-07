"""Prepared Phase 2 timed multi-character TTS execution."""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .media_jobs import MediaJobError, collect_outputs, submit_and_wait


WORKFLOW_PATH = Path(__file__).resolve().parent.parent / "workflows" / "api" / "audio" / "tts_multichar_timed_chatterbox_api.json"
TIMING_MODES = {"stretch_to_fit", "pad_with_silence", "smart_natural", "concatenate"}
LANGUAGES = {
    "en": "English", "english": "English", "de": "German", "german": "German",
    "fr": "French", "french": "French", "no": "Norwegian", "norwegian": "Norwegian",
    "ru": "Russian", "russian": "Russian", "hy": "Armenian", "armenian": "Armenian",
    "ka": "Georgian", "georgian": "Georgian", "ja": "Japanese", "japanese": "Japanese",
    "ko": "Korean", "korean": "Korean", "it": "Italian", "italian": "Italian",
}
TAG_RE = re.compile(r"\[\s*(?:(?P<language>[^:\]\n]+)\s*:\s*)?(?P<character>[^\]\n]+)\s*\]")
SRT_TIME_RE = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
GPU_LOCK = threading.Lock()


class TimedTTSError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def comfy_voice_key(voice: dict[str, Any]) -> str:
    relative = str(voice["relative_path"]).replace("\\", "/").strip("/")
    if voice["source"] == "bundled":
        return f"voices_examples/{relative}"
    if voice["source"] == "tts-user":
        return f"TTS/voices/{relative}"
    if voice["source"] == "user":
        return relative
    raise TimedTTSError(f"Unsupported reference voice source: {voice['source']}")


def voice_character_name(voice: dict[str, Any]) -> str:
    return Path(str(voice["relative_path"])).stem


def validate_srt(value: str) -> str:
    content = value.strip()
    if not content:
        raise TimedTTSError("SRT content cannot be empty")
    if not SRT_TIME_RE.search(content):
        raise TimedTTSError("SRT content must contain at least one valid timestamp range")
    return content + "\n"


def prepare_srt(srt_content: str, characters: list[dict[str, Any]], voices: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    original = validate_srt(srt_content)
    voice_by_id = {voice["id"]: voice for voice in voices if voice.get("discoverable")}
    char_by_name = {item["name"].strip().casefold(): item for item in characters}
    if not char_by_name:
        raise TimedTTSError("Save at least one project character before generating timed TTS")

    resolved: dict[str, dict[str, str]] = {}
    for normalized, character in char_by_name.items():
        voice = voice_by_id.get(character["reference_voice_id"])
        if voice is None:
            raise TimedTTSError(f"Unknown or unusable reference voice for {character['name']}")
        language_key = str(character.get("language") or "en").strip().casefold()
        language = LANGUAGES.get(language_key)
        if language is None:
            raise TimedTTSError(f"Unsupported ChatterBox language for {character['name']}: {character.get('language')}")
        resolved[normalized] = {
            "name": character["name"].strip(),
            "language": language,
            "voice_id": voice["id"],
            "voice_key": comfy_voice_key(voice),
            "voice_character": voice_character_name(voice),
        }

    used: set[str] = set()
    def replace(match: re.Match[str]) -> str:
        requested = match.group("character").strip()
        item = resolved.get(requested.casefold())
        if item is None:
            raise TimedTTSError(f"SRT character is missing from the project character map: {requested}")
        explicit = (match.group("language") or "").strip()
        if explicit:
            language = LANGUAGES.get(explicit.casefold())
            if language is None:
                raise TimedTTSError(f"Unsupported explicit ChatterBox language: {explicit}")
        else:
            language = item["language"]
        used.add(requested.casefold())
        return f"[{language}:{item['voice_character']}]"

    rewritten = TAG_RE.sub(replace, original)
    has_untagged = False
    for block in re.split(r"\n\s*\n", original):
        dialogue = "\n".join(
            line for line in block.splitlines()
            if line.strip() and not line.strip().isdigit() and "-->" not in line
        ).lstrip()
        if dialogue and TAG_RE.match(dialogue) is None:
            has_untagged = True
            break
    narrator = resolved.get("narrator")
    if has_untagged and narrator is None:
        raise TimedTTSError("Untagged SRT dialogue requires a character named Narrator")
    fallback = narrator or next(iter(resolved.values()))
    return rewritten, {"characters": list(resolved.values()), "used_characters": sorted(used), "narrator": fallback}


def build_workflow(*, rewritten_srt: str, narrator: dict[str, str], settings: dict[str, Any], filename_prefix: str) -> dict[str, Any]:
    timing_mode = settings.get("timing_mode", "smart_natural")
    if timing_mode not in TIMING_MODES:
        raise TimedTTSError(f"Unsupported timing mode: {timing_mode}")
    language = LANGUAGES.get(str(settings.get("language", "English")).casefold())
    if language is None:
        raise TimedTTSError(f"Unsupported ChatterBox base language: {settings.get('language')}")
    ranges = {
        "seed": (0, 2**32 - 1), "exaggeration": (0.25, 2.0), "temperature": (0.05, 5.0),
        "cfg_weight": (0.0, 1.0), "fade": (0.0, 0.1), "max_stretch_ratio": (0.5, 5.0),
        "min_stretch_ratio": (0.1, 2.0), "timing_tolerance": (0.5, 10.0), "batch_size": (0, 32),
    }
    defaults = {"seed": 1, "exaggeration": .5, "temperature": .8, "cfg_weight": .5, "fade": .01,
                "max_stretch_ratio": 1.0, "min_stretch_ratio": .5, "timing_tolerance": 2.0, "batch_size": 0}
    values: dict[str, Any] = {}
    for key, (low, high) in ranges.items():
        value = settings.get(key, defaults[key])
        if not isinstance(value, (int, float)) or not low <= value <= high:
            raise TimedTTSError(f"{key} must be between {low} and {high}")
        values[key] = value
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    workflow["1"]["inputs"].update({"language": language, "device": "auto", "exaggeration": values["exaggeration"], "temperature": values["temperature"], "cfg_weight": values["cfg_weight"]})
    workflow["2"]["inputs"]["voice_name"] = narrator["voice_key"]
    workflow["3"]["inputs"].update({
        "srt_content": rewritten_srt, "seed": int(values["seed"]), "timing_mode": timing_mode,
        "enable_audio_cache": bool(settings.get("enable_audio_cache", True)), "fade_for_StretchToFit": values["fade"],
        "max_stretch_ratio": values["max_stretch_ratio"], "min_stretch_ratio": values["min_stretch_ratio"],
        "timing_tolerance": values["timing_tolerance"], "batch_size": int(values["batch_size"]),
    })
    workflow["4"]["inputs"]["filename_prefix"] = filename_prefix
    return workflow


def extract_text_output(history: dict[str, Any], node_id: str) -> str:
    output = history.get("outputs", {}).get(node_id, {})
    values = output.get("text") or output.get("string") or output.get("value") or []
    if isinstance(values, list):
        return "\n".join(str(value) for value in values)
    return str(values or "")


def validate_live_nodes(comfy_url: str, workflow: dict[str, Any]) -> None:
    required = {node["class_type"] for node in workflow.values()}
    try:
        with urllib.request.urlopen(f"{comfy_url}/object_info", timeout=30) as response:
            object_info = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not validate ComfyUI node schemas at {comfy_url}") from exc
    missing = sorted(required - set(object_info))
    if missing:
        raise RuntimeError(f"ComfyUI is missing required timed TTS nodes: {', '.join(missing)}")
    language = workflow["1"]["inputs"]["language"]
    language_spec = object_info.get("ChatterBoxEngineNode", {}).get("input", {}).get("required", {}).get("language", [])
    live_languages = language_spec[0] if language_spec and isinstance(language_spec[0], list) else []
    if live_languages and language not in live_languages:
        raise RuntimeError(f"ChatterBox language is not available in the live node: {language}")


def run_timed_job(*, project_id: str, project_dir: Path, output_root: Path, job: dict[str, Any], workflow: dict[str, Any], comfy_url: str, update: Callable[[dict[str, Any]], None]) -> None:
    run_dir = project_dir / "audio" / "runs" / job["job_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        (run_dir / "original.srt").write_text(job["original_srt"], encoding="utf-8")
        (run_dir / "submitted.srt").write_text(job["rewritten_srt"], encoding="utf-8")
        (run_dir / "request.json").write_text(json.dumps(job, indent=2, ensure_ascii=True), encoding="utf-8")
        update({"status": "running", "started_at": utc_now()})
        validate_live_nodes(comfy_url, workflow)
        if job.get("prompt_id"):
            update({"status": "recovery_required", "error": "Reconcile the saved prompt before retrying."})
            return
        job["prompt_id"] = str(uuid.uuid4())
        update({"prompt_id": job["prompt_id"], "status": "submitting"})
        with GPU_LOCK:
            prompt_id, history = submit_and_wait(workflow, comfy_url=comfy_url, timeout_seconds=1800, prompt_id=job["prompt_id"])
        outputs = collect_outputs(history, destination_dir=run_dir, comfy_url=comfy_url)
        audio = next((item for item in outputs if item["kind"] == "audio"), None)
        if audio is None:
            raise RuntimeError("ComfyUI completed without a saved audio output")
        sidecars = {"generation_info.txt": extract_text_output(history, "5"), "timing_report.txt": extract_text_output(history, "6"), "adjusted.srt": extract_text_output(history, "7")}
        for name, content in sidecars.items():
            (run_dir / name).write_text(content, encoding="utf-8")
        export_dir = output_root / project_id / "audio"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"{job['job_id']}.flac"
        shutil.copy2(run_dir / audio["filename"], export_path)
        registered_outputs = [{**item, "relative_path": str(Path("audio") / "runs" / job["job_id"] / item["filename"])} for item in outputs]
        update({"status": "completed", "completed_at": utc_now(), "prompt_id": prompt_id, "outputs": registered_outputs,
                "export_path": str(export_path), "reports": {name: str(Path("audio") / "runs" / job["job_id"] / name) for name in sidecars}})
    except Exception as exc:
        update({"status": "recovery_required" if isinstance(exc, MediaJobError) and exc.remote_state_unknown else "failed", "prompt_id": job.get("prompt_id"), "completed_at": utc_now(), "error": str(exc)})


def new_job(settings: dict[str, Any], resolved: dict[str, Any], original_srt: str, rewritten_srt: str) -> dict[str, Any]:
    return {"job_id": f"tts-{uuid.uuid4().hex[:12]}", "status": "queued", "created_at": utc_now(),
            "settings": deepcopy(settings), "resolved": resolved, "original_srt": original_srt,
            "rewritten_srt": rewritten_srt, "outputs": [], "error": None}
