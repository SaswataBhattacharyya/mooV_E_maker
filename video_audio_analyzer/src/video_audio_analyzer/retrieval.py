from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Iterable


PE_AV_MODEL = "facebook/pe-av-base"
CLAP_MODEL = "separate-fallback-space"
VECTOR_DIM = 256


def _lancedb_status() -> dict[str, Any]:
    if os.environ.get("VIDEO_AUDIO_ANALYZER_ENABLE_LANCEDB", "0").lower() not in {"1", "true", "yes"}:
        return {"status": "disabled", "reason": "VIDEO_AUDIO_ANALYZER_ENABLE_LANCEDB is not enabled"}
    probe_dir = tempfile.mkdtemp(prefix="vaa-lance-probe-")
    env = dict(os.environ)
    env["LANCE_PROBE_DIR"] = probe_dir
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "video_audio_analyzer.lancedb_probe"],
            env=env, text=True, capture_output=True, timeout=float(os.environ.get("VIDEO_AUDIO_ANALYZER_LANCEDB_TIMEOUT", "8")),
        )
        payload = json.loads(completed.stdout.strip().splitlines()[-1]) if completed.stdout.strip() else {"status": "error", "error": completed.stderr[-500:]}
        return payload
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "reason": "LanceDB initialization exceeded watchdog timeout; JSONL fallback retained"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _hash_vector(text: str, dimension: int = VECTOR_DIM) -> list[float]:
    """Deterministic offline vector used only when PE-AV is not preflight-ready."""
    values = [0.0] * dimension
    tokens = text.lower().split()
    for token in tokens or ["empty"]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for offset in range(0, len(digest), 4):
            index = int.from_bytes(digest[offset:offset + 2], "little") % dimension
            sign = 1.0 if digest[offset + 2] & 1 else -1.0
            values[index] += sign * (1.0 + digest[offset + 3] / 255.0)
    norm = math.sqrt(sum(item * item for item in values)) or 1.0
    return [round(item / norm, 7) for item in values]


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return -1.0
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left)) or 1.0
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right)) or 1.0
    return sum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)


def _model_status() -> dict[str, Any]:
    configured = os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_PATH")
    if configured:
        model_dir = Path(configured)
        if (model_dir / "config.json").exists() and (model_dir / "model.safetensors").exists():
            try:
                from .peav_adapter import PEAVAdapter
                import json as _json
                config = _json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
                dimension = int(config.get("output_dim", 1024))
                return {"backend": "pe_av", "model": PE_AV_MODEL, "status": "checkpoint_ready_lazy_adapter", "dimension": dimension, "checkpoint": str(model_dir)}
            except Exception as exc:
                return {"backend": "deterministic_fallback", "model": PE_AV_MODEL, "status": "adapter_unavailable", "dimension": VECTOR_DIM, "reason": str(exc)}
        return {"backend": "deterministic_fallback", "model": PE_AV_MODEL, "status": "configured_checkpoint_incomplete", "dimension": VECTOR_DIM, "checkpoint": str(model_dir)}
    return {"backend": "deterministic_fallback", "model": PE_AV_MODEL, "status": "unavailable_preflight_only", "dimension": VECTOR_DIM, "reason": "VIDEO_AUDIO_ANALYZER_PE_AV_PATH is not configured"}


