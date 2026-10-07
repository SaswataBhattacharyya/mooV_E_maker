"""Persistent, cancellable visual-analysis runs for Story Builder."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .image_detailer import analyze_image
from .vision_contracts import AnalysisRun, VisualEvidencePacket, generation_brief

ROOT = Path(__file__).resolve().parent.parent / "storage" / "vision_runs"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_dir(run_id: str) -> Path:
    return ROOT / run_id


def _write(run_id: str, payload: dict[str, Any]) -> None:
    target = run_dir(run_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "run.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "run.json"
    if not path.is_file():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def create(source: bytes, filename: str, mode: str, project_id: str | None = None) -> dict[str, Any]:
    run_id = f"vision-{uuid.uuid4().hex[:12]}"
    target = run_dir(run_id)
    target.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename or "image.png").suffix.lower() or ".png"
    input_path = target / f"input{suffix}"
    input_path.write_bytes(source)
    record = AnalysisRun(run_id=run_id, input_sha256=hashlib.sha256(source).hexdigest(), source_type="image", model=os.environ.get("OLLAMA_VISION_MODEL", "qwen3.6:35b"), mode=mode, created_at=now(), updated_at=now()).model_dump()
    record.update({"input_path": str(input_path), "project_id": project_id, "events": []})
    _write(run_id, record)
    return record


def _event(run_id: str, stage: str, progress: int, message: str) -> None:
    record = read(run_id)
    record.update(stage=stage, progress=progress, message=message, updated_at=now())
    record.setdefault("events", []).append({"stage": stage, "progress": progress, "message": message, "timestamp": now()})
    record["events"] = record["events"][-100:]
    _write(run_id, record)


def execute(run_id: str) -> None:
    record = read(run_id)
    if record.get("status") == "cancelled":
        return
    try:
        record.update(status="running", updated_at=now())
        _write(run_id, record)
        _event(run_id, "preprocess", 10, "Validating image and preparing evidence")
        _event(run_id, "specialists", 30, "Collecting optional computer-vision evidence")
        _event(run_id, "qwen", 55, "Running structured Qwen visual analysis")
        result = analyze_image(Path(record["input_path"]), mode=record["mode"], model=record["model"])
        _event(run_id, "fusion", 78, "Fusing specialist evidence and uncertainty")
        packet = VisualEvidencePacket(run_id=run_id, input=result["input"], analysis=result["analysis"], frame_card=result["frame_card"], specialist_evidence=result.get("specialist_evidence", {}), uncertainties=result["analysis"].get("uncertainties", []), provenance={"model": result.get("model"), "mode": result.get("mode")}).model_dump()
        target = run_dir(run_id)
        (target / "evidence.json").write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
        (target / "generation_brief.json").write_text(json.dumps(generation_brief(packet, run_id), indent=2, ensure_ascii=False), encoding="utf-8")
        (target / "report.md").write_text(f"# Visual analysis {run_id}\n\n{packet['frame_card'].get('summary', '')}\n", encoding="utf-8")
        (target / "manifest.json").write_text(json.dumps({"run_id": run_id, "artifacts": ["input", "evidence.json", "generation_brief.json", "report.md"]}, indent=2), encoding="utf-8")
        record.update(status="completed", stage="export", progress=100, result=packet, updated_at=now(), error=None)
        _write(run_id, record)
    except Exception as exc:
        record.update(status="failed", stage="failed", progress=100, error=str(exc), updated_at=now())
        _write(run_id, record)


def cancel(run_id: str) -> dict[str, Any]:
    record = read(run_id)
    record.update(status="cancelled", stage="cancelled", message="Cancelled by user", updated_at=now())
    _write(run_id, record)
    return record


def artifact(run_id: str, relative: str) -> Path:
    root = run_dir(run_id).resolve()
    target = (root / relative).resolve()
    if root not in target.parents and target != root:
        raise ValueError("Invalid artifact path")
    if not target.is_file():
        raise FileNotFoundError(relative)
    return target
