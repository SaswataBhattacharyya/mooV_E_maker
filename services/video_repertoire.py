"""Managed video repertoire assets and subprocess jobs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPERTOIRE_ROOT = Path(os.environ.get("VIDEO_REPERTOIRE_ROOT", PROJECT_ROOT / "video_repertoire"))
LEGACY_VIDEO_ROOT = PROJECT_ROOT / "video_summariser" / "out_videos"
VIDEO_SUMMARISER_ROOT = PROJECT_ROOT / "video_audio_analyzer"
ANALYZER_ROOT = PROJECT_ROOT / "video_audio_analyzer"
LEGACY_ANALYZER_RUNS_ROOT = ANALYZER_ROOT / "runs"
def analyzer_runs_root() -> Path:
    return REPERTOIRE_ROOT / "analyses" / "video_audio_analyzer"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
JOB_KINDS = {"youtube", "analysis"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_layout() -> None:
    for name in ("downloads", "uploads", "analyses", "clips", "manifests", "jobs", "indexes"):
        (REPERTOIRE_ROOT / name).mkdir(parents=True, exist_ok=True)
    analyzer_runs_root().mkdir(parents=True, exist_ok=True)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_path(path: Path, *roots: Path) -> Path:
    resolved = path.resolve()
    if not any(_inside(resolved, root) for root in roots):
        raise ValueError("Path is outside an approved video repertoire root")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe_video(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,format_name:stream=codec_type,codec_name,width,height",
        "-of", "json", str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        data = json.loads(completed.stdout)
    except Exception:
        return {"duration": None, "format": None, "video_codec": None, "audio_codec": None, "width": None, "height": None}
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    format_data = data.get("format", {})
    return {
        "duration": float(format_data["duration"]) if format_data.get("duration") else None,
        "format": format_data.get("format_name"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
    }


def asset_manifest_path(asset_id: str) -> Path:
    return REPERTOIRE_ROOT / "manifests" / f"{asset_id}.json"


def register_asset(
    path: Path,
    *,
    source_mode: str,
    source_url: str = "",
    title: str = "",
    channel: str = "",
    provenance_notes: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_layout()
    path = safe_path(path, REPERTOIRE_ROOT, LEGACY_VIDEO_ROOT)
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("Unsupported or missing video file")
    digest = sha256_file(path)
    for existing in list_assets():
        if existing.get("sha256") == digest:
            return existing
    asset_id = f"video-{digest[:12]}"
    manifest = {
        "asset_id": asset_id,
        "filename": path.name,
        "path": str(path),
        "source_mode": source_mode,
        "source_url": source_url,
        "title": title or path.stem,
        "channel": channel,
        "sha256": digest,
        "size": path.stat().st_size,
        "created_at": utc_now(),
        "provenance_notes": provenance_notes,
        "media": _probe_video(path),
        "metadata": metadata or {},
        "analysis_ids": [],
    }
    _atomic_json(asset_manifest_path(asset_id), manifest)
    return manifest


def list_assets() -> list[dict[str, Any]]:
    ensure_layout()
    assets: list[dict[str, Any]] = []
    for path in (REPERTOIRE_ROOT / "manifests").glob("video-*.json"):
        try:
            asset = _read_json(path)
            media_path = Path(str(asset.get("path", "")))
            if not media_path.is_file():
                continue
            assets.append(asset)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(assets, key=lambda item: item.get("created_at", ""), reverse=True)


def list_audio_assets(category: str = "all") -> list[dict[str, Any]]:
    """List explicitly collected audio assets without exposing arbitrary files.

    The source of truth for collected clips is the promotion manifest. SAM
    isolated clips are listed from their explicit isolated-audio directory and
    adjacent provenance sidecars. Original/analysis audio is intentionally not
    included in this reusable-asset browser.
    """
    allowed = {"all", "voices", "music", "sfx", "ambience", "isolated"}
    if category not in allowed:
        raise ValueError(f"Unsupported audio category: {category}")
    ensure_layout()
    rows: dict[str, dict[str, Any]] = {}
    for manifest_path in (REPERTOIRE_ROOT / "manifests").rglob("*.json"):
        try:
            manifest = _read_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            continue
        for item in manifest.get("collected_assets", []):
            item_category = str(item.get("category", "")).lower()
            path_value = item.get("path")
            if item_category not in allowed - {"all", "isolated"} or not path_value:
                continue
            if category != "all" and item_category != category:
                continue
            try:
                path = safe_path(REPERTOIRE_ROOT / str(path_value), REPERTOIRE_ROOT)
            except ValueError:
                continue
            if not _inside(path, REPERTOIRE_ROOT):
                continue
            relative = path.relative_to(REPERTOIRE_ROOT.resolve()).as_posix()
            asset_id = str(item.get("asset_id") or path.stem)
            available = path.is_file() and not item.get("asset_deleted")
            digest = sha256_file(path) if available else None
            rows[relative] = {**item, "asset_id": asset_id, "category": item_category,
                "filename": path.name, "relative_path": relative,
                "size": path.stat().st_size if available else int(item.get("size", 0) or 0),
                "available": available, "sha256": digest,
                "source_video_id": manifest.get("video_id"),
                "project_id": item.get("project_id") or manifest.get("project_id"),
                "content_url": f"/api/video-repertoire/audio-assets/content/{relative}" if available else None}

    isolated_root = REPERTOIRE_ROOT / "audio" / "isolated"
    if category in {"all", "isolated"} and isolated_root.is_dir():
        sidecars = {path.stem: path for path in isolated_root.glob("*.json")}
        wavs = {path.stem: path for path in isolated_root.glob("*.wav")}
        for stem in sorted(set(sidecars) | set(wavs)):
            sidecar = sidecars.get(stem, isolated_root / f"{stem}.json")
            path = wavs.get(stem, isolated_root / f"{stem}.wav")
            try:
                path = safe_path(path, isolated_root)
            except ValueError:
                continue
            try:
                metadata = _read_json(sidecar) if sidecar.is_file() else {}
            except (OSError, json.JSONDecodeError):
                metadata = {}
            relative = path.relative_to(REPERTOIRE_ROOT.resolve()).as_posix()
            provenance = metadata.get("provenance", {}) if isinstance(metadata.get("provenance"), dict) else {}
            available = path.is_file() and not metadata.get("asset_deleted")
            rows[relative] = {"asset_id": path.stem, "category": "isolated", "filename": path.name,
                "relative_path": relative, "label": metadata.get("prompt") or provenance.get("event_label") or "SAM Audio isolation",
                "available": available, "sha256": sha256_file(path) if available else None,
                "size": path.stat().st_size if available else int(metadata.get("size", 0) or 0),
                "start_time_sec": provenance.get("start_time_sec"), "end_time_sec": provenance.get("end_time_sec"),
                "source_video_id": provenance.get("video_id"), "source_project_id": provenance.get("source_project_id"),
                "model": metadata.get("model"), "director_review": metadata.get("director_review"),
                "content_url": f"/api/video-repertoire/audio-assets/content/{relative}" if available else None}
    # Exact-file duplicate groups are confirmed duplicates. Same-class groups
    # are only a review aid: two different thunder events, for example, are not
    # duplicates merely because the classifier assigned the same label.
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    class_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows.values():
        project = str(row.get("project_id") or row.get("source_project_id") or row.get("source_video_id") or "unassigned")
        item_category = str(row.get("category", ""))
        label = " ".join(str(row.get("label") or "").casefold().split())
        if row.get("available") and label and item_category in {"sfx", "ambience", "music"}:
            class_groups.setdefault((project, item_category, label), []).append(row)
        if row.get("available") and row.get("sha256"):
            groups.setdefault((project, item_category, str(row["sha256"])), []).append(row)
    for (project, item_category, digest), members in groups.items():
        if len(members) < 2:
            continue
        group_id = f"exact-{hashlib.sha256(f'{project}|{item_category}|{digest}'.encode()).hexdigest()[:16]}"
        for row in members:
            row.update({"duplicate": True, "duplicate_group_id": group_id,
                        "duplicate_group_size": len(members), "duplicate_basis": "exact_file_hash",
                        "duplicate_project_id": project, "duplicate_category": item_category})
    for (project, item_category, label), members in class_groups.items():
        if len(members) < 2:
            continue
        group_id = f"class-{hashlib.sha256(f'{project}|{item_category}|{label}'.encode()).hexdigest()[:16]}"
        for row in members:
            row.update({"classification_group_id": group_id,
                        "classification_group_size": len(members),
                        "classification_group_label": label,
                        "classification_duplicate_candidate": True})
    return sorted(rows.values(), key=lambda item: (item.get("category", ""), item.get("filename", "").lower()))


def delete_audio_assets(relative_paths: list[str], *, confirmed: bool) -> dict[str, Any]:
    """Delete only explicitly collected derivatives; keep occurrence metadata."""
    if not confirmed:
        raise ValueError("Explicit confirmation is required before deleting derived audio")
    if not isinstance(relative_paths, list) or not relative_paths:
        raise ValueError("Select at least one derived audio asset")
    listed = {row["relative_path"]: row for row in list_audio_assets("all")}
    wanted = list(dict.fromkeys(str(item) for item in relative_paths))
    if len(wanted) > 500:
        raise ValueError("Delete at most 500 audio assets per request")
    allowed_rows: dict[str, dict[str, Any]] = {}
    for relative in wanted:
        row = listed.get(relative)
        if not row:
            raise ValueError(f"Not a registered derived audio asset: {relative}")
        if row.get("category") not in {"voices", "music", "sfx", "ambience", "isolated"}:
            raise ValueError("Only collected voice/music/SFX/ambience or SAM derivatives can be deleted here")
        allowed_rows[relative] = row
    removed: list[str] = []
    failures: list[dict[str, str]] = []
    reclaimed = 0
    targets = set(wanted)
    # Keep the manifest occurrence and timestamp, recording that its audio
    # derivative was deliberately removed.
    for manifest_path in (REPERTOIRE_ROOT / "manifests").rglob("*.json"):
        try:
            manifest = _read_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            continue
        changed = False
        for item in manifest.get("collected_assets", []):
            raw_path = str(item.get("path", ""))
            try:
                relative = safe_path(REPERTOIRE_ROOT / raw_path, REPERTOIRE_ROOT).relative_to(REPERTOIRE_ROOT.resolve()).as_posix()
            except (ValueError, OSError):
                continue
            if relative in targets:
                item["asset_deleted"] = True
                item["asset_deleted_at"] = utc_now()
                changed = True
        if changed:
            _atomic_json(manifest_path, manifest)
    for relative in wanted:
        row = allowed_rows[relative]
        try:
            path = safe_path(REPERTOIRE_ROOT / relative, REPERTOIRE_ROOT)
            if row.get("category") == "isolated":
                allowed_root = REPERTOIRE_ROOT / "audio" / "isolated"
                path = safe_path(path, allowed_root)
                sidecar = path.with_suffix(".json")
                if sidecar.is_file():
                    data = _read_json(sidecar)
                    data["asset_deleted"] = True
                    data["asset_deleted_at"] = utc_now()
                    _atomic_json(sidecar, data)
            else:
                # Prove the target is referenced by a collected-assets entry.
                if not any(relative == str(row.get("relative_path")) for row in listed.values()):
                    raise ValueError("Asset provenance check failed")
            if path.is_file():
                reclaimed += path.stat().st_size
                path.unlink()
            removed.append(relative)
        except (OSError, ValueError) as exc:
            failures.append({"relative_path": relative, "error": str(exc)})
    return {"deleted": removed, "failures": failures, "reclaimed_bytes": reclaimed,
            "occurrence_metadata_preserved": True, "source_media_preserved": True}


def get_asset(asset_id: str) -> dict[str, Any]:
    path = asset_manifest_path(asset_id)
    if not path.exists():
        raise FileNotFoundError(asset_id)
    return _read_json(path)


def delete_assets(asset_ids: list[str]) -> list[str]:
    """Remove registered assets and generated analysis media.

    Curated legacy source videos are preserved; uploaded/downloaded source files
    are removed with their registration. Analysis jobs and generated clips are
    removed when they reference one of the deleted assets.
    """
    ensure_layout()
    wanted = {str(item) for item in asset_ids if str(item).strip()}
    deleted: list[str] = []
    for asset_id in wanted:
        manifest_path = asset_manifest_path(asset_id)
        if not manifest_path.exists():
            continue
        try:
            asset = _read_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            asset = {}
        source = Path(str(asset.get("path", ""))) if asset.get("path") else None
        if source and source.exists() and _inside(source, REPERTOIRE_ROOT) and not _inside(source, LEGACY_VIDEO_ROOT):
            source.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        deleted.append(asset_id)
    for job in list_jobs("analysis"):
        requested = set((job.get("request") or {}).get("asset_ids") or [])
        if requested.intersection(wanted):
            shutil.rmtree(job_path("analysis", job["job_id"]).parent, ignore_errors=True)
    for root_name in ("analyses", "clips"):
        root = REPERTOIRE_ROOT / root_name
        if root.exists():
            for child in list(root.iterdir()):
                if child.name in wanted or any(asset_id in child.name for asset_id in wanted):
                    if child.is_dir(): shutil.rmtree(child, ignore_errors=True)
                    else: child.unlink(missing_ok=True)
    return deleted


def import_legacy_assets() -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    if not LEGACY_VIDEO_ROOT.exists():
        return imported
    for path in sorted(LEGACY_VIDEO_ROOT.iterdir()):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            imported.append(register_asset(path, source_mode="legacy", provenance_notes="Imported from video_summariser/out_videos"))
    return imported


def create_uploaded_asset(filename: str, content: bytes, provenance_notes: str = "") -> dict[str, Any]:
    ensure_layout()
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise ValueError("Upload must be a supported video file")
    safe_name = f"{uuid.uuid4().hex[:12]}_{Path(filename).name}"
    path = REPERTOIRE_ROOT / "uploads" / safe_name
    path.write_bytes(content)
    try:
        return register_asset(path, source_mode="upload", provenance_notes=provenance_notes)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def job_path(kind: str, job_id: str) -> Path:
    if kind not in JOB_KINDS:
        raise ValueError("Unknown video job kind")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
        raise ValueError("Invalid job ID")
    root = REPERTOIRE_ROOT / "jobs" / kind
    result = (root / job_id / "job.json").resolve()
    if not _inside(result, root):
        raise ValueError("Job path is outside its managed directory")
    return result


def create_job(kind: str, request: dict[str, Any]) -> dict[str, Any]:
    ensure_layout()
    if kind not in JOB_KINDS:
        raise ValueError("Unknown video job kind")
    job_id = f"{kind}-{uuid.uuid4().hex[:12]}"
    job = {
        "job_id": job_id,
        "kind": kind,
        "status": "queued",
        "progress": 0,
        "stage": "queued",
        "message": "Job is queued.",
        "request": request,
        "events": [],
        "result": None,
        "error": None,
        "pid": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    _atomic_json(job_path(kind, job_id), job)
    return job


def read_job(kind: str, job_id: str) -> dict[str, Any]:
    path = job_path(kind, job_id)
    if not path.exists():
        raise FileNotFoundError(job_id)
    job = _read_json(path)
    if job.get("status") == "running" and job.get("pid") and not _pid_alive(int(job["pid"])):
        job.update(status="interrupted", stage="interrupted", message="Worker stopped before reporting completion.", updated_at=utc_now())
        _atomic_json(path, job)
    return job


def list_jobs(kind: str) -> list[dict[str, Any]]:
    ensure_layout()
    root = REPERTOIRE_ROOT / "jobs" / kind
    if not root.exists():
        return []
    jobs = []
    for path in root.glob("*/job.json"):
        try:
            jobs.append(read_job(kind, path.parent.name))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return sorted(jobs, key=lambda item: item.get("created_at", ""), reverse=True)


def _pid_alive(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if stat.is_file():
        try:
            state = stat.read_text(encoding="ascii").rsplit(")", 1)[1].strip().split()[0]
            if state == "Z":
                return False
        except (OSError, IndexError):
            pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _owned_worker_process(pid: int, kind: str, job_id: str) -> bool:
    """Verify the persisted PID is this job's session-leading worker before signaling it."""
    try:
        if os.getpgid(pid) != pid:
            return False
        args = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", errors="replace").split("\0")
        if args and args[-1] == "":
            args.pop()
        return (len(args) >= 5 and args[1] == "-m"
            and args[2] == "story_builder.services.video_repertoire_worker"
            and args[3] == kind and args[4] == job_id)
    except (OSError, ProcessLookupError, IndexError):
        return False