def _records(manifest: dict[str, Any]) -> Iterable[dict[str, Any]]:
    source = manifest["source"]
    scenes = manifest.get("scenes", [])
    transcript = manifest.get("transcript", {})
    transcript_segments = transcript.get("segments", []) if isinstance(transcript, dict) else []
    audio_events = manifest.get("audio_events", [])
    sfx_floor = float(os.environ.get("VIDEO_AUDIO_ANALYZER_RETRIEVAL_SFX_MIN_CONFIDENCE", "0.60"))

    def reliable_audio_event(event: dict[str, Any]) -> bool:
        label = str(event.get("label", "")).strip()
        event_type = str(event.get("event_type", "")).lower()
        confidence = event.get("confidence")
        if not label or len(label) > 120:
            return False
        if confidence is None:
            return event_type in {"speech", "music", "sfx", "sfx_ambience"}
        threshold = sfx_floor if event_type in {"sfx", "sfx_ambience"} else 0.35
        return float(confidence) >= threshold

    def overlaps(item: dict[str, Any], start: float, end: float) -> bool:
        item_start = float(item.get("start_time_sec", 0.0) or 0.0)
        item_end = float(item.get("end_time_sec", item_start) or item_start)
        return item_start < end and item_end > start

    def visual_evidence(frames: list[dict[str, Any]]) -> str:
        cues: list[str] = []
        for frame in frames:
            evidence = frame.get("evidence", {})
            for key in ("subjects", "objects", "actions_visible", "continuity_facts"):
                values = evidence.get(key, [])
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, str):
                            cues.append(value)
                        elif isinstance(value, dict):
                            cues.extend(str(value[field]) for field in ("name", "label", "description", "action") if value.get(field))
            camera = evidence.get("camera", {})
            lighting = evidence.get("lighting", {})
            measurements = evidence.get("measurements", {})
            cues.extend(str(value) for value in (camera.get("framing"), camera.get("motion"), lighting.get("brightness_level"), lighting.get("contrast_level"), measurements.get("orientation")) if value)
            text = evidence.get("ocr", {}).get("text")
            if text:
                cues.append(str(text))
        return " ".join(dict.fromkeys(cues))

    # Scene clips are the semantic visual/audio-video retrieval unit. Do not
    # stamp a scene embedding onto every frame or audio event: that made many
    # unrelated records appear to have independent semantic vectors.
    for scene in scenes:
        start = float(scene.get("start_time_sec", 0.0))
        end = float(scene.get("end_time_sec", start))
        frames = scene.get("frames", [])
        dialogue = [str(item.get("text", "")).strip() for item in transcript_segments if overlaps(item, start, end) and item.get("text")]
        scene_sounds = [item for item in audio_events if overlaps(item, start, end) and reliable_audio_event(item)]
        scene_sounds.sort(key=lambda item: float(item.get("confidence") or 0.0), reverse=True)
        sounds = [str(item.get("label", "")).strip() for item in scene_sounds[:10]]
        cues = visual_evidence(frames)
        intern = manifest.get("internvideo3", {})
        clip_summary = str(scene.get("summary") or "").strip()
        text = " ".join(part for part in [source.get("file_name", ""), f"scene {scene.get('scene_id', '')}", clip_summary, cues,
            ("dialogue: " + " ".join(dialogue)) if dialogue else "",
            ("sound events: " + ", ".join(dict.fromkeys(sounds))) if sounds else ""] if part).strip()
        scene_vector = (scene.get("embeddings") or {}).get("audio_video")
        if not isinstance(scene_vector, list):
            scene_vector = None
        text_vector = (scene.get("embeddings") or {}).get("text_summary")
        if not isinstance(text_vector, list):
            text_vector = None
        yield {
            "record_id": scene["scene_id"], "kind": "scene_clip", "video_id": source["video_id"],
            "scene_id": scene["scene_id"], "start_time_sec": start, "end_time_sec": end,
            "text": text, "source_path": (scene.get("clip_path") or scene.get("video_path") or
                (f"/app/runs/{manifest.get('run_id')}/embeddings/{scene.get('scene_id')}.mp4" if manifest.get("run_id") else None) or
                (frames[0].get("path") if frames else None)),
            "pe_av_vector": scene_vector, "index_embedding_backend": "pe_av" if scene_vector else "deterministic_fallback",
            "pe_av_text_vector": text_vector,
            "pe_av_text_embedding_backend": "pe_av" if text_vector else "unavailable",
            "clap_vector": None, "clap_embedding_backend": "unavailable",
        }
        for frame in scene.get("frames", []):
            evidence = frame.get("evidence", {})
            if not frame.get("path") and not evidence:
                # Scene/change samples are segmentation signals, not useful
                # search records unless an image or measured evidence exists.
                continue
            frame_text = " ".join([source.get("file_name", ""), scene.get("scene_id", ""), frame.get("frame_id", ""), visual_evidence([frame])]).strip()
            frame_vector = (frame.get("embeddings") or {}).get("audio_video")
            if not isinstance(frame_vector, list):
                frame_vector = None
            yield {
                "record_id": frame["frame_id"], "kind": "frame", "video_id": source["video_id"], "scene_id": scene["scene_id"],
                "start_time_sec": frame["timestamp_sec"], "end_time_sec": frame["timestamp_sec"], "text": frame_text,
                "source_path": frame["path"], "pe_av_vector": frame_vector,
                "index_embedding_backend": "pe_av" if frame_vector else "deterministic_fallback",
                "clap_vector": None, "clap_embedding_backend": "unavailable",
            }
    full_summary = str(manifest.get("internvideo3", {}).get("full_video_summary") or "").strip()
    full_embedding = manifest.get("internvideo3", {}).get("full_video_summary_embedding", {})
    full_vector = full_embedding.get("vector") if isinstance(full_embedding, dict) else None
    if full_summary:
        yield {
            "record_id": f"{source['video_id']}:full_summary", "kind": "video_summary",
            "video_id": source["video_id"], "scene_id": None,
            "start_time_sec": 0.0, "end_time_sec": float(source.get("duration_sec", 0.0) or 0.0),
            "text": full_summary, "source_path": None,
            "pe_av_vector": None, "index_embedding_backend": "deterministic_fallback",
            "pe_av_text_vector": full_vector if isinstance(full_vector, list) else None,
            "pe_av_text_embedding_backend": "pe_av" if isinstance(full_vector, list) else "unavailable",
            "clap_vector": None, "clap_embedding_backend": "unavailable",
        }
    for event in audio_events:
        if not reliable_audio_event(event):
            continue
        mood = event.get("semantic_mood") if isinstance(event.get("semantic_mood"), dict) else {}
        mood_text = f"estimated music mood: {mood.get('top_match')}" if mood.get("top_match") else ""
        text = " ".join(part for part in [source.get("file_name", ""), str(event.get("label", "")), "audio activity", mood_text] if part)
        event_vector = (event.get("embeddings") or {}).get("audio") or (event.get("embeddings") or {}).get("audio_video")
        if not isinstance(event_vector, list):
            event_vector = None
        yield {
            "record_id": event["event_id"], "kind": "audio_event", "video_id": source["video_id"], "scene_id": None,
            "start_time_sec": event.get("start_time_sec", 0.0), "end_time_sec": event.get("end_time_sec", 0.0), "text": text,
            "source_path": manifest.get("audio", {}).get("analysis_wav"), "pe_av_vector": event_vector,
            "index_embedding_backend": "pe_av" if event_vector else "deterministic_fallback",
            "clap_vector": None, "clap_embedding_backend": "unavailable",
            "event_type": event.get("event_type"), "embedding_modality": "audio",
            "semantic_mood": event.get("semantic_mood"),
        }


