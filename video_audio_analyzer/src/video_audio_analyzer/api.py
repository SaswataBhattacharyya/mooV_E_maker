from __future__ import annotations

import json
import os
import threading
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .pipeline import AnalyzerOptions, analyze_video
from .preflight import run_preflight
from .retrieval import search as search_index
from .codex_director_review import apply_director_overlay


ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title="Video Audio Analyzer", version="0.1.0")
_jobs: dict[str, dict[str, Any]] = {}
_sam_previews: dict[str, dict[str, Any]] = {}


class AnalyzeRequest(BaseModel):
    video_path: str
    extract_fps: float = 4.0
    cut_boundary_threshold: float = 0.18
    min_cut_seconds: float = 0.5
    extract_cut_clips: bool = True
    run_demucs: str = "AUTO"
    detect_speech: bool = True
    detect_music: bool = True
    detect_sfx: bool = True
    create_audio_embeddings: bool = True
    create_av_embeddings: bool = True
    diarize_speakers: bool = True
    collect_voice_examples: bool = False
    collect_music_clips: bool = False
    collect_sfx_clips: bool = False
    adaptive_sampling: bool = True
    keep_intermediate_samples: bool = False
    delete_intermediate_samples: bool = True
    preserve_scene_anchors: bool = True


class SearchRequest(BaseModel):
    video_id: str
    query: str
    top_n: int = 5
    mode: str = "semantic"
    offset: int = 0


class CorpusSearchRequest(BaseModel):
    query: str
    top_n: int = 5
    mode: str = "semantic"
    offset: int = 0


class SAMIsolateRequest(BaseModel):
    run_id: str
    event_id: str
    prompt: str


class SAMSaveRequest(BaseModel):
    director_decision: str


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "video_audio_analyzer", "version": "0.1.0"}


@app.get("/api/preflight")
def preflight() -> dict[str, Any]:
    return run_preflight(ROOT)


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    video = Path(request.video_path).expanduser().resolve()
    if not video.is_file():
        raise HTTPException(status_code=404, detail=f"Video not found: {video}")
    job_id = video.stem + "-" + str(abs(hash(str(video))))[:8]
    _jobs[job_id] = {"job_id": job_id, "status": "running", "video_path": str(video)}

    def worker() -> None:
        try:
            manifest = analyze_video(video, ROOT, AnalyzerOptions(
                extract_fps=request.extract_fps,
                cut_boundary_threshold=request.cut_boundary_threshold,
                min_cut_seconds=request.min_cut_seconds,
                extract_cut_clips=request.extract_cut_clips,
                run_demucs=request.run_demucs,
                detect_speech=request.detect_speech,
                detect_music=request.detect_music,
                detect_sfx=request.detect_sfx,
                create_audio_embeddings=request.create_audio_embeddings,
                create_av_embeddings=request.create_av_embeddings,
                diarize_speakers=request.diarize_speakers,
                collect_voice_examples=request.collect_voice_examples,
                collect_music_clips=request.collect_music_clips,
                collect_sfx_clips=request.collect_sfx_clips,
                adaptive_sampling=request.adaptive_sampling,
                keep_intermediate_samples=request.keep_intermediate_samples,
                delete_intermediate_samples=request.delete_intermediate_samples,
                preserve_scene_anchors=request.preserve_scene_anchors,
            ))
            _jobs[job_id] = {"job_id": job_id, "status": "completed", "video_id": manifest["source"]["video_id"], "manifest": manifest}
        except Exception as exc:
            _jobs[job_id] = {"job_id": job_id, "status": "error", "error": str(exc)}

    threading.Thread(target=worker, daemon=True).start()
    return _jobs[job_id]


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return _jobs[job_id]


