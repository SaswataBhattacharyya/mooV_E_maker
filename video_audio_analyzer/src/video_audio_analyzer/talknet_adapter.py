"""HTTP adapter for the opt-in, isolated TalkNet active-speaker container."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


def detect_active_speakers(video_path: Path, worker_url: str) -> dict[str, Any]:
    video_path = Path(video_path)
    health = requests.get(urljoin(worker_url.rstrip("/") + "/", "health"), timeout=5)
    health.raise_for_status()
    readiness = health.json()
    if not readiness.get("ok") or not readiness.get("checkpoint_present") or not readiness.get("face_checkpoint_present"):
        return {"status": "unavailable", "backend": "TalkNet-ASD", "reason": "TalkNet worker preflight is incomplete", "preflight": readiness, "tracks": [], "scores": []}
    with video_path.open("rb") as handle:
        response = requests.post(urljoin(worker_url.rstrip("/") + "/", "api/active-speaker"),
            files={"video": (video_path.name, handle, "video/mp4")}, timeout=(10, 1200))
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.json())
        except Exception:
            detail = response.text[-4000:]
        return {"status": "error", "backend": "TalkNet-ASD", "reason": detail, "tracks": [], "scores": []}
    result = response.json()
    result["preflight"] = readiness
    return result