def _preserve_legacy_clap(records: list[dict[str, Any]], legacy_index_dir: Path | None) -> dict[str, Any]:
    """Carry forward valid CLAP vectors from a prior index without re-embedding.

    Only exact (kind, record_id) matches and a single consistent vector dimension
    are accepted. The PE-AV and CLAP spaces remain independent.
    """
    if legacy_index_dir is None:
        return {"model": "LAION-AI/CLAP", "status": "unavailable_checkpoint_not_configured", "dimension": None}
    try:
        report = json.loads((legacy_index_dir / "index_manifest.json").read_text(encoding="utf-8"))
        old_rows = _load_records(legacy_index_dir)
    except (OSError, json.JSONDecodeError):
        return {"model": "LAION-AI/CLAP", "status": "legacy_index_unavailable", "dimension": None}
    old_clap = report.get("clap", {})
    expected_dim = int(old_clap.get("dimension") or report.get("vector_fields", {}).get("clap_vector") or 0)
    if old_clap.get("status") != "completed" or expected_dim <= 0:
        return {"model": "LAION-AI/CLAP", "status": "not_present_in_legacy_index", "dimension": None}
    source_rows: dict[tuple[str, str], list[float]] = {}
    for row in old_rows:
        vector = row.get("clap_vector")
        if (row.get("clap_embedding_backend") in {None, "laion_clap"}
                and isinstance(vector, list) and len(vector) == expected_dim
                and all(isinstance(value, (int, float)) for value in vector)):
            source_rows[(str(row.get("kind", "media")), str(row.get("record_id", "")))] = [float(value) for value in vector]
    preserved = 0
    for row in records:
        vector = source_rows.get((str(row.get("kind", "media")), str(row.get("record_id", ""))))
        if vector is None:
            continue
        row["clap_vector"] = vector
        row["clap_embedding_backend"] = "laion_clap"
        row.setdefault("clap_embedding_kind", "legacy_preserved")
        preserved += 1
    return {"model": "LAION-AI/CLAP", "status": "completed" if preserved else "legacy_vectors_no_exact_record_matches",
            "dimension": expected_dim if preserved else None, "vector_field": "clap_vector",
            "preserved_from": str(legacy_index_dir), "preserved_record_count": preserved,
            "concatenated_with_pe_av": False}