def start_job(kind: str, job_id: str) -> dict[str, Any]:
    job = read_job(kind, job_id)
    if job["status"] not in {"queued", "failed", "interrupted", "cancelled"}:
        raise ValueError("Job cannot be started from its current state")
    if kind == "analysis" and any(item["status"] in {"queued", "running"} and item["job_id"] != job_id for item in list_jobs("analysis")):
        raise ValueError("Another video analysis job is already active")
    python = os.environ.get("VIDEO_SUMMARIZER_PYTHON", sys.executable)
    command = [python, "-m", "story_builder.services.video_repertoire_worker", kind, job_id]
    env = os.environ.copy()
    package_parent = str(PROJECT_ROOT.parent)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_parent, str(VIDEO_SUMMARISER_ROOT / "src"), env.get("PYTHONPATH", "")]))
    log_path = job_path(kind, job_id).parent / "worker.log"
    log_handle = log_path.open("ab")
    process = subprocess.Popen(command, cwd=str(PROJECT_ROOT.parent), env=env, stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True)
    log_handle.close()
    job.update(status="running", stage="starting", message="Worker started.", pid=process.pid, progress=1, updated_at=utc_now())
    _atomic_json(job_path(kind, job_id), job)
    return job


def cancel_job(kind: str, job_id: str) -> dict[str, Any]:
    job = read_job(kind, job_id)
    pid = job.get("pid")
    status = job.get("status")
    if status == "queued":
        job.update(status="cancelled", stage="cancelled", message="Queued job cancelled before worker startup.", updated_at=utc_now())
        _atomic_json(job_path(kind, job_id), job)
        return job
    if status not in {"running", "cancel_requested"}:
        raise ValueError("Only queued or running jobs can be cancelled")

    job.update(status="cancel_requested", stage="cancelling", message="Stopping owned analyzer work and waiting for process exit.", updated_at=utc_now())
    _atomic_json(job_path(kind, job_id), job)
    if kind == "analysis" and _uses_direct_gpu_analyzer(job):
        _stop_analysis_job_containers(job_id)

    if pid and _pid_alive(int(pid)):
        if not _owned_worker_process(int(pid), kind, job_id):
            raise RuntimeError(f"Worker process ownership could not be verified for {job_id}; no process signal was sent and cancellation remains pending.")
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        if not _wait_for_process_exit(int(pid), 12.0):
            try:
                os.killpg(int(pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            if not _wait_for_process_exit(int(pid), 5.0):
                raise RuntimeError("Analysis worker did not exit after TERM/KILL; cancellation remains pending and GPU ownership is uncertain.")

    # A worker can cross a stage boundary just after the first Docker scan.
    # Once its process is gone, scan again so a container launched in that
    # window cannot outlive a job reported as cancelled.
    if kind == "analysis" and _uses_direct_gpu_analyzer(job):
        _stop_analysis_job_containers(job_id)

    current = _read_json(job_path(kind, job_id))
    if current.get("status") in {"completed", "failed"}:
        return current
    job = current
    job.update(status="cancelled", stage="cancelled", message="Owned analyzer containers and worker process have exited.", updated_at=utc_now())
    _atomic_json(job_path(kind, job_id), job)
    return job


def _uses_direct_gpu_analyzer(job: dict[str, Any]) -> bool:
    settings = (job.get("request") or {}).get("settings", {})
    configured = settings.get("analysis_backend") if isinstance(settings, dict) else None
    return str(configured or os.environ.get("VIDEO_REPERTOIRE_ANALYSIS_BACKEND", "video_audio_analyzer")) == "video_audio_analyzer"


def _stop_analysis_job_containers(job_id: str) -> list[str]:
    """Stop only Docker containers explicitly labelled with this analysis job ID."""
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker is unavailable; cannot verify or stop containers owned by this analysis job.")
    label = f"story-builder.analysis-job={job_id}"

    def list_owned() -> list[str]:
        try:
            result = subprocess.run([docker, "ps", "--no-trunc", "-q", "--filter", f"label={label}"],
                capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Could not inspect Docker containers for analysis job {job_id}: {type(exc).__name__}: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError(f"Could not inspect Docker containers for analysis job {job_id}: {result.stderr[-1000:]}")
        ids = [value.strip() for value in result.stdout.splitlines() if value.strip()]
        if any(not re.fullmatch(r"[0-9a-fA-F]{12,64}", value) for value in ids):
            raise RuntimeError(f"Docker returned an invalid container ID for analysis job {job_id}.")
        return ids

    owned_ids = list_owned()
    if not owned_ids:
        return []
    try:
        stopped = subprocess.run([docker, "stop", "--time", "10", *owned_ids],
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Could not stop Docker containers for analysis job {job_id}: {type(exc).__name__}: {exc}") from exc
    remaining = list_owned()
    if remaining:
        raise RuntimeError(f"Docker did not stop all containers owned by analysis job {job_id}: {', '.join(remaining)}")
    if stopped.returncode != 0 and stopped.stdout.strip() == "":
        raise RuntimeError(f"Docker stop failed for analysis job {job_id}: {stopped.stderr[-1000:]}")
    return owned_ids


def _wait_for_process_exit(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)
    return not _pid_alive(pid)


def _remove_analysis_job_outputs(job: dict[str, Any]) -> None:
    """Remove this job's private outputs; preserve sources/shared repertoire media."""
    job_id = str(job.get("job_id", ""))
    job_dir = job_path("analysis", job_id).parent
    # Legacy scene analysis outputs are per-job.
    analysis_output = safe_path(REPERTOIRE_ROOT / "analyses" / job_id, REPERTOIRE_ROOT)
    if analysis_output.is_dir():
        shutil.rmtree(analysis_output)

    # Scene clips carry the owning job ID in their generated filename. Never
    # remove an asset directory or its source video as part of job cleanup.
    clips_root = REPERTOIRE_ROOT / "clips"
    for clip in clips_root.glob(f"*/{job_id}_*.mp4") if clips_root.exists() else ():
        clip = safe_path(clip, clips_root)
        if clip.is_file():
            clip.unlink()

    # Analyzer runs are shared/reusable. Delete one only when its promotion
    # manifest explicitly proves this job owns it; old or untagged runs stay.
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    audio_runs = result.get("audio_analysis", []) if isinstance(result, dict) else []
    owned_run_ids: set[str] = set()
    for item in audio_runs if isinstance(audio_runs, list) else []:
        run_id = str(item.get("run_id", "")) if isinstance(item, dict) else ""
        if not run_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", run_id):
            continue
        owned_run_ids.add(run_id)
    # Also capture a run interrupted before the analyzer returned its manifest
    # to the parent worker. Ownership is written by the analyzer at run start.
    runs_root = analyzer_runs_root()
    if runs_root.is_dir():
        for owner_file in runs_root.glob("*/job_owner.json"):
            try:
                owner = _read_json(owner_file)
            except (OSError, json.JSONDecodeError):
                continue
            if owner.get("job_id") == job_id:
                owned_run_ids.add(owner_file.parent.name)
    for run_id in owned_run_ids:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", run_id):
            continue
        promotion_manifest = REPERTOIRE_ROOT / "manifests" / "analyzer-runs" / f"{run_id}.json"
        try:
            promotion = _read_json(promotion_manifest)
        except (OSError, json.JSONDecodeError):
            promotion = {}
        owner_file = analyzer_runs_root() / run_id / "job_owner.json"
        try:
            owner = _read_json(owner_file)
        except (OSError, json.JSONDecodeError):
            owner = {}
        if promotion.get("job_id") != job_id and owner.get("job_id") != job_id:
            continue
        run_dir = safe_path(analyzer_runs_root() / run_id, analyzer_runs_root())
        if run_dir.is_dir():
            shutil.rmtree(run_dir)
        promotion_manifest.unlink(missing_ok=True)

    # Remove this ID from the source asset's bookkeeping, but do not delete
    # explicitly promoted media: it is a reusable, potentially shared asset.
    for asset_id in (job.get("request") or {}).get("asset_ids", []):
        try:
            manifest_path = asset_manifest_path(str(asset_id))
            asset = _read_json(manifest_path)
        except (OSError, json.JSONDecodeError):
            continue
        asset["analysis_ids"] = [value for value in asset.get("analysis_ids", []) if value != job_id]
        _atomic_json(manifest_path, asset)

    # Logs, copied inputs, and job state are the final thing removed, after the
    # worker is known to have exited.
    safe_job_dir = safe_path(job_dir, REPERTOIRE_ROOT / "jobs" / "analysis")
    if safe_job_dir.is_dir():
        shutil.rmtree(safe_job_dir)


def stop_and_delete_analysis_job(job_id: str) -> dict[str, Any]:
    """Stop an analysis worker, wait for it to exit, then delete its private data."""
    job = read_job("analysis", job_id)
    pid_value = job.get("pid")
    if pid_value and _pid_alive(int(pid_value)):
        pid = int(pid_value)
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        if not _wait_for_process_exit(pid, 12.0):
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if not _wait_for_process_exit(pid, 5.0):
                raise RuntimeError("Analysis worker did not exit; its files were left intact for safety.")
    try:
        _remove_analysis_job_outputs(job)
    except PermissionError as exc:
        blocked_path = exc.filename or "an analyzer output"
        raise RuntimeError(
            f"Could not delete analyzer output at {blocked_path}: permission denied. "
            "The output was left in place. Run analyzer containers with the host UID/GID "
            "or fix ownership of this job's generated files, then retry."
        ) from exc
    return {"job_id": job_id, "status": "stopped", "deleted": True}


def delete_analysis_job(job_id: str) -> dict[str, Any]:
    """Delete an analysis job; an active worker is stopped before cleanup."""
    return stop_and_delete_analysis_job(job_id)


def capabilities(ollama_host: str) -> dict[str, Any]:
    ensure_layout()
    ollama_online = False
    models: list[str] = []
    try:
        with urlopen(f"{ollama_host.rstrip('/')}/api/tags", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            models = [item.get("name", "") for item in payload.get("models", [])]
            ollama_online = True
    except (URLError, OSError, json.JSONDecodeError):
        pass
    analyzer_root = PROJECT_ROOT / "video_audio_analyzer"
    intern_model = analyzer_root / "models" / "internvideo3-8b-instruct"
    peav_model = analyzer_root / "models" / "pe-av-base"
    analyzer_models_ready = all((intern_model / name).is_file() for name in ("config.json", "model.safetensors.index.json")) and all(
        (peav_model / name).is_file() for name in ("config.json", "model.safetensors"))
    peav_query_worker_online = False
    try:
        query_worker = os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL", "http://127.0.0.1:8034").rstrip("/")
        with urlopen(f"{query_worker}/health", timeout=1.5) as response:
            query_status = json.loads(response.read().decode("utf-8"))
            peav_query_worker_online = bool(query_status.get("ok") and query_status.get("model") == "facebook/pe-av-base")
    except (URLError, OSError, json.JSONDecodeError, TimeoutError):
        pass
    analyzer_image_ready = False
    analyzer_audio_image_ready = False
    if shutil.which("docker"):
        try:
            probe = subprocess.run(["docker", "image", "inspect", "video-audio-analyzer-internvideo3:dev"],
                capture_output=True, timeout=4, check=False)
            analyzer_image_ready = probe.returncode == 0
            audio_probe = subprocess.run(["docker", "image", "inspect", "video-audio-analyzer-peav:dev"],
                capture_output=True, timeout=4, check=False)
            analyzer_audio_image_ready = audio_probe.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {
        "repertoire_root": str(REPERTOIRE_ROOT),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "yt_dlp": bool(shutil.which("yt-dlp") or shutil.which("yt-dlp_linux")),
        "ollama_online": ollama_online,
        "ollama_models": models,
        "video_audio_analyzer_ready": bool(shutil.which("docker") and analyzer_models_ready and analyzer_image_ready and analyzer_audio_image_ready),
        "video_audio_analyzer_models_ready": analyzer_models_ready,
        "video_audio_analyzer_image_ready": analyzer_image_ready,
        "video_audio_analyzer_audio_image_ready": analyzer_audio_image_ready,
        "pe_av_query_worker_online": peav_query_worker_online,
        "analysis_model": os.environ.get("VIDEO_SUMMARIZER_ANALYSIS_MODEL", "qwen3.6:35b"),
        "legacy_video_root": str(LEGACY_VIDEO_ROOT),
        "legacy_video_count": len([path for path in LEGACY_VIDEO_ROOT.glob("*") if path.suffix.lower() in VIDEO_EXTENSIONS]) if LEGACY_VIDEO_ROOT.exists() else 0,
        "active_analysis_job": next((item["job_id"] for item in list_jobs("analysis") if item["status"] in {"queued", "running"}), None),
    }


def resolve_youtube_sources(*, mode: str, query: str = "", count: int = 5, urls_text: str = "") -> dict[str, Any]:
    if mode not in {"search", "paste", "file"}:
        raise ValueError("Source mode must be search, paste, or file")
    candidates: list[dict[str, Any]] = []
    if mode == "search":
        if not query.strip():
            raise ValueError("Search query is required")
        count = max(1, min(int(count), 25))
        executable = shutil.which("yt-dlp") or shutil.which("yt-dlp_linux")
        if not executable:
            raise RuntimeError("yt-dlp is not installed")
        completed = subprocess.run(
            [executable, "--flat-playlist", "--dump-single-json", f"ytsearch{count}:{query.strip()}"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        payload = json.loads(completed.stdout)
        for entry in payload.get("entries", []):
            video_id = str(entry.get("id", ""))
            url = entry.get("webpage_url") or entry.get("url")
            if url and not str(url).startswith("http") and video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
            if video_id and (not url or "youtube.com" not in str(url)):
                url = f"https://www.youtube.com/watch?v={video_id}"
            if url:
                candidates.append({"url": str(url), "video_id": video_id, "title": entry.get("title") or video_id, "channel": entry.get("channel") or entry.get("uploader") or ""})
    else:
        for raw in urls_text.splitlines():
            url = raw.strip()
            if not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid URL: {url}")
            candidates.append({"url": url, "video_id": "", "title": url, "channel": ""})
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        if item["url"] not in seen:
            seen.add(item["url"])
            deduplicated.append(item)
    return {"source_mode": mode, "query": query, "candidates": deduplicated}


def search_records(query: str) -> list[dict[str, Any]]:
    terms = [term.lower() for term in query.split() if term.strip()]
    records: list[dict[str, Any]] = []
    for job in list_jobs("analysis"):
        result = job.get("result") or {}
        for video in result.get("videos", []):
            for scene in video.get("scenes", []):
                haystack = " ".join([
                    video.get("title", ""), scene.get("scene_id", ""), scene.get("summary", ""),
                    scene.get("transcript", ""), " ".join(scene.get("keywords", [])),
                ]).lower()
                if not terms or all(term in haystack for term in terms):
                    records.append({
                        "job_id": job["job_id"], "asset_id": video.get("asset_id"), "title": video.get("title"),
                        "scene_id": scene.get("scene_id"), "start_time_sec": scene.get("start_time_sec"),
                        "end_time_sec": scene.get("end_time_sec"), "summary": scene.get("summary"),
                        "keywords": scene.get("keywords", []), "clip_path": scene.get("clip_path"),
                    })
    return records[:100]


def safe_artifact_path(kind: str, job_id: str, relative_path: str) -> Path:
    root_name = "analyses" if kind == "analysis" else "downloads"
    root = REPERTOIRE_ROOT / root_name
    candidate = safe_path(root / relative_path, root)
    if not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate
