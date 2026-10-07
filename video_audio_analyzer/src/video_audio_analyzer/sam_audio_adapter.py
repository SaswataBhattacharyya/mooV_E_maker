"""Lazy SAM Audio isolation lifecycle; inference is delegated to an isolated worker."""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL = "facebook/sam-audio-large-tv"


def readiness(*, endpoint: str | None = None) -> dict[str, Any]:
    checkpoint = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_PATH", "/models/sam-audio-large-tv"))
    endpoint = endpoint or os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL")
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    present = checkpoint.exists() and any(checkpoint.iterdir()) if checkpoint.is_dir() else checkpoint.is_file()
    worker_status: dict[str, Any] | None = None
    if endpoint:
        try:
            import requests
            response = requests.get(endpoint.rstrip("/") + "/health", timeout=3)
            response.raise_for_status()
            worker_status = response.json()
            present = bool(worker_status.get("checkpoint_present"))
        except Exception as exc:
            worker_status = {"ok": False, "reason": str(exc)}
    ready = bool(endpoint and worker_status and worker_status.get("ok") and present)
    return {"model": MODEL, "repository": "facebookresearch/sam-audio", "status": "ready" if ready else "gated_or_unavailable",
            "checkpoint_present": present, "authentication_configured": bool(token), "worker_configured": bool(endpoint),
            "worker": worker_status, "access_may_be_gated": True, "auto_download": False}


def isolate(*, audio_path: Path, prompt: str, start_sec: float, end_sec: float, temp_root: Path,
            provenance: dict[str, Any], endpoint: str | None = None) -> dict[str, Any]:
    """Call configured sidecar. Never saves to repertoire implicitly."""
    endpoint = endpoint or os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL")
    status = readiness(endpoint=endpoint)
    if not endpoint or status.get("status") != "ready":
        reason = "SAM Audio worker/checkpoint is not ready; gated weights are never downloaded automatically"
        return {"status": "unavailable", "readiness": status, "reason": reason}
    cleanup_expired_previews(temp_root)
    if not audio_path.is_file() or end_sec <= start_sec or not prompt.strip():
        raise ValueError("audio, prompt, and a positive timestamp interval are required")
    # The local process boundary uses a JSON request contract. The worker owns
    # model-specific inference and returns a temporary output path.
    try:
        import requests
        with audio_path.open("rb") as handle:
            response = requests.post(endpoint.rstrip("/") + "/isolate",
                files={"audio": (audio_path.name, handle, "audio/wav")},
                data={"prompt": prompt, "start_sec": str(start_sec), "end_sec": str(end_sec), "model": MODEL},
                timeout=3600)
        response.raise_for_status()
        temp_root.mkdir(parents=True, exist_ok=True)
        destination = temp_root / f"sam-{uuid.uuid4().hex}.wav"
        destination.write_bytes(response.content)
        if destination.stat().st_size < 44:
            destination.unlink(missing_ok=True)
            raise RuntimeError("SAM Audio worker returned no usable WAV output")
        import soundfile as sf
        if sf.info(str(destination)).duration <= 0:
            destination.unlink(missing_ok=True)
            raise RuntimeError("SAM Audio worker returned an invalid/empty WAV output")
        ttl_hours = max(1, int(os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_TEMP_TTL_HOURS", "24")))
        expires = datetime.fromtimestamp(destination.stat().st_mtime + ttl_hours * 3600, timezone.utc).isoformat()
        return {"status": "preview_ready", "temporary_id": destination.stem, "temporary_path": str(destination),
                "expires_at": expires, "save_to_repertoire": False,
                "model": MODEL, "prompt": prompt, "start_time_sec": start_sec, "end_time_sec": end_sec,
                "provenance": provenance}
    except Exception as exc:
        return {"status": "error", "readiness": status, "reason": str(exc)}


def save_to_repertoire(preview: dict[str, Any], repertoire_root: Path, *, director_decision: str) -> dict[str, Any]:
    if director_decision != "save_to_repertoire":
        raise PermissionError("SAM output requires an explicit director save_to_repertoire decision")
    source = Path(preview.get("temporary_path", ""))
    if preview.get("status") != "preview_ready" or not source.is_file():
        raise FileNotFoundError("temporary SAM Audio preview does not exist")
    target = repertoire_root / "audio" / "isolated" / f"{source.stem}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"status": "saved", "path": str(target), "model": preview.get("model"), "provenance": preview.get("provenance"),
            "director_decision": director_decision, "temporary_id": preview.get("temporary_id")}


def expire_preview(preview: dict[str, Any]) -> bool:
    source = Path(preview.get("temporary_path", ""))
    if source.is_file():
        source.unlink()
        return True
    return False


def cleanup_expired_previews(temp_root: Path, ttl_hours: int | None = None) -> int:
    """Prune old temporary previews on each new request; saved assets are elsewhere."""
    if not temp_root.exists():
        return 0
    hours = max(1, ttl_hours or int(os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_TEMP_TTL_HOURS", "24")))
    cutoff = time.time() - hours * 3600
    removed = 0
    for path in temp_root.glob("sam-*.wav"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed
