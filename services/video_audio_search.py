"""Safe Story Builder adapter for the isolated video/audio analyzer corpus."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from . import video_repertoire


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYZER_ROOT = PROJECT_ROOT / "video_audio_analyzer"
RUNS_ROOT = video_repertoire.analyzer_runs_root()
LEGACY_RUNS_ROOT = video_repertoire.LEGACY_ANALYZER_RUNS_ROOT


def _artifact_path(run_id: str, source_path: str) -> str | None:
    """Translate a worker/container path to a validated run-relative artifact."""
    prefix = f"/app/runs/{run_id}/"
    if not source_path.startswith(prefix):
        return None
    relative = Path(source_path[len(prefix):])
    if relative.is_absolute() or ".." in relative.parts:
        return None
    base = RUNS_ROOT if (RUNS_ROOT / run_id).is_dir() else LEGACY_RUNS_ROOT
    run_root = (base / run_id).resolve()
    candidate = (run_root / relative).resolve()
    try:
        candidate.relative_to(run_root)
    except ValueError:
        return None
    return relative.as_posix() if candidate.is_file() else None


def _asset_id(video_id: str) -> str | None:
    """Find a registered source asset by its analyzer content-hash prefix."""
    for asset in video_repertoire.list_assets():
        digest = str(asset.get("sha256") or "")
        if video_id and digest.startswith(video_id):
            return str(asset.get("asset_id"))
    return None


def search(*, query: str, top_n: int = 5, mode: str = "semantic", offset: int = 0) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("Enter a search description.")
    if mode not in {"semantic", "keyword", "hybrid"}:
        raise ValueError("Search mode must be semantic, keyword, or hybrid.")
    top_n = max(1, min(int(top_n), 50))
    offset = max(0, int(offset))
    analyzer_src = str(ANALYZER_ROOT / "src")
    if analyzer_src not in sys.path:
        sys.path.insert(0, analyzer_src)
    # Match run_api.sh defaults while keeping the model worker isolated.
    os.environ.setdefault("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL", "http://127.0.0.1:8034")
    os.environ.setdefault("VIDEO_AUDIO_ANALYZER_CORPUS_INDEX_ROOT",
        str(video_repertoire.REPERTOIRE_ROOT / "analyses" / "corpus_index_v2"))
    from video_audio_analyzer.retrieval import search_all

    roots = [RUNS_ROOT]
    if LEGACY_RUNS_ROOT.is_dir():
        roots.append(LEGACY_RUNS_ROOT)
    # Preserve access to historical, permission-locked runs while new data is
    # written only to the canonical repertoire tree.
    pages = [search_all(root, query, top_n=max(top_n + offset, 50), mode=mode, offset=0)
             for root in roots if root.is_dir()]
    combined: dict[str, Any] = {**(pages[0] if pages else {}), "results": [], "total_candidates": 0}
    seen: set[str] = set()
    for page in pages:
        combined["total_candidates"] += int(page.get("total_candidates", 0))
        for row in page.get("results", []):
            identity = str(row.get("result_id") or row.get("record_id") or "")
            if identity not in seen:
                seen.add(identity)
                combined["results"].append(row)
    combined["results"].sort(key=lambda row: (-float(row.get("score", 0)), str(row.get("run_id", "")), str(row.get("record_id", ""))))
    combined["results"] = combined["results"][offset:offset + top_n]
    combined["next_offset"] = offset + len(combined["results"]) if offset + len(combined["results"]) < combined["total_candidates"] else None
    result = combined
    safe_results = []
    manifest_cache: dict[str, dict[str, Any]] = {}
    for row in result.get("results", []):
        item = {key: value for key, value in row.items()
                if key not in {"pe_av_vector", "pe_av_text_vector", "clap_vector", "source_path", "embedding", "vector"}}
        run_id = str(row.get("run_id") or "")
        base = RUNS_ROOT if run_id and (RUNS_ROOT / run_id / "manifest.json").is_file() else LEGACY_RUNS_ROOT
        if not run_id or not (base / run_id / "manifest.json").is_file():
            continue
        if run_id not in manifest_cache:
            try:
                manifest_cache[run_id] = json.loads((base / run_id / "manifest.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest_cache[run_id] = {}
        artifact = _artifact_path(run_id, str(row.get("source_path") or ""))
        item["run_id"] = run_id
        item["artifact_path"] = artifact
        item["asset_id"] = _asset_id(str(row.get("source_video_id") or row.get("video_id") or ""))
        scene_id = str(row.get("scene_id") or "")
        scene = next((item for item in manifest_cache[run_id].get("scenes", []) if str(item.get("scene_id")) == scene_id), None)
        if scene:
            item["cuts"] = scene.get("cuts", [])
        clip_relative = f"embeddings/{scene_id}.mp4" if scene_id else ""
        if clip_relative and (RUNS_ROOT / run_id / clip_relative).is_file():
            item["clip_artifact_path"] = clip_relative
        safe_results.append(item)
    return {**result, "results": safe_results}
