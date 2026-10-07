"""Managed audio library and deterministic batch utility jobs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from story_builder.services.media_jobs import gpu_workload_guard


AUDIO_EXTS = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
OPERATIONS = {"noise_cleanup", "extract_mp3", "demucs_stems"}
ROOT = Path(__file__).resolve().parent.parent
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008")


class AudioUtilityError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str, fallback: str = "collection") -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or fallback


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict[str, Any]:
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,sample_rate,channels", "-of", "json", str(path)]
    try:
        data = json.loads(subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"duration": None, "sample_rate": None, "channels": None}
    audio = next((row for row in data.get("streams", []) if row.get("codec_type") == "audio"), {})
    return {
        "duration": round(float(data.get("format", {}).get("duration", 0)), 3),
        "sample_rate": int(audio["sample_rate"]) if audio.get("sample_rate") else None,
        "channels": audio.get("channels"),
    }


def library_assets(root: Path) -> list[dict[str, Any]]:
    index = root / "index.json"
    if not index.exists():
        return []
    return json.loads(index.read_text(encoding="utf-8"))


def _write_library(root: Path, rows: list[dict[str, Any]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    temp = root / f"index.{uuid.uuid4().hex}.tmp"
    temp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    temp.replace(root / "index.json")


def import_library_asset(root: Path, *, filename: str, content: bytes, relative_path: str = "", tags: str = "", notes: str = "") -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in AUDIO_EXTS or not content:
        raise AudioUtilityError("A non-empty supported audio file is required")
    digest = hashlib.sha256(content).hexdigest()
    rows = library_assets(root)
    duplicate = next((row for row in rows if row["sha256"] == digest), None)
    if duplicate:
        return {**duplicate, "duplicate": True}
    asset_id = f"audio-{digest[:12]}"
    target_dir = root / "files" / asset_id
    target_dir.mkdir(parents=True, exist_ok=False)
    target = target_dir / Path(filename).name
    target.write_bytes(content)
    media = probe(target)
    row = {
        "asset_id": asset_id, "filename": target.name, "relative_source_path": relative_path or filename,
        "relative_path": str(target.relative_to(root)), "size": target.stat().st_size, "sha256": digest,
        "tags": [part.strip() for part in tags.split(",") if part.strip()], "notes": notes.strip(),
        "created_at": utc_now(), **media,
    }
    rows.append(row); _write_library(root, rows)
    return row


def update_library_asset(root: Path, asset_id: str, *, tags: list[str], notes: str) -> dict[str, Any]:
    rows = library_assets(root)
    row = next((item for item in rows if item["asset_id"] == asset_id), None)
    if row is None:
        raise AudioUtilityError("Curated audio asset not found")
    row["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
    row["notes"] = notes.strip(); row["updated_at"] = utc_now(); _write_library(root, rows)
    return row


def remove_library_asset(root: Path, asset_id: str) -> None:
    rows = library_assets(root)
    row = next((item for item in rows if item["asset_id"] == asset_id), None)
    if row is None:
        raise AudioUtilityError("Curated audio asset not found")
    target = (root / row["relative_path"]).resolve()
    if root.resolve() not in target.parents:
        raise AudioUtilityError("Unsafe curated audio path")
    target.unlink(missing_ok=True)
    if target.parent != root.resolve():
        target.parent.rmdir()
    _write_library(root, [item for item in rows if item["asset_id"] != asset_id])


def capabilities() -> dict[str, Any]:
    def container_running(name: str) -> bool:
        if not shutil.which("docker"):
            return False
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", name],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except (OSError, subprocess.SubprocessError):
            return False

    denoiser_ready = container_running("story-audio-denoiser")
    demucs_ready = container_running("story-audio-demucs")
    return {
        "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")),
        "docker": bool(shutil.which("docker")), "architecture": os.uname().machine,
        "operations": [
            {"id": "noise_cleanup", "status": "available" if denoiser_ready else "pinned", "runtime": "story-audio-denoiser", "reason": None if denoiser_ready else "Isolated denoiser runtime is not running"},
            {"id": "extract_mp3", "status": "available" if shutil.which("ffmpeg") else "blocked", "runtime": "ffmpeg"},
            {"id": "demucs_stems", "status": "available" if demucs_ready else "blocked", "runtime": "story-audio-demucs", "reason": None if demucs_ready else "Isolated Demucs runtime is not running"},
        ],
    }


def new_job(operation: str, settings: dict[str, Any], staged: list[dict[str, str]]) -> dict[str, Any]:
    if operation not in OPERATIONS:
        raise AudioUtilityError("Unknown audio utility operation")
    return {"job_id": f"utility-{operation}-{uuid.uuid4().hex[:10]}", "operation": operation, "status": "queued", "created_at": utc_now(), "settings": settings, "inputs": staged, "outputs": [], "items": [], "error": None}


def stage_inputs(project_dir: Path, job_id: str, files: list[tuple[str, str, bytes]], operation: str) -> list[dict[str, str]]:
    # Extraction is useful for both uploaded videos and already-audio sources
    # (the latter are commonly exported from TTS/ComfyUI).  Accept either
    # media class and let ffmpeg perform the normalization.
    allowed = (VIDEO_EXTS | AUDIO_EXTS) if operation == "extract_mp3" else AUDIO_EXTS
    destination = project_dir / "audio" / "utility_inputs" / job_id
    staged = []
    for filename, relative, content in files:
        suffix = Path(filename).suffix.lower()
        if suffix not in allowed or not content:
            raise AudioUtilityError(f"Unsupported or empty input: {filename}")
        safe_relative = Path(relative or filename)
        if safe_relative.is_absolute() or ".." in safe_relative.parts:
            raise AudioUtilityError("Input relative path is unsafe")
        target = destination / safe_relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        staged.append({"filename": filename, "relative_path": str(target.relative_to(project_dir)), "source_relative_path": str(safe_relative)})
    if not staged:
        raise AudioUtilityError("At least one input file is required")
    return staged


def _run(command: list[str], timeout: int = 3600) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Command failed")[-3000:])


def _run_gpu_command(command: list[str], timeout: int = 3600) -> None:
    """Serialize CUDA-backed audio utilities with every Story Builder GPU job.

    The denoiser and Demucs execute in separate containers, so ComfyUI's own
    queue cannot serialize them. Keep their GPU work behind the shared app
    lease and wait for visible/manual ComfyUI work to finish first.
    """
    with gpu_workload_guard(comfy_url=COMFYUI_URL):
        _run(command, timeout=timeout)


def run_job(job: dict[str, Any], *, project_dir: Path, output_root: Path, progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    job.update(status="running", started_at=utc_now()); progress(job)
    collection = safe_name(str(job["settings"].get("output_collection", job["operation"])))
    work = project_dir / "audio" / "utilities" / job["job_id"]
    results = work / collection; results.mkdir(parents=True, exist_ok=True)
    items = []
    try:
        for index, source in enumerate(job["inputs"], 1):
            path = project_dir / source["relative_path"]
            item = {"input": source, "status": "running", "outputs": []}; items.append(item); job["items"] = items; progress(job)
            try:
                if job["operation"] == "extract_mp3":
                    target = results / f"{path.stem}.mp3"
                    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-vn", "-codec:a", "libmp3lame", "-q:a", str(job["settings"].get("quality", 2)), str(target)])
                    outputs = [target]
                elif job["operation"] == "noise_cleanup":
                    target_dir = results / path.stem; target_dir.mkdir(exist_ok=True)
                    # Each item gets an isolated input directory so the enhancer cannot
                    # accidentally process siblings from a browser folder upload.
                    local_input = work / "denoiser_inputs" / f"item-{index}"
                    local_input.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, local_input / f"source{path.suffix}")
                    container_input = f"/workspace/{local_input.relative_to(ROOT)}"
                    container_output = f"/workspace/{target_dir.relative_to(ROOT)}"
                    _run_gpu_command(["docker", "exec", "story-audio-denoiser", "python", "-c", "import denoiser_runtime_compat, runpy; runpy.run_module('denoiser.enhance', run_name='__main__')", "--master64" if job["settings"].get("model", "master64") == "master64" else "--dns64", "--dry", str(job["settings"].get("dry", 0)), "--num_workers", "1", "--noisy_dir", container_input, "--out_dir", container_output])
                    outputs = sorted(target_dir.glob("*enhanced.wav"))
                else:
                    stems = int(job["settings"].get("stems", 2))
                    if stems not in {2, 4, 6}: raise AudioUtilityError("stems must be 2, 4, or 6")
                    target_dir = results / path.stem; target_dir.mkdir(exist_ok=True); temp = work / "demucs_tmp" / path.stem
                    model = "htdemucs_6s" if stems == 6 else "htdemucs"
                    command = ["docker", "exec", "story-audio-demucs", "demucs", "-n", model, "-o", f"/workspace/{temp.relative_to(ROOT)}", "--device", str(job["settings"].get("device", "cuda"))]
                    if stems == 2: command += ["--two-stems", "vocals"]
                    command += [f"/workspace/{path.relative_to(ROOT)}"]; _run_gpu_command(command)
                    track = temp / model / path.stem
                    order = ["vocals", "no_vocals"] if stems == 2 else (["vocals", "drums", "bass", "other"] if stems == 4 else ["vocals", "drums", "bass", "guitar", "piano", "other"])
                    mapping = []
                    for number, stem in enumerate(order, 1):
                        source_stem = track / f"{stem}.wav"
                        if not source_stem.exists(): continue
                        target = target_dir / f"{path.stem}_{number}.wav"; shutil.copy2(source_stem, target); mapping.append({"number": number, "stem": stem, "filename": target.name})
                    if not mapping: raise RuntimeError("Demucs did not produce expected stems")
                    (target_dir / "stem_manifest.json").write_text(json.dumps({"source": source["source_relative_path"], "model": model, "stems": mapping}, indent=2), encoding="utf-8")
                    outputs = [target_dir / row["filename"] for row in mapping]
                for output in outputs:
                    item["outputs"].append({"filename": output.name, "relative_path": str(output.relative_to(project_dir)), **probe(output)})
                item["status"] = "completed"
            except Exception as exc:
                item.update(status="failed", error=str(exc))
            job["progress"] = round(index / len(job["inputs"]) * 100); progress(job)
        job["outputs"] = [output for item in items for output in item.get("outputs", [])]
        job["status"] = "completed" if any(item["status"] == "completed" for item in items) else "failed"
        if job["status"] == "failed": job["error"] = "All batch items failed"
        export = output_root / project_dir.name / "audio" / job["job_id"]; export.parent.mkdir(parents=True, exist_ok=True)
        if results.exists(): shutil.copytree(results, export, dirs_exist_ok=True)
    except Exception as exc:
        job.update(status="failed", error=str(exc))
    job["completed_at"] = utc_now(); progress(job); return job
