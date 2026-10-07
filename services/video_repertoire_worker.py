"""Subprocess worker for Video Repertoire download and analysis jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from story_builder.services import video_repertoire as store
from story_builder.services.media_jobs import gpu_workload_guard


class _GpuMemorySampler:
    """Best-effort host GPU allocation sampler for an analysis job.

    Reports total compute-process allocations, not a falsely precise attribution
    to one container. The baseline/delta help separate resident services from
    the peak observed while this job was active.
    """

    def __init__(self, interval_seconds: float = 1.0) -> None:
        self.interval_seconds = interval_seconds
        self.samples: list[int] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _read_compute_allocations_mib() -> int | None:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=used_memory", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=False)
            if result.returncode != 0:
                return None
            values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
            return sum(values)
        except (OSError, subprocess.SubprocessError, AttributeError, TypeError, ValueError):
            return None

    def _sample(self) -> None:
        while not self._stop.is_set():
            value = self._read_compute_allocations_mib()
            if value is not None:
                self.samples.append(value)
            self._stop.wait(self.interval_seconds)

    def __enter__(self) -> "_GpuMemorySampler":
        self._thread = threading.Thread(target=self._sample, name="analysis-gpu-sampler", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=4)
        # Take a final sample so short jobs still have an end reading.
        value = self._read_compute_allocations_mib()
        if value is not None:
            self.samples.append(value)

    def report(self) -> dict[str, Any]:
        if not self.samples:
            return {"available": False, "reason": "nvidia-smi compute memory query unavailable"}
        baseline = self.samples[0]
        peak = max(self.samples)
        return {"available": True, "measurement": "host_compute_process_allocations",
                "sample_interval_seconds": self.interval_seconds,
                "baseline_mib": baseline, "peak_mib": peak,
                "peak_delta_mib": max(0, peak - baseline),
                "sample_count": len(self.samples),
                "note": "Includes concurrent/resident GPU processes; peak delta is an estimate, not isolated per-container VRAM."}


def save_job(kind: str, job_id: str, **changes: Any) -> dict[str, Any]:
    path = store.job_path(kind, job_id)
    job = json.loads(path.read_text(encoding="utf-8"))
    if job.get("status") in {"cancelled", "cancel_requested"}:
        return job
    job.update(changes, updated_at=store.utc_now())
    store._atomic_json(path, job)
    return job


def event(kind: str, job_id: str, stage: str, status: str, message: str, progress: int, payload: dict[str, Any] | None = None) -> None:
    path = store.job_path(kind, job_id)
    job = json.loads(path.read_text(encoding="utf-8"))
    if job.get("status") in {"cancelled", "cancel_requested"}:
        raise KeyboardInterrupt("Job cancelled")
    job.setdefault("events", []).append({"timestamp": store.utc_now(), "stage": stage, "status": status, "message": message, "payload": payload or {}})
    job["events"] = job["events"][-300:]
    job.update(stage=stage, message=message, progress=max(job.get("progress", 0), min(progress, 99)), updated_at=store.utc_now())
    store._atomic_json(path, job)


def _analyzer_visual_scenes(manifest: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    """Expose only run-relative frame artifacts and compact measured evidence."""
    run_id = str(manifest.get("run_id", ""))
    marker = f"/app/runs/{run_id}/"
    scenes: list[dict[str, Any]] = []
    for scene in manifest.get("scenes", []):
        scene_id = str(scene.get("scene_id", ""))
        frames: list[dict[str, Any]] = []
        for frame in scene.get("frames", []):
            container_path = str(frame.get("path", ""))
            relative = container_path.split(marker, 1)[1] if marker in container_path else ""
            candidate = (run_dir / relative).resolve() if relative else None
            try:
                if candidate is not None:
                    candidate.relative_to(run_dir.resolve())
            except ValueError:
                candidate = None
            artifact_path = relative if candidate is not None and candidate.is_file() else None
            evidence = frame.get("evidence", {}) if isinstance(frame.get("evidence"), dict) else {}
            frames.append({
                "frame_id": frame.get("frame_id"), "timestamp_sec": frame.get("timestamp_sec"),
                "artifact_path": Path(relative).as_posix() if artifact_path else None,
                "change_score": frame.get("change_score"),
                "camera_motion_score": frame.get("camera_motion_score"),
                "measurements": evidence.get("measurements", {}),
                "dominant_colors": evidence.get("dominant_colors", []),
                "subjects": evidence.get("subjects", []), "objects": evidence.get("objects", []),
                "actions_visible": evidence.get("actions_visible", []),
                "camera": evidence.get("camera", {}), "lighting": evidence.get("lighting", {}),
                "ocr": evidence.get("ocr", {}), "continuity_facts": evidence.get("continuity_facts", []),
                "uncertainties": evidence.get("uncertainties", []),
                "confidence": evidence.get("confidence", {}),
            })
        clip_relative = f"embeddings/{scene_id}.mp4" if scene_id else ""
        clip_path = (run_dir / clip_relative).resolve() if clip_relative else None
        try:
            if clip_path is not None:
                clip_path.relative_to(run_dir.resolve())
        except ValueError:
            clip_path = None
        scenes.append({
            "scene_id": scene_id, "start_time_sec": scene.get("start_time_sec"),
            "end_time_sec": scene.get("end_time_sec"), "duration_sec": scene.get("duration_sec"),
            "clip_artifact_path": clip_relative if clip_path is not None and clip_path.is_file() else None,
            "frames": frames,
        })
    return scenes


def run_youtube(job_id: str, request: dict[str, Any]) -> dict[str, Any]:
    urls = request.get("urls", [])
    max_height = int(request.get("max_height", 720))
    if not urls:
        raise ValueError("At least one URL is required")
    if max_height != 720:
        raise ValueError("The current downloader supports the approved 720p preset only")
    outputs = []
    failures = []
    for index, item in enumerate(urls, start=1):
        url = item.get("url") if isinstance(item, dict) else str(item)
        event("youtube", job_id, "download", "running", f"Downloading {index} of {len(urls)}", int(5 + 85 * (index - 1) / len(urls)), {"url": url})
        try:
            path, metadata = _download_with_cli(url, store.REPERTOIRE_ROOT / "downloads")
            asset = store.register_asset(
                path, source_mode=request.get("source_mode", "urls"), source_url=url,
                title=str(metadata.get("title", "")), channel=str(metadata.get("channel") or metadata.get("uploader") or ""),
                provenance_notes=str(request.get("provenance_notes", "")), metadata={"extractor": metadata.get("extractor"), "id": metadata.get("id")},
            )
            outputs.append(asset)
        except Exception as exc:
            failures.append({"url": url, "error": str(exc)})
    return {"assets": outputs, "failures": failures}


def _download_with_cli(url: str, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    executable = shutil.which("yt-dlp") or shutil.which("yt-dlp_linux")
    if not executable:
        raise RuntimeError("yt-dlp executable is not available")
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_run = subprocess.run([executable, "--no-playlist", "--dump-single-json", url], check=True, capture_output=True, text=True, timeout=120)
    metadata = json.loads(metadata_run.stdout)
    command = [
        executable, "--no-playlist",
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "--merge-output-format", "mp4", "--print", "after_move:filepath",
        "-o", str(output_dir / "%(title)s.%(ext)s"), url,
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=7200)
    candidates = [Path(line.strip()) for line in completed.stdout.splitlines() if line.strip()]
    path = next((item for item in reversed(candidates) if item.exists()), None)
    if path is None:
        raise FileNotFoundError("yt-dlp completed without reporting a downloaded file")
    return path, metadata


def _make_clip(source: Path, destination: Path, start: float, end: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.05, end - start)
    copy_command = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration), "-c", "copy", str(destination)]
    result = subprocess.run(copy_command, capture_output=True)
    if result.returncode or not destination.exists() or destination.stat().st_size == 0:
        encode_command = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration), "-c:v", "libx264", "-c:a", "aac", str(destination)]
        subprocess.run(encode_command, check=True, capture_output=True)


def _run_direct_analyzer(job_id: str, assets: list[dict[str, Any]], settings: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    """Run the isolated clip-first analyzer as the primary website analysis path."""
    analyzer_root = store.PROJECT_ROOT / "video_audio_analyzer"
    launcher = analyzer_root / "run_peav_worker.sh"
    if not launcher.is_file():
        raise FileNotFoundError(f"Direct video/audio analyzer launcher is missing: {launcher}")
    audio_settings = settings.get("audio_analyzer", {}) if isinstance(settings.get("audio_analyzer", {}), dict) else {}
    audio_enabled = bool(settings.get("audio_analyzer_enabled", True))
    fps = float(audio_settings.get("extract_fps", settings.get("extract_fps", 2.0)))
    args_by_setting = (
        ("detect_speech", "--detect-speech"), ("detect_music", "--detect-music"),
        ("detect_sfx", "--detect-sfx"), ("create_audio_embeddings", "--create-audio-embeddings"),
        ("create_av_embeddings", "--create-av-embeddings"), ("diarize_speakers", "--diarize-speakers"),
        ("extract_source_audio", "--extract-source-audio"), ("extract_preview_mp3", "--extract-mp3"),
    )
    videos: list[dict[str, Any]] = []
    audio_runs: list[dict[str, Any]] = []
    for index, asset in enumerate(assets, start=1):
        source = store.safe_path(Path(asset["path"]), store.REPERTOIRE_ROOT, store.LEGACY_VIDEO_ROOT)
        event("analysis", job_id, "video_audio_analyzer", "running",
            f"Analyzing video {index} of {len(assets)} with direct-video InternVideo3; audio stages are independently configurable.",
            12 + int(80 * (index - 1) / max(1, len(assets))), {"asset_id": asset["asset_id"], "title": asset.get("title", source.name)})
        args = ["bash", str(launcher), str(source), "--extract-fps", str(fps),
            "--run-demucs", str(audio_settings.get("run_demucs", "AUTO") if audio_enabled else "off"),
            "--frame-change-threshold", str(audio_settings.get("frame_change_threshold", 0.08)),
            "--no-persist-selected-frames", "--no-analyze-frame-evidence",
            "--project-id", str(audio_settings.get("project_id") or asset["asset_id"])]
        for key, flag in args_by_setting:
            enabled = audio_enabled and bool(audio_settings.get(key, True))
            args.append(flag if enabled else "--no-" + flag[2:])
        args.append("--adaptive-sampling" if audio_settings.get("adaptive_sampling", True) else "--no-adaptive-sampling")
        args.append("--preserve-scene-anchors" if audio_settings.get("preserve_scene_anchors", True) else "--no-preserve-scene-anchors")
        if audio_settings.get("keep_intermediate_samples", False):
            args.append("--keep-intermediate-samples")
        for key, flag in (("collect_voice_examples", "--collect-voice-examples"),
            ("collect_music_clips", "--collect-music-clips"), ("collect_sfx_clips", "--collect-sfx-clips")):
            if audio_enabled and audio_settings.get(key, False):
                args.append(flag)
        environment = os.environ.copy()
        environment["VIDEO_AUDIO_ANALYZER_PROJECT_ID"] = str(audio_settings.get("project_id") or asset["asset_id"])
        environment["VIDEO_AUDIO_ANALYZER_JOB_ID"] = job_id
        log_path = job_dir / f"direct-analyzer-{asset['asset_id']}.log"
        with log_path.open("ab") as log_handle:
            completed = subprocess.run(args, cwd=str(store.PROJECT_ROOT), env=environment,
                stdout=log_handle, stderr=subprocess.STDOUT, timeout=24 * 3600, check=False)
        digest = store.sha256_file(source)[:16]
        runs_root = store.analyzer_runs_root()
        candidates = list((runs_root / digest).glob("manifest.json")) if (runs_root / digest).is_dir() else []
        candidates += list(runs_root.glob(f"{digest}-rerun-*/manifest.json"))
        manifest_path = max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None
        if completed.returncode != 0 or manifest_path is None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-5000:]
            raise RuntimeError(f"Direct analyzer failed for {source.name} (exit {completed.returncode}); "
                f"manifest={'missing' if manifest_path is None else manifest_path}; log tail:\n{tail}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(analyzer_root / "src") not in sys.path:
            sys.path.insert(0, str(analyzer_root / "src"))
        from video_audio_analyzer.codex_director_review import apply_director_overlay
        manifest = apply_director_overlay(manifest, store.REPERTOIRE_ROOT / "indexes" / "director_reviews")
        run_id = str(manifest["run_id"])
        run_dir = store.analyzer_runs_root() / run_id
        from video_audio_analyzer.repertoire import promote_run
        promotion = promote_run(run_dir, store.REPERTOIRE_ROOT,
            str(audio_settings.get("project_id") or asset["asset_id"]), include_standard_media=False, job_id=job_id)
        analyzer_scenes = _analyzer_visual_scenes(manifest, run_dir)
        direct_scenes = []
        for scene in manifest.get("scenes", []):
            start = float(scene.get("start_time_sec", 0.0) or 0.0)
            end = float(scene.get("end_time_sec", start) or start)
            scene_id = str(scene.get("scene_id", ""))
            relative_clip = f"analyses/video_audio_analyzer/{run_id}/embeddings/{scene_id}.mp4"
            transcript_segments = [item for item in manifest.get("transcript", {}).get("segments", [])
                if float(item.get("start_time_sec", 0) or 0) < end and float(item.get("end_time_sec", 0) or 0) > start]
            timed_events = [item for item in manifest.get("audio_events", [])
                if float(item.get("start_time_sec", 0) or 0) < end and float(item.get("end_time_sec", 0) or 0) > start]
            transcript_text = " ".join(str(item.get("text", "")).strip() for item in transcript_segments if item.get("text"))
            direct_scenes.append({"scene_id": scene_id, "start_time_sec": start, "end_time_sec": end,
                "start_time_hms": _format_hms(start), "end_time_hms": _format_hms(end),
                "summary": str(scene.get("summary") or ""), "transcript": transcript_text,
                "transcript_segments": transcript_segments, "audio_events": timed_events,
                "cuts": scene.get("cuts", []),
                "clip_path": relative_clip if (run_dir / "embeddings" / f"{scene_id}.mp4").is_file() else None,
                "keyframes": [], "deltas": []})
        summary_text = str(manifest.get("internvideo3", {}).get("full_video_summary") or manifest.get("summary") or "")
        videos.append({"asset_id": asset["asset_id"], "title": asset.get("title") or source.name,
            "summary": {"detailed_video_summary": summary_text, "brief_video_summary": summary_text},
            "scenes": direct_scenes, "summary_model": manifest.get("internvideo3", {}).get("model"),
            "run_id": run_id})
        collection = manifest.get("media_collection", {})
        for collected in collection.get("assets", []):
            stored = str(collected.get("path", "")).replace("\\", "/")
            marker = f"runs/{run_id}/"
            collected["relative_path"] = stored.split(marker, 1)[1] if marker in stored else ""
            collected.pop("path", None)
        audio_runs.append({"asset_id": asset["asset_id"], "status": "completed", "run_id": run_id,
            "summary": summary_text, "summary_model": manifest.get("internvideo3", {}).get("model"),
            "statuses": manifest.get("statuses", {}), "scenes": analyzer_scenes,
            "audio": {"source_audio": "audio/source_audio.mka" if manifest.get("audio", {}).get("source_audio") else None,
                "preview_mp3": "audio/preview.mp3" if manifest.get("audio", {}).get("preview_mp3") else None,
                "analysis_wav": "audio/analysis.wav" if manifest.get("audio", {}).get("analysis_wav") else None},
            "audio_events": manifest.get("audio_events", []), "transcript": manifest.get("transcript", {}),
            "diarization": manifest.get("diarization", {}), "voices": manifest.get("voices", {}),
            "music_features": manifest.get("music_features", {}), "media_collection": collection, "promotion": promotion})
        if job_id not in asset.setdefault("analysis_ids", []):
            asset["analysis_ids"].append(job_id)
            store._atomic_json(store.asset_manifest_path(asset["asset_id"]), asset)
        event("analysis", job_id, "video_audio_analyzer", "completed",
            f"Direct-video summary and {len(direct_scenes)} timestamped clip(s) are ready.",
            12 + int(80 * index / max(1, len(assets))), {"asset_id": asset["asset_id"], "run_id": run_id,
                "audio_events": len(manifest.get("audio_events", [])), "summary_model": manifest.get("internvideo3", {}).get("model")})
    return {"videos": videos, "audio_analysis": audio_runs, "errors": [], "skipped_videos": [],
        "primary_backend": "video_audio_analyzer", "summary_model": "InternVideo3"}


def _format_hms(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _frame_card(frame: Any) -> dict[str, Any]:
    """Compact director-facing frame metadata; verbose analysis remains in artifacts."""
    signals = getattr(frame, "support_signals", {}) or {}
    detections = getattr(frame, "object_detections", []) or []
    return {
        "frame_id": frame.frame_id,
        "timestamp_sec": frame.timestamp_sec,
        "summary": (frame.concise_summary or frame.detailed_description or "")[:500],
        "subjects": [item.label for item in detections],
        "objects": [item.to_dict() for item in detections],
        "action_state": (frame.concise_summary or ""),
        "composition": "",
        "camera": "",
        "lighting": "",
        "palette": frame.dominant_colors,
        "text": frame.ocr_text,
        "reference_uses": ["composition", "subject appearance", "lighting"],
        "replaceable_parts": ["subjects", "background", "style"],
        "confidence": 0.75 if frame.detailed_description else 0.0,
        "uncertainties": frame.warnings,
        "evidence": {"florence_caption": frame.florence_caption, "support_signals": signals},
    }


def run_analysis(job_id: str, request: dict[str, Any]) -> dict[str, Any]:
    settings = request.get("settings", {})
    backend = str(settings.get("analysis_backend") or os.environ.get("VIDEO_REPERTOIRE_ANALYSIS_BACKEND", "video_audio_analyzer"))
    if backend == "video_audio_analyzer":
        assets = [store.get_asset(asset_id) for asset_id in request.get("asset_ids", [])]
        if not assets:
            raise ValueError("Select at least one video asset")
        job_dir = store.job_path("analysis", job_id).parent
        job_dir.mkdir(parents=True, exist_ok=True)
        # Direct analyzer stages launch their own CUDA containers, outside
        # ComfyUI. Share the same cross-process admission lock as every
        # Story Builder ComfyUI render so an analysis cannot overlap a video,
        # image, or audio generation job and consume the GB10 unified-memory
        # pool at the same time. This is backend-side queueing: no second
        # prompt is placed in ComfyUI's queue while another Story Builder GPU
        # job owns the lease.
        event("analysis", job_id, "gpu_admission", "waiting",
            "Waiting for the exclusive Story Builder GPU slot; analyzer stages will run one at a time.", 10)
        with gpu_workload_guard(comfy_url=os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008")):
            with _GpuMemorySampler() as gpu_sampler:
                result = _run_direct_analyzer(job_id, assets, settings, job_dir)
        result["gpu_usage"] = gpu_sampler.report()
        return result
    if backend != "legacy":
        raise ValueError(f"Unsupported video analysis backend: {backend}")
    from video_scene_summarizer.config.settings import load_settings
    from video_scene_summarizer.graph.workflow import run_analysis_stage

    assets = [store.get_asset(asset_id) for asset_id in request.get("asset_ids", [])]
    if not assets:
        raise ValueError("Select at least one video asset")
    job_dir = store.job_path("analysis", job_id).parent
    input_dir = job_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    filename_to_asset: dict[str, dict[str, Any]] = {}
    for asset in assets:
        source = store.safe_path(Path(asset["path"]), store.REPERTOIRE_ROOT, store.LEGACY_VIDEO_ROOT)
        target = input_dir / f"{asset['asset_id']}_{source.name}"
        if not target.exists():
            try:
                target.symlink_to(source)
            except OSError:
                shutil.copy2(source, target)
        filename_to_asset[target.stem] = asset
    output_root = store.REPERTOIRE_ROOT / "analyses" / job_id
    config = load_settings(store.VIDEO_SUMMARISER_ROOT)
    stage_progress = {"model_setup": 8, "audio_extraction": 16, "transcription": 28, "scene_detection": 40, "scene_preview": 48, "keyframe_analysis": 62, "frame_delta": 70, "scene_analysis": 78, "cross_scene_analysis": 84, "video_summary": 90, "report_writing": 94}

    def callback(item: dict[str, Any]) -> None:
        stage = str(item.get("stage", "analysis"))
        event("analysis", job_id, stage, str(item.get("status", "running")), str(item.get("message", stage)), stage_progress.get(stage, 50), item.get("payload") if isinstance(item.get("payload"), dict) else {})

    with gpu_workload_guard(comfy_url=os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008")):
        result = run_analysis_stage(
            config=config, input_dir=input_dir, output_root=output_root, keep_downloaded_videos=True,
            use_transcript_fusion=bool(settings.get("transcript_fusion", True)), reuse_cache=bool(settings.get("reuse_cache", True)),
            skip_existing=bool(settings.get("skip_existing", False)), use_frame_shaving=bool(settings.get("frame_shaving", False)),
            extract_fps=float(settings.get("extract_fps", config.extract_fps or config.analysis_fps)),
            use_scene_compaction=bool(settings.get("scene_compaction", False)), delete_frame_images=bool(settings.get("delete_frames", False)),
            event_callback=callback,
        )
    videos = []
    visual_detailer_enabled = bool(settings.get("visual_detailer", False))
    for record in result.get("processed_videos", []):
        record_name = Path(record.video_path).name if record.video_path else ""
        matching = next((asset for asset in assets if record_name.startswith(f"{asset['asset_id']}_")), None)
        if matching is None and len(assets) == 1:
            matching = assets[0]
        source = Path(matching["path"]) if matching else Path(record.video_path)
        scenes = []
        for scene in record.metadata.get("_scenes", []):
            clip = store.REPERTOIRE_ROOT / "clips" / (matching["asset_id"] if matching else record.sanitized_name) / f"{job_id}_{scene.scene_id}.mp4"
            try:
                _make_clip(source, clip, scene.start_time_sec, scene.end_time_sec)
                clip_path = str(clip.relative_to(store.REPERTOIRE_ROOT))
            except Exception:
                clip_path = ""
            scene_payload = {
                "scene_id": scene.scene_id, "scene_number": scene.scene_number, "start_time_sec": scene.start_time_sec,
                "end_time_sec": scene.end_time_sec, "start_time_hms": scene.start_time_hms, "end_time_hms": scene.end_time_hms,
                "summary": scene.scene_compiled_text or scene.scene_story_text, "transcript": scene.transcript_text,
                "keywords": scene.keywords, "confidence_notes": scene.confidence_notes, "clip_path": clip_path,
                "action_segment": {"start_time_sec": scene.start_time_sec, "end_time_sec": scene.end_time_sec, "clip_path": clip_path, "label": scene.scene_id},
                "keyframes": [{"frame_id": frame.frame_id, "timestamp_sec": frame.timestamp_sec, "description": frame.detailed_description,
                               "summary": frame.concise_summary, "frame_card": _frame_card(frame), "path": _relative_artifact(Path(frame.frame_path))} for frame in scene.keyframe_analyses],
                "deltas": [delta.to_dict() for delta in scene.frame_deltas],
            }
            if visual_detailer_enabled:
                evidence: list[dict[str, Any]] = []
                for frame in scene.keyframe_analyses:
                    try:
                        from story_builder.services.image_detailer import analyze_image
                        frame_result = analyze_image(Path(frame.frame_path), mode="quick")
                        evidence.append({"frame_id": frame.frame_id, "timestamp_sec": frame.timestamp_sec, "frame_card": frame_result.get("frame_card"), "specialist_evidence": frame_result.get("specialist_evidence", {}), "analysis": frame_result.get("analysis", {})})
                    except Exception as exc:
                        evidence.append({"frame_id": frame.frame_id, "timestamp_sec": frame.timestamp_sec, "error": str(exc)})
                evidence_path = output_root / "visual_evidence" / f"{scene.scene_id}.json"
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
                scene_payload["visual_evidence_path"] = str(evidence_path.relative_to(store.REPERTOIRE_ROOT))
                scene_payload["visual_evidence"] = evidence
            scenes.append(scene_payload)
        summary = record.metadata.get("_final_summary")
        videos.append({
            "asset_id": matching.get("asset_id") if matching else None, "title": record.title,
            "summary": summary.to_dict() if summary else None, "scenes": scenes,
        })
        if matching:
            matching.setdefault("analysis_ids", [])
            if job_id not in matching["analysis_ids"]:
                matching["analysis_ids"].append(job_id)
                store._atomic_json(store.asset_manifest_path(matching["asset_id"]), matching)
    audio_runs: list[dict[str, Any]] = []
    audio_settings = settings.get("audio_analyzer", {}) if isinstance(settings.get("audio_analyzer", {}), dict) else {}
    if settings.get("audio_analyzer_enabled", False):
        analyzer_root = store.PROJECT_ROOT / "video_audio_analyzer"
        script = analyzer_root / "run_peav_worker.sh"
        if not script.is_file():
            audio_runs.append({"status": "unavailable", "reason": f"Analyzer launcher is missing: {script}"})
        else:
            for index, asset in enumerate(assets, start=1):
                source = store.safe_path(Path(asset["path"]), store.REPERTOIRE_ROOT, store.LEGACY_VIDEO_ROOT)
                event("analysis", job_id, "audio_video_analyzer", "running",
                    f"Running upgraded audio/semantic analysis for video {index} of {len(assets)}.", 94,
                    {"asset_id": asset["asset_id"], "title": asset.get("title", source.name)})
                args = ["bash", str(script), str(source), "--extract-fps", str(audio_settings.get("extract_fps", settings.get("extract_fps", 4))),
                    "--run-demucs", str(audio_settings.get("run_demucs", "AUTO")),
                    "--frame-change-threshold", str(audio_settings.get("frame_change_threshold", 0.08)),
                    "--cut-boundary-threshold", str(settings.get("cut_boundary_threshold", 0.18)),
                    "--min-cut-seconds", str(settings.get("min_cut_seconds", 0.5)),
                    "--project-id", str(audio_settings.get("project_id") or asset["asset_id"])]
                args.append("--extract-cut-clips" if settings.get("extract_cut_clips", True) else "--no-extract-cut-clips")
                args.append("--adaptive-sampling" if audio_settings.get("adaptive_sampling", True) else "--no-adaptive-sampling")
                args.append("--preserve-scene-anchors" if audio_settings.get("preserve_scene_anchors", True) else "--no-preserve-scene-anchors")
                if audio_settings.get("keep_intermediate_samples", False):
                    args.append("--keep-intermediate-samples")
                for key, flag in (("detect_speech", "--detect-speech"), ("detect_music", "--detect-music"),
                    ("detect_sfx", "--detect-sfx"), ("create_audio_embeddings", "--create-audio-embeddings"),
                    ("create_av_embeddings", "--create-av-embeddings"), ("diarize_speakers", "--diarize-speakers"),
                    ("extract_source_audio", "--extract-source-audio"), ("extract_preview_mp3", "--extract-mp3")):
                    args.append(flag if audio_settings.get(key, True) else "--no-" + flag[2:])
                for key, flag in (("collect_voice_examples", "--collect-voice-examples"),
                    ("collect_music_clips", "--collect-music-clips"), ("collect_sfx_clips", "--collect-sfx-clips")):
                    if audio_settings.get(key, False):
                        args.append(flag)
                log_path = job_dir / f"audio-analyzer-{asset['asset_id']}.log"
                environment = os.environ.copy()
                environment["VIDEO_AUDIO_ANALYZER_PROJECT_ID"] = str(audio_settings.get("project_id") or asset["asset_id"])
                environment["VIDEO_AUDIO_ANALYZER_JOB_ID"] = job_id
                completed = None
                try:
                    with log_path.open("ab") as log_handle:
                        with gpu_workload_guard(comfy_url=os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008")):
                            completed = subprocess.run(args, cwd=str(store.PROJECT_ROOT.parent), env=environment,
                                stdout=log_handle, stderr=subprocess.STDOUT, timeout=24 * 3600, check=False)
                    digest = store.sha256_file(source)[:16]
                    run_root = store.analyzer_runs_root()
                    manifests = list((run_root / digest).glob("manifest.json")) if (run_root / digest).is_dir() else []
                    manifests += sorted(run_root.glob(f"{digest}-rerun-*/manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
                    manifest_path = max(manifests, key=lambda item: item.stat().st_mtime) if manifests else None
                    if completed.returncode != 0 or manifest_path is None:
                        tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                        audio_runs.append({"asset_id": asset["asset_id"], "status": "failed",
                            "reason": f"Analyzer exited {completed.returncode}; manifest was not produced." if not manifest_path else f"Analyzer exited {completed.returncode}.",
                            "log_tail": tail})
                        continue
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    from video_audio_analyzer.codex_director_review import apply_director_overlay
                    manifest = apply_director_overlay(manifest, store.REPERTOIRE_ROOT / "indexes" / "director_reviews")
                    run_dir = store.analyzer_runs_root() / str(manifest["run_id"])
                    if not run_dir.is_dir():
                        raise FileNotFoundError(f"Analyzer manifest points to a missing run directory: {run_dir}")
                    analyzer_scenes = _analyzer_visual_scenes(manifest, run_dir)
                    if str(analyzer_root / "src") not in sys.path:
                        sys.path.insert(0, str(analyzer_root / "src"))
                    from video_audio_analyzer.repertoire import promote_run
                    promotion = promote_run(run_dir, store.REPERTOIRE_ROOT,
                        str(audio_settings.get("project_id") or asset["asset_id"]), include_standard_media=False,
                        job_id=job_id)
                    collection = manifest.get("media_collection", {})
                    for collected_asset in collection.get("assets", []):
                        stored = str(collected_asset.get("path", "")).replace("\\", "/")
                        marker = f"runs/{manifest['run_id']}/"
                        collected_asset["relative_path"] = stored.split(marker, 1)[1] if marker in stored else ""
                        collected_asset.pop("path", None)
                    audio_runs.append({"asset_id": asset["asset_id"], "status": "completed", "run_id": manifest["run_id"],
                        "summary": manifest.get("summary"), "statuses": manifest.get("statuses", {}),
                        "scenes": analyzer_scenes,
                        "audio": {"source_audio": "audio/source_audio.mka" if manifest.get("audio", {}).get("source_audio") else None,
                            "preview_mp3": "audio/preview.mp3" if manifest.get("audio", {}).get("preview_mp3") else None,
                            "analysis_wav": "audio/analysis.wav" if manifest.get("audio", {}).get("analysis_wav") else None},
                        "audio_events": manifest.get("audio_events", []), "transcript": manifest.get("transcript", {}),
                        "diarization": manifest.get("diarization", {}), "voices": manifest.get("voices", {}),
                        "music_features": manifest.get("music_features", {}),
                        "media_collection": collection, "promotion": promotion})
                    event("analysis", job_id, "audio_video_analyzer", "completed",
                        f"Upgraded analyzer finished: {len(manifest.get('audio_events', []))} timestamped audio event(s).", 97,
                        {"asset_id": asset["asset_id"], "run_id": manifest["run_id"], "stages": manifest.get("statuses", {})})
                except Exception as exc:
                    audio_runs.append({"asset_id": asset["asset_id"], "status": "failed", "reason": str(exc),
                        "log_path": str(log_path)})
    return {"videos": videos, "audio_analysis": audio_runs, "errors": result.get("errors", []), "skipped_videos": [str(item) for item in result.get("skipped_videos", [])]}


def _relative_artifact(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(store.REPERTOIRE_ROOT.resolve()))
    except ValueError:
        return ""


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    kind, job_id = sys.argv[1:]
    try:
        job = store.read_job(kind, job_id)
        save_job(kind, job_id, status="running", stage="running", message="Worker is running.")
        result = run_youtube(job_id, job["request"]) if kind == "youtube" else run_analysis(job_id, job["request"])
        save_job(kind, job_id, status="completed", stage="completed", message="Job completed.", progress=100, result=result, error=None)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        save_job(kind, job_id, status="failed", stage="failed", message=str(exc), error=f"{exc}\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