@app.get("/api/runs/{video_id}/manifest")
def manifest(video_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{16}(?:-rerun-[a-f0-9]{8})?", video_id):
        raise HTTPException(status_code=400, detail="invalid video/run ID")
    path = ROOT / "runs" / video_id / "manifest.json"
    if not path.exists():
        candidates = sorted((ROOT / "runs").glob(f"{video_id}-rerun-*/manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        path = candidates[0] if candidates else path
    if not path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")
    result = json.loads(path.read_text(encoding="utf-8"))
    return apply_director_overlay(result, ROOT / "director_reviews")


@app.post("/api/search")
def search(request: SearchRequest) -> dict[str, Any]:
    if not request.query.strip():
        raise HTTPException(status_code=422, detail="query must not be blank")
    if request.mode not in {"semantic", "keyword", "hybrid"}:
        raise HTTPException(status_code=422, detail="mode must be semantic, keyword, or hybrid")
    if not re.fullmatch(r"[a-f0-9]{16}(?:-rerun-[a-f0-9]{8})?", request.video_id):
        raise HTTPException(status_code=400, detail="invalid video/run ID")
    run = ROOT / "runs" / request.video_id
    if not (run / "manifest.json").exists() and "-rerun-" not in request.video_id:
        candidates = sorted((ROOT / "runs").glob(f"{request.video_id}-rerun-*/manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        run = candidates[0].parent if candidates else run
    corpus_index = ROOT / "corpus_index_v2" / run.name / "index"
    index_v2 = run / "index_v2"
    index_dir = corpus_index if (corpus_index / "records.jsonl").is_file() else index_v2 if (index_v2 / "records.jsonl").is_file() else run / "index"
    if not (index_dir / "records.jsonl").exists():
        raise HTTPException(status_code=404, detail="search index not found for this video run")
    return search_index(index_dir, request.query, top_n=max(1, min(request.top_n, 50)), mode=request.mode, offset=max(0, request.offset))


@app.post("/api/search/all")
def search_all(request: CorpusSearchRequest) -> dict[str, Any]:
    """Search all analysis-run indexes, returning globally paginated results."""
    if not request.query.strip():
        raise HTTPException(status_code=422, detail="query must not be blank")
    if request.mode not in {"semantic", "keyword", "hybrid"}:
        raise HTTPException(status_code=422, detail="mode must be semantic, keyword, or hybrid")
    try:
        from .retrieval import search_all as search_corpus
        return search_corpus(ROOT / "runs", request.query.strip(), top_n=max(1, min(request.top_n, 50)),
                             mode=request.mode, offset=max(0, request.offset))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sam/isolate")
def sam_isolate(request: SAMIsolateRequest) -> dict[str, Any]:
    """Isolate only a specifically selected/directed event; never auto-save it."""
    if not re.fullmatch(r"[a-f0-9]{16}(?:-rerun-[a-f0-9]{8})?", request.run_id):
        raise HTTPException(status_code=400, detail="invalid run ID")
    run_dir = ROOT / "runs" / request.run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="analysis run not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    event = next((row for row in manifest.get("audio_events", []) if row.get("event_id") == request.event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail="audio event not found in this run")
    audio_path = Path(manifest.get("audio", {}).get("analysis_wav", ""))
    if not audio_path.is_file():
        candidate = run_dir / "audio" / "analysis.wav"
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="run analysis audio is missing")
        audio_path = candidate
    from .sam_audio_adapter import isolate
    temp_root = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_TEMP_PATH", str(ROOT / "temp" / "sam_audio")))
    result = isolate(audio_path=audio_path, prompt=request.prompt,
        start_sec=float(event.get("start_time_sec", 0)), end_sec=float(event.get("end_time_sec", 0)),
        temp_root=temp_root, provenance={"run_id": request.run_id, "video_id": manifest.get("source", {}).get("video_id"),
            "event_id": request.event_id, "detector": event.get("detector"), "label": event.get("label")})
    if result.get("status") != "preview_ready":
        # 503 contains a truthful preflight reason, not a pretend output asset.
        raise HTTPException(status_code=503, detail=result)
    _sam_previews[result["temporary_id"]] = result
    return result


@app.post("/api/sam/{temporary_id}/save")
def sam_save(temporary_id: str, request: SAMSaveRequest) -> dict[str, Any]:
    """Persist only after an explicit director save_to_repertoire decision."""
    if not re.fullmatch(r"sam-[a-f0-9]{32}", temporary_id):
        raise HTTPException(status_code=400, detail="invalid temporary asset ID")
    preview = _sam_previews.get(temporary_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="temporary SAM preview not found or expired")
    from .sam_audio_adapter import save_to_repertoire
    repertoire_root = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_REPERTOIRE_PATH", str(ROOT / "video_repertoire")))
    try:
        result = save_to_repertoire(preview, repertoire_root, director_decision=request.director_decision)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result
