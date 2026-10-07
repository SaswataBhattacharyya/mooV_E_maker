"""Explicit promotion of approved run artifacts into the shared repertoire."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def promote_run(run_dir: Path, repertoire_root: Path, project_id: str = "unassigned", *, include_standard_media: bool = True, job_id: str | None = None) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    video_id = manifest["source"]["video_id"]
    copied: list[str] = []
    run_dir = run_dir.resolve()
    repertoire_root = repertoire_root.resolve()
    def canonical_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(repertoire_root).as_posix()
        except ValueError:
            return str(path.resolve())
    def resolve(value: str) -> Path:
        source = Path(value)
        if source.exists():
            return source
        # Container manifests may contain /app/runs/... while promotion runs
        # on the host. Resolve the stable run-relative suffix safely.
        marker = f"runs/{run_dir.name}/"
        text = str(source)
        if marker in text:
            candidate = run_dir / text.split(marker, 1)[1]
            if candidate.exists():
                return candidate
        candidate = run_dir / source.name
        if candidate.exists():
            return candidate
        raise FileNotFoundError(source)
    if include_standard_media:
        for scene in manifest.get("scenes", []):
            for frame in scene.get("frames", []):
                source = resolve(frame["path"])
                target = repertoire_root / "frames" / frame["frame_id"] / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(str(target))
        for kind, source_key in (("audio", "preview_mp3"), ("audio", "analysis_wav"), ("audio", "source_audio")):
            source_value = manifest.get("audio", {}).get(source_key)
            if source_value:
                try:
                    source = resolve(source_value)
                except FileNotFoundError:
                    continue
                target = repertoire_root / kind / f"{video_id}_{source.name}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(str(target))
    collected: list[dict[str, Any]] = []
    for asset in manifest.get("media_collection", {}).get("assets", []):
        value = asset.get("path")
        if not value or asset.get("status") == "error":
            continue
        try:
            source = resolve(str(value))
        except FileNotFoundError:
            continue
        category = str(asset.get("category", "audio"))
        asset_id = str(asset.get("asset_id") or source.stem)
        # Analyzer runs are mounted directly inside video_repertoire. Keep one
        # retained media copy and reference it from the library manifest.
        try:
            source.resolve().relative_to(repertoire_root)
            target = source
        except ValueError:
            target = repertoire_root / category / asset_id / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(target))
        collected.append({**asset, "path": canonical_path(target), "source_run": run_dir.name, "project_id": project_id})
    event_manifest = repertoire_root / "manifests" / "analyzer-runs" / f"{run_dir.name}.json"
    event_manifest.parent.mkdir(parents=True, exist_ok=True)
    record = {"video_id": video_id, "run_id": run_dir.name, "project_id": project_id, "job_id": job_id,
        "source_run": canonical_path(run_dir),
        "copied_assets": copied, "collected_assets": collected, "approved": True}
    event_manifest.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