def build_index(manifest: dict[str, Any], run_dir: Path, index_name: str = "index",
                preserve_clap_from: Path | None = None) -> dict[str, Any]:
    index_dir = run_dir / index_name
    index_dir.mkdir(parents=True, exist_ok=True)
    records = list(_records(manifest))
    clap_status: dict[str, Any] = _preserve_legacy_clap(records, preserve_clap_from)
    allow_audio_embeddings = bool(manifest.get("options", {}).get("create_audio_embeddings", True))
    if not allow_audio_embeddings:
        for row in records:
            if row.get("kind") == "audio_event":
                row["clap_vector"] = None
                row["clap_embedding_backend"] = "disabled_by_analysis_option"
    clap_checkpoint = os.environ.get("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT")
    clap_worker = os.environ.get("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL")
    if clap_checkpoint or clap_worker:
        try:
            from .clap_adapter import configured_adapter
            adapter = configured_adapter()
            text_rows = [row["text"] for row in records]
            text_vectors = adapter.text(text_rows) if text_rows else []
            for row, vector in zip(records, text_vectors):
                row["clap_vector"] = [float(x) for x in vector]
                row["clap_embedding_backend"] = "laion_clap"
                row["clap_embedding_kind"] = "text"
            audio_rows = [row for row in records if allow_audio_embeddings and row["kind"] == "audio_event" and row.get("source_path") and Path(row["source_path"]).is_file()]
            with tempfile.TemporaryDirectory(prefix="vaa-clap-") as temp_dir:
                clips: list[Path] = []
                clip_rows: list[dict[str, Any]] = []
                for index, row in enumerate(audio_rows):
                    clip = Path(temp_dir) / f"event_{index:05d}.wav"
                    duration = max(0.25, float(row.get("end_time_sec", 0)) - float(row.get("start_time_sec", 0)))
                    try:
                        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(row.get("start_time_sec", 0)), "-t", str(duration), "-i", str(row["source_path"]), "-ac", "1", "-ar", "48000", str(clip)], check=True, capture_output=True)
                        clips.append(clip); clip_rows.append(row)
                    except Exception:
                        continue
                if clips:
                    audio_vectors = adapter.audio(clips)
                    for row, vector in zip(clip_rows, audio_vectors):
                        row["clap_vector"] = [float(x) for x in vector]
                        row["clap_embedding_backend"] = "laion_clap"
                        row["clap_embedding_kind"] = "audio"
            dimension = next((len(row["clap_vector"]) for row in records if row.get("clap_vector")), None)
            clap_status = {"model": "LAION-AI/CLAP", "status": "completed", "dimension": dimension,
                           "checkpoint": str(clap_checkpoint) if clap_checkpoint else None,
                           "worker_url": clap_worker if not clap_checkpoint else None,
                           "vector_field": "clap_vector", "concatenated_with_pe_av": False,
                           "audio_embeddings_requested": allow_audio_embeddings}
        except Exception as exc:
            clap_status = {"model": "LAION-AI/CLAP", "status": "error", "reason": str(exc), "concatenated_with_pe_av": False}
    jsonl = index_dir / "records.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    status = _model_status()
    peav_vectors = [record["pe_av_vector"] for record in records if record.get("index_embedding_backend") == "pe_av"]
    text_vectors = [record["pe_av_text_vector"] for record in records if record.get("pe_av_text_embedding_backend") == "pe_av"]
    vector_dimension = len(peav_vectors[0]) if peav_vectors else None
    text_dimension = len(text_vectors[0]) if text_vectors else None
    if (peav_vectors or text_vectors) and (manifest.get("embeddings", {}).get("pe_av", {}).get("status") == "completed"
            or manifest.get("embeddings", {}).get("pe_av", {}).get("text_summary", {}).get("status") == "completed"):
        vector_dimension = vector_dimension or text_dimension
        status = {**status, "backend": "pe_av", "status": "completed", "dimension": vector_dimension}
    lance_status = _lancedb_status()
    if lance_status.get("status") == "ready":
        try:
            import lancedb
            db = lancedb.connect(str(index_dir / "lancedb"))
            table_rows = [{**record, "vector": record["pe_av_vector"]} for record in records if record.get("index_embedding_backend") == "pe_av"]
            if table_rows:
                table = db.create_table("media_events", data=table_rows, mode="overwrite")
                lance_status = {**lance_status, "status": "ready", "table": "media_events", "rows": table.count_rows()}
        except Exception as exc:
            lance_status = {"status": "error", "error": f"table creation failed after probe: {exc}", "fallback": "jsonl"}
    report = {
        "record_schema_version": 3,
        "backend": "lancedb" if lance_status.get("status") == "ready" and lance_status.get("table") else "jsonl",
        # Corpus search currently performs multi-run late fusion over JSONL.
        # The Lance table is retained but not yet queried by search_all().
        "vector_search_backend": "exact_jsonl_scan",
        "model": status,
        "clap": clap_status,
        "record_count": len(records),
        "vector_fields": {"pe_av_vector": vector_dimension, "pe_av_text_vector": text_dimension, "clap_vector": clap_status.get("dimension")},
        "late_fusion": "normalized PE-AV score plus optional CLAP score; no vector concatenation",
        "ann": "lancedb_table_written_but_not_used_by_corpus_query" if lance_status.get("status") == "ready" and lance_status.get("table") else "not_enabled_for_jsonl_scan",
        "lancedb": lance_status,
    }
    (index_dir / "index_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _load_records(index_dir: Path) -> list[dict[str, Any]]:
    path = index_dir / "records.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _query_embeddings(query: str, records: list[dict[str, Any]], mode: str) -> tuple[list[float], str, list[float] | None, str]:
    query_vector = _hash_vector(query)
    query_backend = "deterministic_fallback"
    if mode in {"semantic", "hybrid"} and os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_PATH"):
        try:
            from .peav_adapter import configured_adapter
            output = configured_adapter().embed(text=query)
            query_vector = (output.get("text_audio_video_embeds") or output.get("visual_text_embeds") or output.get("text_video_embeds") or [[None]])[0]
            dimensions = {len(value) for row in records for value in (
                row.get("pe_av_vector") if row.get("index_embedding_backend") == "pe_av" else None,
                row.get("pe_av_text_vector") if row.get("pe_av_text_embedding_backend") == "pe_av" else None,
            ) if isinstance(value, list) and value}
            if query_vector and query_vector[0] is not None and len(query_vector) in dimensions:
                query_backend = "pe_av"
            else:
                query_vector = _hash_vector(query)
        except Exception:
            query_vector = _hash_vector(query)
    elif mode in {"semantic", "hybrid"} and os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL"):
        try:
            query_vector = _remote_peav_text(query)
            dimensions = {len(value) for row in records for value in (
                row.get("pe_av_vector") if row.get("index_embedding_backend") == "pe_av" else None,
                row.get("pe_av_text_vector") if row.get("pe_av_text_embedding_backend") == "pe_av" else None,
            ) if isinstance(value, list) and value}
            if query_vector and len(query_vector) in dimensions:
                query_backend = "pe_av"
            else:
                query_vector = _hash_vector(query)
        except Exception:
            query_vector = _hash_vector(query)
    clap_query: list[float] | None = None
    clap_backend = "unavailable"
    clap_config = os.environ.get("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT")
    clap_worker = os.environ.get("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL")
    if (clap_config or clap_worker) and mode in {"semantic", "hybrid"}:
        try:
            from .clap_adapter import configured_adapter
            clap_query = configured_adapter().text([query])[0]
            clap_backend = "laion_clap"
        except Exception:
            clap_query = None
    return query_vector, query_backend, clap_query, clap_backend


def _remote_peav_text(query: str) -> list[float]:
    """Request one query embedding from the isolated PE-AV worker."""
    base_url = os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL is not configured")
    request = urllib.request.Request(
        f"{base_url}/embed/text",
        data=json.dumps({"text": query}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = max(1.0, float(os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_TIMEOUT", "45")))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("model") != PE_AV_MODEL:
        raise RuntimeError(f"unexpected PE-AV query worker model: {payload.get('model')!r}")
    vector = payload.get("embedding")
    if not isinstance(vector, list) or not vector or not all(isinstance(value, (int, float)) for value in vector):
        raise RuntimeError("PE-AV query worker returned an invalid embedding")
    return [float(value) for value in vector]


def search_records(records: list[dict[str, Any]], query: str, top_n: int = 5, mode: str = "semantic",
                   offset: int = 0, exclude_ids: set[str] | None = None) -> dict[str, Any]:
    if mode not in {"semantic", "keyword", "hybrid"}:
        raise ValueError("mode must be semantic, keyword, or hybrid")
    exclude_ids = exclude_ids or set()
    query_vector, query_backend, clap_query, clap_backend = _query_embeddings(query, records, mode)
    has_peav_candidates = any((record.get("index_embedding_backend") == "pe_av" and record.get("pe_av_vector"))
        or (record.get("pe_av_text_embedding_backend") == "pe_av" and record.get("pe_av_text_vector")) for record in records)
    if mode == "semantic" and (query_backend != "pe_av" or not has_peav_candidates) and clap_query is not None:
        query_backend = "laion_clap"
    if mode == "semantic" and query_backend not in {"pe_av", "laion_clap"}:
        return {"query": query, "mode": mode, "query_backend": query_backend, "clap_backend": clap_backend,
            "fusion": "late_score_fusion_no_vector_concatenation", "top_n": top_n, "offset": offset,
            "results": [], "next_offset": None, "total_candidates": 0,
            "reason": "No real PE-AV or CLAP query embedding is available; semantic results are withheld."}
    terms = set(query.lower().split())
    scored: list[dict[str, Any]] = []
    for record in records:
        identity = str(record.get("result_id") or record["record_id"])
        if identity in exclude_ids or record["record_id"] in exclude_ids:
            continue
        video_vector = record.get("pe_av_vector") if record.get("index_embedding_backend") == "pe_av" else None
        text_vector = record.get("pe_av_text_vector") if record.get("pe_av_text_embedding_backend") == "pe_av" else None
        video_match = isinstance(video_vector, list) and len(video_vector) == len(query_vector)
        text_match = isinstance(text_vector, list) and len(text_vector) == len(query_vector)
        has_semantic = video_match or text_match
        has_clap = (record.get("clap_embedding_backend") in {None, "laion_clap"}
                    and isinstance(record.get("clap_vector"), list) and bool(record.get("clap_vector")))
        # A semantic result must have a vector in the queried embedding space.
        # CLAP-only rows are not valid zero-score PE-AV hits (and vice versa).
        # In hybrid mode lexical matches can still be useful without vectors.
        if mode == "semantic" and query_backend == "pe_av" and not has_semantic:
            continue
        if mode == "semantic" and query_backend == "laion_clap" and not has_clap:
            continue
        video_score = _cosine(query_vector, video_vector) if video_match else None
        text_score = _cosine(query_vector, text_vector) if text_match else None
        available_scores = [value for value in (video_score, text_score) if value is not None]
        # Separate PE-AV spaces/representations are late-fused as scores, never concatenated.
        semantic = sum(available_scores) / len(available_scores) if available_scores else 0.0
        text_terms = set(record.get("text", "").lower().split())
        keyword = len(terms & text_terms) / max(1, len(terms)) if mode in {"keyword", "hybrid"} else 0.0
        clap_score = _cosine(clap_query, record["clap_vector"]) if clap_query and has_clap else 0.0
        if mode == "semantic":
            score = clap_score if query_backend == "laion_clap" else semantic
        else:
            score = keyword if mode == "keyword" else 0.7 * semantic + 0.3 * keyword
        scored.append({**record, "semantic_video_score": round(video_score, 6) if video_score is not None else None,
            "semantic_text_score": round(text_score, 6) if text_score is not None else None,
            "semantic_score": round(semantic, 6), "keyword_score": round(keyword, 6), "clap_score": round(clap_score, 6), "score": round(score, 6)})
    if clap_backend == "laion_clap" and query_backend == "pe_av" and mode in {"semantic", "hybrid"}:
        # Rerank only a bounded PE-AV candidate pool; normalize each score
        # independently and combine late, never concatenate vectors.
        pool = sorted(scored, key=lambda row: -row["score"])[:max(50, top_n)]
        ids = [str(row.get("result_id") or row["record_id"]) for row in pool]
        from .clap_adapter import late_fusion
        fused = late_fusion(
            [row["score"] for row in pool], {identity: row["clap_score"] for identity, row in zip(ids, pool)}, ids)
        for row, value in zip(pool, fused): row["score"] = round(value, 6)
        scored = pool + [row for row in scored if row not in pool]
    scored.sort(key=lambda item: (-item["score"], str(item.get("run_id", "")), item["record_id"]))
    page = scored[offset:offset + max(1, top_n)]
    return {"query": query, "mode": mode, "query_backend": query_backend, "clap_backend": clap_backend, "fusion": "late_score_fusion_no_vector_concatenation", "top_n": top_n, "offset": offset, "results": page, "next_offset": offset + len(page) if offset + len(page) < len(scored) else None, "total_candidates": len(scored)}


def search(index_dir: Path, query: str, top_n: int = 5, mode: str = "semantic", offset: int = 0,
           exclude_ids: set[str] | None = None) -> dict[str, Any]:
    return search_records(_load_records(index_dir), query, top_n, mode, offset, exclude_ids)


def search_all(runs_root: Path, query: str, top_n: int = 5, mode: str = "semantic", offset: int = 0,
               exclude_ids: set[str] | None = None) -> dict[str, Any]:
    """Search all persisted run indexes without mixing embedding spaces."""
    if mode not in {"semantic", "keyword", "hybrid"}:
        raise ValueError("mode must be semantic, keyword, or hybrid")
    if not query.strip():
        raise ValueError("query must not be blank")
    records_by_clip: dict[tuple[str, str, str], dict[str, Any]] = {}
    source_runs: list[dict[str, Any]] = []
    for manifest_path in sorted(Path(runs_root).glob("*/manifest.json")):
        run_dir = manifest_path.parent
        shared_index_root = Path(os.environ.get(
            "VIDEO_AUDIO_ANALYZER_CORPUS_INDEX_ROOT", Path(runs_root).parent / "corpus_index_v2"))
        corpus_index = shared_index_root / run_dir.name / "index"
        run_index_v2 = run_dir / "index_v2"
        index_dir = corpus_index if (corpus_index / "records.jsonl").is_file() else run_index_v2 if (run_index_v2 / "records.jsonl").is_file() else run_dir / "index"
        run_records = _load_records(index_dir)
        if not run_records:
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            index_manifest = json.loads((index_dir / "index_manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest, index_manifest = {}, {}
        model = index_manifest.get("model", {})
        dimension = int(index_manifest.get("vector_fields", {}).get("pe_av_vector", 0) or 0)
        text_dimension = int(index_manifest.get("vector_fields", {}).get("pe_av_text_vector", 0) or 0)
        clap_dimension = int(index_manifest.get("vector_fields", {}).get("clap_vector", 0) or 0)
        actual_peav = (index_manifest.get("record_schema_version", 0) >= 2
            and model.get("backend") == "pe_av"
            and (manifest.get("embeddings", {}).get("pe_av", {}).get("status") == "completed"
                 or manifest.get("embeddings", {}).get("pe_av", {}).get("text_summary", {}).get("status") == "completed")
            and (dimension > 0 or text_dimension > 0))
        actual_clap = index_manifest.get("clap", {}).get("status") == "completed" and clap_dimension > 0
        backend = "pe_av" if actual_peav else "laion_clap" if actual_clap else "deterministic_fallback"
        if mode == "semantic" and not actual_peav and not actual_clap:
            # Do not market lexical hash vectors as semantic matches.
            continue
        source = manifest.get("source", {}) if isinstance(manifest.get("source"), dict) else {}
        source_identity = str(source.get("video_id") or source.get("file_name") or run_dir.name)
        run_mtime = manifest_path.stat().st_mtime
        eligible_records = [record for record in run_records
            if mode != "semantic" or
                (actual_peav and ((record.get("index_embedding_backend") == "pe_av" and dimension > 0 and len(record.get("pe_av_vector") or []) == dimension) or
                    (record.get("pe_av_text_embedding_backend") == "pe_av" and text_dimension > 0 and len(record.get("pe_av_text_vector") or []) == text_dimension))) or
                (actual_clap and len(record.get("clap_vector") or []) == clap_dimension)]
        if mode == "semantic" and not eligible_records:
            continue
        for record in eligible_records:
            record_backend = "pe_av" if actual_peav and ((dimension > 0 and record.get("index_embedding_backend") == "pe_av" and len(record.get("pe_av_vector") or []) == dimension) or (text_dimension > 0 and record.get("pe_av_text_embedding_backend") == "pe_av" and len(record.get("pe_av_text_vector") or []) == text_dimension)) else "deterministic_fallback"
            clap_backend = "laion_clap" if actual_clap and len(record.get("clap_vector") or []) == clap_dimension else "unavailable"
            indexed = {**record, "run_id": run_dir.name, "result_id": f"{run_dir.name}:{record['record_id']}",
                "source_file": source.get("file_name"), "source_video_id": source.get("video_id"),
                "index_embedding_backend": record_backend, "clap_embedding_backend": clap_backend,
                "run_updated_at": run_mtime}
            key = (source_identity, str(record.get("kind", "media")), str(record["record_id"]))
            previous = records_by_clip.get(key)
            if previous is None or run_mtime > float(previous.get("run_updated_at", 0)):
                records_by_clip[key] = indexed
        source_runs.append({"run_id": run_dir.name, "embedding_backend": backend, "record_count": len(eligible_records)})
    records = list(records_by_clip.values())
    result = search_records(records, query, top_n, mode, offset, exclude_ids)
    result["corpus_run_count"] = len(source_runs)
    result["corpus_video_count"] = len({str(row.get("source_video_id") or row.get("source_file")) for row in records})
    result["source_runs"] = source_runs
    result["semantic_results_filtered_to_real_models"] = mode == "semantic"
    if mode == "semantic" and result.get("query_backend") not in {"pe_av", "laion_clap"}:
        result.update(results=[], next_offset=None, total_candidates=0,
            reason="No real PE-AV or CLAP text query embedding is available; semantic search is withheld instead of using lexical fallback vectors.")
    return result
