"""Curated clip retrieval for Media Composer.

The first release deliberately indexes only files explicitly placed in
``video_summariser/out_videos``.  LanceDB is used when installed; the JSONL
manifest remains the portable source of truth and a small lexical scorer keeps
the API useful in development environments without optional embedding wheels.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
VIDEO_ROOT = Path(os.environ.get("VIDEO_SUMMARISER_ROOT", ROOT / "video_summariser"))
OUT_VIDEOS = VIDEO_ROOT / "out_videos"
INDEX_ROOT = VIDEO_ROOT / "index"
MANIFEST_PATH = INDEX_ROOT / "clips.jsonl"
INDEX_META_PATH = INDEX_ROOT / "manifest.json"
STYLE_PATH = INDEX_ROOT / "seo_styles.json"
SESSION_ROOT = INDEX_ROOT / "search_sessions"

WORD_RE = re.compile(r"[a-z0-9]{2,}")
STOP = {"the", "and", "with", "from", "that", "this", "into", "for", "of", "a", "an", "to", "in"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
EMBEDDING_DIM = 256


def _ensure() -> None:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)


def _tokens(text: str) -> set[str]:
    return {word for word in WORD_RE.findall((text or "").lower()) if word not in STOP}


def _vector(text: str) -> list[float]:
    """Stable local text vector; optional ML embeddings can replace this later.

    Hashing keeps the index usable in the minimal backend environment and is
    deterministic across restarts.  The record advertises the version so a
    future model migration can rebuild rather than silently mix vectors.
    """
    values = [0.0] * EMBEDDING_DIM
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        values[index] += 1.0 if digest[4] % 2 else -1.0
    norm = math.sqrt(sum(item * item for item in values)) or 1.0
    return [round(item / norm, 6) for item in values]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _score(query: set[str], text: set[str]) -> float:
    if not query or not text:
        return 0.0
    return len(query & text) / math.sqrt(len(query) * len(text))


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_for_file(path: Path) -> dict[str, Any]:
    digest = _hash(path)
    asset_id = f"curated-{digest[:12]}"
    clip_id = f"{asset_id}_clip_001"
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(path)
    return _base_record(path, asset_id, clip_id, digest)


def _base_record(path: Path, asset_id: str, clip_id: str, digest: str, **overrides: Any) -> dict[str, Any]:
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(path)
    row = {
        "clip_id": clip_id,
        "asset_id": asset_id,
        "source_video": rel,
        "scene_id": "scene_001",
        "subscene_id": "scene_001_action_01",
        "cut_id": "cut_001",
        "start_time_sec": 0.0,
        "end_time_sec": None,
        "duration_sec": None,
        "clip_path": rel,
        "thumbnail_path": None,
        "summary": path.stem.replace("_", " "),
        "action_beats": [],
        "subjects": [],
        "camera": {},
        "lighting": {},
        "reusable_properties": [],
        "replaceable_properties": [],
        "frame_cards": [],
        "transcript": "",
        "audio_events": [],
        "provenance": {"source_url": "", "notes": "curated out_videos asset", "license_status": "unknown"},
        "embedding_versions": {"text": "hash-v1", "image": ""},
        "_source_hash": digest,
    }
    row.update(overrides)
    row["embedding"] = _vector(_search_text(row))
    return row


def _metadata_records(path: Path) -> list[dict[str, Any]]:
    """Adapt existing video-summariser metadata into clip-level records."""
    candidates = list(path.parent.glob("**/metadata.json")) + list(path.parent.glob("**/video_story.json"))
    for output_root in (VIDEO_ROOT / "outputs", VIDEO_ROOT / "artifacts"):
        if output_root.exists():
            candidates.extend(output_root.glob("**/metadata.json"))
            candidates.extend(output_root.glob("**/video_story.json"))
    metadata: dict[str, Any] | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = str(payload.get("video_path") or payload.get("record_metadata", {}).get("video_path") or "")
        if source and (Path(source).resolve() == path.resolve() or Path(source).name == path.name):
            metadata = payload
            break
    if metadata is None:
        return []
    digest = _hash(path)
    asset_id = f"curated-{digest[:12]}"
    rows: list[dict[str, Any]] = []
    for index, scene in enumerate(metadata.get("scenes") or [], start=1):
        scene_id = str(scene.get("scene_id") or f"scene_{index:03d}")
        start = float(scene.get("start_time_sec") or 0.0)
        end = scene.get("end_time_sec")
        end_value = float(end) if end is not None else None
        story = scene.get("scene_story_text") or scene.get("scene_text") or scene.get("summary") or ""
        cards = scene.get("keyframe_analyses") or []
        beats = []
        subjects: list[str] = []
        camera: dict[str, Any] = {}
        lighting: dict[str, Any] = {}
        for card in cards:
            if not isinstance(card, dict):
                continue
            signals = card.get("support_signals") or {}
            text = card.get("detailed_description") or card.get("summary") or ""
            if text:
                beats.append(str(text)[:240])
            frame = card.get("frame_card") or {}
            subjects.extend(str(item) for item in frame.get("subjects", []) if item)
            camera.update(frame.get("camera") or {})
            lighting.update(frame.get("lighting") or {})
            if not story:
                story = str(text)
        clip_id = f"{asset_id}_{scene_id}_cut_001"
        rows.append(_base_record(path, asset_id, clip_id, digest,
            scene_id=scene_id, subscene_id=f"{scene_id}_action_01", cut_id="cut_001",
            start_time_sec=start, end_time_sec=end_value,
            duration_sec=round(end_value - start, 3) if end_value is not None else None,
            summary=str(story).strip() or path.stem.replace("_", " "),
            action_beats=beats[:12], subjects=sorted(set(subjects)), camera=camera,
            lighting=lighting, frame_cards=[card.get("frame_id") for card in cards if isinstance(card, dict) and card.get("frame_id")],
            analysis_path=str(next((candidate for candidate in candidates if candidate.name == "metadata.json"), "")),
        ))
    return rows


def _probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=20, check=True)
        return round(float(result.stdout.strip()), 3)
    except Exception:
        return None


def _prepare_media(row: dict[str, Any], source: Path) -> dict[str, Any]:
    """Create a small playable clip and first-frame thumbnail, best effort."""
    duration = row.get("duration_sec")
    if duration is None:
        source_duration = _probe_duration(source)
        if source_duration is not None:
            row["end_time_sec"] = source_duration
            row["duration_sec"] = source_duration - float(row.get("start_time_sec") or 0)
            duration = row["duration_sec"]
    media_root = VIDEO_ROOT / "clips" / str(row["asset_id"]) / str(row.get("analysis_id") or row.get("_source_hash", "source")[:12])
    media_root.mkdir(parents=True, exist_ok=True)
    clip = media_root / f"{row['scene_id']}_{row['cut_id']}.mp4"
    thumbnail = media_root / "thumbnails" / f"{row['scene_id']}_{row['cut_id']}.jpg"
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    start = max(0.0, float(row.get("start_time_sec") or 0.0))
    if not clip.exists():
        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(start)]
        if duration and duration > 0:
            command += ["-t", str(duration)]
        command += ["-i", str(source), "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(clip)]
        try:
            subprocess.run(command, timeout=180, check=True)
        except Exception:
            clip.unlink(missing_ok=True)
    if not thumbnail.exists():
        try:
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", str(source), "-frames:v", "1", str(thumbnail)], timeout=60, check=True)
        except Exception:
            thumbnail.unlink(missing_ok=True)
    for key, value in (("clip_path", clip), ("thumbnail_path", thumbnail)):
        if value.exists():
            row[key] = value.relative_to(ROOT).as_posix()
    return row


def _load() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def index_curated(force: bool = False) -> dict[str, Any]:
    _ensure()
    existing_rows = _load()
    existing: dict[str, list[dict[str, Any]]] = {}
    for row in existing_rows:
        existing.setdefault(str(row.get("source_video")), []).append(row)
    discovered: list[dict[str, Any]] = []
    for path in sorted(OUT_VIDEOS.rglob("*")) if OUT_VIDEOS.exists() else []:
        if not path.is_file() or path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
            continue
        try:
            rel = path.relative_to(ROOT).as_posix()
        except ValueError:
            rel = str(path)
        digest = _hash(path)
        old = existing.get(rel, [])
        if old and not force and all(item.get("_source_hash") == digest for item in old):
            discovered.extend(old)
            continue
        records = _metadata_records(path) or [_record_for_file(path)]
        for record in records:
            _prepare_media(record, path)
        discovered.extend(records)
    MANIFEST_PATH.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in discovered) + ("\n" if discovered else ""), encoding="utf-8")
    INDEX_META_PATH.write_text(json.dumps({"version": int(time.time()), "corpus": "curated_out_videos", "count": len(discovered), "embedding_version": "hash-v1"}, indent=2), encoding="utf-8")
    _ensure_lancedb(discovered)
    return {"count": len(discovered), "manifest": str(MANIFEST_PATH), "corpus": "curated_out_videos"}


def _ensure_lancedb(rows: list[dict[str, Any]]) -> None:
    """Mirror records into LanceDB when the optional dependency is available."""
    if not rows:
        # LanceDB cannot create a table from an empty schema; the JSONL manifest
        # remains a valid empty index until the user adds curated videos.
        return
    # The service must remain responsive when the optional native Lance
    # runtime is unavailable or slow to initialise.  Set this explicitly in
    # production after verifying the local wheel; JSONL + hash vectors remain
    # the rebuildable fallback.
    if os.environ.get("VIDEO_REFERENCES_USE_LANCEDB", "0") != "1":
        return
    try:
        import lancedb  # type: ignore
    except Exception:
        return
    table_dir = INDEX_ROOT / "lancedb"
    table_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(table_dir))
    payload = [{"clip_id": r["clip_id"], "text": _search_text(r), "summary": r.get("summary", ""), "vector": r.get("embedding") or _vector(_search_text(r)), "record_json": json.dumps(r, ensure_ascii=False)} for r in rows]
    if "clips" in db.table_names():
        db.drop_table("clips")
    db.create_table("clips", data=payload)


def _search_text(row: dict[str, Any]) -> str:
    return " ".join(str(x) for x in [row.get("summary", ""), row.get("transcript", ""), *(row.get("action_beats") or []), *(row.get("subjects") or []), json.dumps(row.get("camera", {})), json.dumps(row.get("lighting", {})), *(row.get("reusable_properties") or [])])


def _styles() -> list[dict[str, Any]]:
    _ensure()
    if not STYLE_PATH.is_file():
        return []
    return json.loads(STYLE_PATH.read_text(encoding="utf-8"))


def list_styles() -> list[dict[str, Any]]:
    return _styles()


def create_style(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Style name is required")
    styles = _styles()
    style = {"style_id": f"seo-{uuid.uuid4().hex[:10]}", "name": name, "terms": payload.get("terms", []), "avoid_terms": payload.get("avoid_terms", []), "weights": payload.get("weights", {}), "created_at": time.time()}
    styles.append(style)
    STYLE_PATH.write_text(json.dumps(styles, indent=2), encoding="utf-8")
    return style


def delete_style(style_id: str) -> bool:
    styles = _styles()
    filtered = [row for row in styles if row.get("style_id") != style_id]
    if len(filtered) == len(styles):
        return False
    STYLE_PATH.write_text(json.dumps(filtered, indent=2), encoding="utf-8")
    return True


def _matches_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    if not filters:
        return True
    duration = row.get("duration_sec")
    if filters.get("min_duration_sec") is not None and (duration is None or float(duration) < float(filters["min_duration_sec"])):
        return False
    if filters.get("max_duration_sec") is not None and (duration is None or float(duration) > float(filters["max_duration_sec"])):
        return False
    for key in ("subjects", "camera", "lighting", "license"):
        wanted = filters.get(key)
        if not wanted:
            continue
        haystack = json.dumps(row.get(key) if key != "license" else row.get("provenance", {}).get("license_status", "")).lower()
        values = wanted if isinstance(wanted, list) else [wanted]
        if not all(str(value).lower() in haystack for value in values):
            return False
    return True


def _apply_style_score(score: float, row: dict[str, Any], style: dict[str, Any] | None) -> float:
    if not style:
        return score
    text = _tokens(_search_text(row))
    preferred = _tokens(" ".join(style.get("terms") or []))
    avoided = _tokens(" ".join(style.get("avoid_terms") or []))
    weights = style.get("weights") or {}
    return score + 0.1 * len(preferred & text) + 0.02 * sum(float(value) for value in weights.values() if isinstance(value, (int, float))) - 0.08 * len(avoided & text)


def _diverse_select(scored: list[tuple[float, dict[str, Any]]], limit: int, sort_level: str) -> list[tuple[float, dict[str, Any]]]:
    selected: list[tuple[float, dict[str, Any]]] = []
    used_groups: set[str] = set()
    remaining = list(scored)
    while remaining and len(selected) < limit:
        best_index, best_value = 0, -10.0
        for index, (score, row) in enumerate(remaining):
            group_key = "source_video" if sort_level == "scene" else "subscene_id" if sort_level == "subscene" else "clip_id"
            group = str(row.get(group_key))
            value = score + (0.08 if group not in used_groups else 0.0)
            if value > best_value:
                best_value, best_index = value, index
        pair = remaining.pop(best_index)
        selected.append(pair)
        used_groups.add(str(pair[1].get("asset_id")))
    return selected


def search(payload: dict[str, Any]) -> dict[str, Any]:
    rows = _load()
    if not rows:
        index_curated()
        rows = _load()
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    top_n = max(1, min(int(payload.get("top_n", 5)), 50))
    excluded = set(payload.get("exclude_clip_ids") or [])
    style_id = payload.get("style_id") if payload.get("seo_enabled") else None
    style = next((s for s in _styles() if s.get("style_id") == style_id), None)
    terms = _tokens(query)
    if style:
        terms |= _tokens(" ".join(style.get("terms") or []))
    query_vector = _vector(query)
    search_mode = str(payload.get("search_mode") or "hybrid")
    if search_mode not in {"semantic", "keyword", "hybrid"}:
        raise ValueError("search_mode must be semantic, keyword, or hybrid")
    scored = []
    for row in rows:
        if row.get("clip_id") in excluded:
            continue
        if not _matches_filters(row, payload.get("filters") or {}):
            continue
        text = _tokens(_search_text(row))
        keyword_score = _score(terms, text)
        semantic_score = _cosine(query_vector, row.get("embedding") or _vector(_search_text(row)))
        score = semantic_score if search_mode == "semantic" else keyword_score if search_mode == "keyword" else 0.7 * keyword_score + 0.3 * semantic_score
        score = _apply_style_score(score, row, style)
        scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("clip_id", "")))
    sort_level = str(payload.get("sort_level") or "subscene")
    if sort_level in {"scene", "subscene"}:
        seen: set[str] = set()
        key_name = "source_video" if sort_level == "scene" else "subscene_id"
        collapsed = []
        for pair in scored:
            key = f"{pair[1].get('asset_id')}:{pair[1].get(key_name)}"
            if key in seen:
                continue
            seen.add(key)
            collapsed.append(pair)
        scored = collapsed
    scored = _diverse_select(scored, max(top_n * 4, top_n), sort_level)
    search_id = str(payload.get("search_id") or f"search-{uuid.uuid4().hex[:12]}")
    returned = [{**row, "match_score": round(max(0.0, min(1.0, score)), 4), "match_reason": "text, metadata and diversity-ranked match" if score else "metadata candidate"} for score, row in scored[:top_n]]
    state = {"search_id": search_id, "query": query, "top_n": top_n, "sort_level": sort_level, "filters": payload.get("filters") or {}, "style_id": style_id, "search_mode": search_mode, "returned": [r["clip_id"] for r in returned], "created_at": time.time()}
    (SESSION_ROOT / f"{search_id}.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {"search_id": search_id, "results": returned, "has_more": len(scored) > top_n, "next_exclude_clip_ids": state["returned"], "index_version": _index_version(), "embedding_version": "hash-v1", "search_mode": search_mode}


def next_page(search_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state_path = SESSION_ROOT / f"{search_id}.json"
    if not state_path.is_file():
        raise ValueError("search session not found")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    payload = {**payload, "query": state["query"], "sort_level": state.get("sort_level", "subscene"), "filters": state.get("filters", {}), "search_id": search_id, "style_id": state.get("style_id"), "seo_enabled": bool(state.get("style_id")), "search_mode": state.get("search_mode", "hybrid"), "exclude_clip_ids": state.get("returned", []) + list(payload.get("exclude_clip_ids") or [])}
    result = search(payload)
    state["returned"] = payload["exclude_clip_ids"] + [r["clip_id"] for r in result["results"]]
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return result


def refine(search_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state_path = SESSION_ROOT / f"{search_id}.json"
    if not state_path.is_file():
        raise ValueError("search session not found")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if payload.get("enabled") is False:
        state["style_id"] = None
    else:
        state["style_id"] = payload.get("style_id")
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return search({"query": state["query"], "top_n": payload.get("top_n", state.get("top_n", 5)), "sort_level": state.get("sort_level", "subscene"), "filters": state.get("filters", {}), "search_id": search_id, "style_id": state.get("style_id"), "seo_enabled": bool(state.get("style_id")), "exclude_clip_ids": []})


def _index_version() -> str:
    try:
        return str(json.loads(INDEX_META_PATH.read_text(encoding="utf-8")).get("version", ""))
    except Exception:
        return ""
