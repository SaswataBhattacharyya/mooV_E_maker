"""Clip-first InternVideo3 summarization and bounded text-context refinement.

Run only in the dedicated analyzer caption container. Video is supplied by
path to the model's video processor; intermediate scene clips are deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .internvideo3_captioner import InternVideo3Captioner, MODEL_ID, decode_video_preflight


MODEL_REVISION = "c4602918b65225650d152db2850fe34e01d21fcd"


def _overlap(row: dict[str, Any], start: float, end: float) -> bool:
    return float(row.get("start_time_sec", 0) or 0) < end and float(row.get("end_time_sec", row.get("start_time_sec", 0)) or 0) > start


def _timed_context(manifest: dict[str, Any], start: float, end: float) -> dict[str, list[dict[str, Any]]]:
    transcript = manifest.get("transcript", {})
    segments = transcript.get("segments", []) if isinstance(transcript, dict) else []
    cues = transcript.get("cues", []) if isinstance(transcript, dict) else []
    if not segments:
        segments = cues
    dialogue = []
    for item in segments:
        if _overlap(item, start, end) and str(item.get("text", "")).strip():
            dialogue.append({
                "start_time_sec": item.get("start_time_sec", item.get("start")),
                "end_time_sec": item.get("end_time_sec", item.get("end")),
                "text": str(item.get("text", "")).strip(),
                "language": item.get("language") or transcript.get("language"),
                "source": item.get("source") or transcript.get("source"),
                "speaker_id": item.get("speaker_id") or item.get("speaker"),
            })
    events = []
    for item in manifest.get("audio_events", []):
        if _overlap(item, start, end):
            events.append({key: item.get(key) for key in (
                "event_id", "start_time_sec", "end_time_sec", "label", "event_type", "confidence", "source", "classification_status"
            ) if item.get(key) is not None})
    for item in manifest.get("diarization", {}).get("segments", []):
        if _overlap(item, start, end) and item.get("speaker_id"):
            events.append({"event_type": "speaker", "start_time_sec": item.get("start_time_sec"),
                "end_time_sec": item.get("end_time_sec"), "speaker_id": item.get("speaker_id"),
                "confidence": item.get("confidence"), "source": "nemo_diarization"})
    return {"transcript": dialogue, "audio_events": events}


def _format_context(context: dict[str, list[dict[str, Any]]], *, limit: int = 7000) -> str:
    encoded = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    return encoded if len(encoded) <= limit else encoded[:limit] + "… [context truncated; source timestamps retained in manifest]"


def _cut(source: Path, destination: Path, start: float, end: float) -> None:
    if end <= start:
        raise ValueError(f"Invalid clip interval {start}–{end}")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-i", str(source),
        "-t", f"{end-start:.3f}", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-movflags", "+faststart", str(destination),
    ], check=True, capture_output=True, text=True)


def preflight(model_dir: Path | None = None) -> dict[str, Any]:
    model_dir = (model_dir or Path(os.environ.get(
        "VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_PATH", "/models/internvideo3-8b-instruct"
    ))).resolve()
    try:
        import platform
        import torch
        import transformers
        import importlib.util
        cuda = torch.cuda.is_available()
        gpu = torch.cuda.get_device_properties(0) if cuda else None
        config = json.loads((model_dir / "config.json").read_text(encoding="utf-8")) if (model_dir / "config.json").is_file() else {}
        index_path = model_dir / "model.safetensors.index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
        shards = sorted(set(index.get("weight_map", {}).values()))
        missing = [name for name in shards if not (model_dir / name).is_file()]
        custom_files = [model_dir / name for name in (
            "configuration_internvideo3.py", "modeling_internvideo3.py", "modeling_internvideo3_xslinear.py",
            "processing_internvideo3.py", "video_processing_internvideo3.py",
        )]
        code_hash = hashlib.sha256("".join(
            f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}\n" for path in custom_files if path.is_file()
        ).encode()).hexdigest()
        try:
            import torchvision
            torchvision_version = torchvision.__version__
            video_backend = "torchvision/Transformers video_utils"
        except Exception as exc:
            torchvision_version = None
            video_backend = f"unavailable: {type(exc).__name__}: {exc}"
        accelerate_ready = importlib.util.find_spec("accelerate") is not None
        ready = bool(cuda and accelerate_ready and config.get("model_type") == "internvideo3" and shards and not missing and all(path.is_file() for path in custom_files))
        return {
            "component": "internvideo3-8b-caption-worker", "status": "preflight_ready" if ready else "not_ready",
            "model": MODEL_ID, "revision": os.environ.get("VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_REVISION", MODEL_REVISION),
            "model_code_sha256": code_hash, "model_license": "Apache-2.0 (snapshot card metadata; verify upstream terms separately)",
            "python": platform.python_version(), "architecture": platform.machine(),
            "torch": torch.__version__, "transformers": transformers.__version__,
            "accelerate_available": accelerate_ready,
            "cuda_available": cuda, "gpu_name": gpu.name if gpu else None,
            "gpu_total_memory_bytes": gpu.total_memory if gpu else None,
            "gpu_bfloat16": bool(cuda and torch.cuda.is_bf16_supported()),
            "video_backend": video_backend, "torchvision": torchvision_version,
            "checkpoint": str(model_dir), "checkpoint_config_model_type": config.get("model_type"),
            "weight_shards_expected": len(shards), "weight_shards_missing": missing,
            "custom_model_code_files_present": all(path.is_file() for path in custom_files),
            "network_downloads_enabled": False,
            "reason": None if ready else ("CUDA unavailable" if not cuda else "Accelerate missing" if not accelerate_ready else "checkpoint or required custom code incomplete"),
        }
    except Exception as exc:
        return {"component": "internvideo3-8b-caption-worker", "status": "preflight_error",
            "checkpoint": str(model_dir), "reason": f"{type(exc).__name__}: {exc}"}


def _draft_prompt(clip: dict[str, Any], context: dict[str, list[dict[str, Any]]]) -> str:
    return f"""You are a careful film editor creating a concise, searchable clip record. Analyze the attached video clip directly.
Clip interval in source: {clip['start_time_sec']:.3f}–{clip['end_time_sec']:.3f} seconds.
Describe only visible evidence: the action/progression, people or objects that matter, spatial relations, camera/framing or movement when apparent, and how the moment begins and ends. Do not merely list static objects. Do not infer identity, intent, sound, or events that are not supported. If uncertain, say so briefly. Return a compact factual paragraph (2–5 sentences), no headings, no chain-of-thought.
Time-aligned audio/transcript evidence for later fusion (do not claim you heard it): {_format_context(context)}"""


def _whole_prompt(source: dict[str, Any], clips: list[dict[str, Any]], transcript: dict[str, Any], events: list[dict[str, Any]]) -> str:
    timeline = [{"clip_id": c["clip_id"], "start_time_sec": c["start_time_sec"], "end_time_sec": c["end_time_sec"], "draft": c["draft_summary"]} for c in clips]
    compact = {"transcript": transcript, "audio_events": events}
    evidence = json.dumps({"clip_timeline": timeline, "timed_audio_and_transcript": compact}, ensure_ascii=False, separators=(",", ":"))
    return f"""Write the coherent overall summary of this complete video: {source.get('file_name', 'video')} ({source.get('duration_sec', 0):.2f} seconds).
Use the chronological clip drafts and time-aligned transcript/audio-event evidence below. Explain the progression and the relationship between major moments; distinguish observed visual actions from supplied transcript/audio labels. Never invent events, speaker names, motives, or off-screen action. Preserve chronology, mention material uncertainty, and keep this useful as searchable production-reference metadata (one compact paragraph, about 4–8 sentences). Do not output headings, JSON, or chain-of-thought.
EVIDENCE: {evidence[:24000]}"""


def _refine_prompt(full_summary: str, clip: dict[str, Any], neighbors: list[dict[str, Any]], context: dict[str, list[dict[str, Any]]]) -> str:
    neighbor_context = [{"start_time_sec": n["start_time_sec"], "end_time_sec": n["end_time_sec"], "draft": n["draft_summary"]} for n in neighbors]
    return f"""Refine this one clip's searchable summary in the context of its full video. The full summary is context, not permission to add details absent from the local clip or its time-aligned evidence.
Full-video context: {full_summary}
Target clip {clip['clip_id']} ({clip['start_time_sec']:.3f}–{clip['end_time_sec']:.3f}s), initial direct-video summary: {clip['draft_summary']}
Adjacent clip context: {json.dumps(neighbor_context, ensure_ascii=False)}
Target transcript/audio evidence: {_format_context(context)}
Return 2–5 factual sentences: preserve target-clip progression, add only useful continuity/context, retain source/confidence distinctions, and mark uncertainty. No headings, invented identities, or chain-of-thought."""


def summarize_manifest(manifest_path: Path, source_video: Path, *, sample_fps: float = 1.0) -> dict[str, Any]:
    manifest_path, source_video = manifest_path.resolve(), source_video.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not source_video.is_file():
        raise FileNotFoundError(source_video)
    scenes = manifest.get("scenes", [])
    if not scenes:
        raise ValueError("No timestamped scenes/clips available for direct-video summarization")
    run_dir = manifest_path.parent
    captioner = InternVideo3Captioner(sample_fps=sample_fps)
    started = time.monotonic()
    clip_records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="internvideo3-clips-") as temp_name:
        temp_dir = Path(temp_name)
        for index, scene in enumerate(scenes):
            start = float(scene.get("start_time_sec", 0.0))
            end = float(scene.get("end_time_sec", start))
            clip_id = str(scene.get("clip_id") or scene.get("scene_id") or f"clip_{index+1:04d}")
            clip_path = temp_dir / f"{index:04d}.mp4"
            context = _timed_context(manifest, start, end)
            _cut(source_video, clip_path, start, end)
            output = captioner.summarize_video(clip_path, _draft_prompt({"start_time_sec": start, "end_time_sec": end}, context))
            clip_records.append({"clip_id": clip_id, "scene_id": scene.get("scene_id"),
                "start_time_sec": start, "end_time_sec": end, "draft_summary": output["text"],
                "summary": None, "transcript": context["transcript"], "audio_events": context["audio_events"],
                "direct_video_inference": {"input_mode": output["input_mode"], "sample_fps": output["sample_fps"], "seconds": output["seconds"]}})

    all_transcript = [row for clip in clip_records for row in clip["transcript"]]
    all_events = [row for clip in clip_records for row in clip["audio_events"]]
    dedup_transcript = list({(str(x.get("start_time_sec")), str(x.get("end_time_sec")), str(x.get("text"))): x for x in all_transcript}.values())
    dedup_events = list({(str(x.get("event_id", x.get("speaker_id"))), str(x.get("start_time_sec")), str(x.get("end_time_sec")), str(x.get("label"))): x for x in all_events}.values())
    whole = captioner.synthesize_text(_whole_prompt(manifest.get("source", {}), clip_records, dedup_transcript, dedup_events), max_new_tokens=480)
    full_summary = whole["text"]
    refine_started = time.monotonic()
    for index, clip in enumerate(clip_records):
        start, end = clip["start_time_sec"], clip["end_time_sec"]
        context = {"transcript": clip["transcript"], "audio_events": clip["audio_events"]}
        neighbors = clip_records[max(0, index - 1):index] + clip_records[index + 1:index + 2]
        refined = captioner.synthesize_text(_refine_prompt(full_summary, clip, neighbors, context), max_new_tokens=240)
        clip["summary"] = refined["text"]
        clip["refinement_seconds"] = refined["seconds"]
        scene = scenes[index]
        scene["clip_id"] = clip["clip_id"]
        scene["summary"] = clip["summary"]
        scene["summary_source"] = {"model": MODEL_ID, "phase": "single_context_refinement", "evidence_start_sec": start, "evidence_end_sec": end}

    result = {
        "status": "completed", "model": MODEL_ID, "revision": os.environ.get("VIDEO_AUDIO_ANALYZER_INTERNVIDEO3_REVISION", MODEL_REVISION),
        "processor": "pinned_local_snapshot", "direct_video_input": True, "sample_fps": sample_fps,
        "sequence": ["direct_video_clip_drafts", "chronological_full_video_synthesis", "single_context_refinement_pass"],
        "full_video_summary": full_summary, "clips": clip_records,
        "timings": {"model_load_seconds": getattr(captioner, "model_load_seconds", None),
            "full_pipeline_seconds": round(time.monotonic() - started, 3),
            "wall_seconds_including_model_load": round(time.monotonic() - started + (getattr(captioner, "model_load_seconds", 0) or 0), 3),
            "full_video_synthesis_seconds": whole["seconds"], "refinement_pass_seconds": round(time.monotonic() - refine_started, 3)},
        "reasoning_traces_stored": False,
    }
    manifest["internvideo3"] = result
    manifest["summary_baseline"] = manifest.get("summary")
    manifest["summary"] = full_summary
    manifest.setdefault("pipeline", {})["summary_backend"] = MODEL_ID
    manifest.setdefault("statuses", {})["internvideo3_summary"] = "completed"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.txt").write_text(full_summary + "\n", encoding="utf-8")
    (run_dir / "internvideo3_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def attach_peav_text_embeddings(manifest_path: Path) -> dict[str, Any]:
    """Create separate PE-AV text vectors in the PE-AV runtime, after captioning."""
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    from .peav_adapter import configured_adapter
    adapter = configured_adapter()
    items: list[tuple[dict[str, Any] | None, str, str]] = []
    result = manifest.get("internvideo3", {})
    for clip in result.get("clips", []):
        scene = next((x for x in manifest.get("scenes", []) if x.get("scene_id") == clip.get("scene_id")), None)
        if scene is not None:
            text = " ".join([str(clip.get("summary", "")),
                "transcript: " + " ".join(str(x.get("text", "")) for x in clip.get("transcript", [])),
                "audio events: " + ", ".join(str(x.get("label", x.get("speaker_id", ""))) for x in clip.get("audio_events", []))]).strip()
            items.append((scene, text, "clip_refined_text"))
    summary_text = str(result.get("full_video_summary", "")).strip()
    if summary_text:
        items.append((None, summary_text, "full_video_summary"))
    embedded = 0
    full_vector: list[float] | None = None
    for scene, text, kind in items:
        vectors = adapter.embed(text=text)
        vector = (vectors.get("text_audio_video_embeds") or vectors.get("text_video_embeds") or vectors.get("visual_text_embeds") or [[None]])[0]
        if not vector or vector[0] is None:
            raise RuntimeError(f"PE-AV produced no text vector for {kind}")
        values = [float(value) for value in vector]
        if scene is not None:
            scene.setdefault("embeddings", {})["text_summary"] = values
            scene["embeddings"].setdefault("providers", {})["text_summary"] = {
                "model": "facebook/pe-av-base", "dimension": len(values), "record_kind": kind,
            }
        else:
            full_vector = values
        embedded += 1
    manifest.setdefault("embeddings", {}).setdefault("pe_av", {})["text_summary"] = {
        "status": "completed" if embedded else "unavailable", "dimension": adapter.dimension,
        "model": "facebook/pe-av-base", "clip_text_records": max(0, embedded - (1 if full_vector else 0)),
        "full_video_summary_record": full_vector is not None,
    }
    if full_vector is not None:
        manifest["internvideo3"]["full_video_summary_embedding"] = {
            "model": "facebook/pe-av-base", "dimension": len(full_vector), "vector": full_vector,
        }
    manifest.setdefault("statuses", {})["pe_av_summary_text_embeddings"] = "completed" if embedded else "unavailable"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest["embeddings"]["pe_av"]["text_summary"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize timestamped clips directly with InternVideo3")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--fps", default=1.0, type=float)
    parser.add_argument("--embed-text-only", action="store_true", help="Use in the PE-AV image after the caption worker exits")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--decode-only", action="store_true")
    args = parser.parse_args()
    if args.preflight_only:
        output = preflight()
    elif args.decode_only:
        if args.source is None:
            parser.error("--source is required with --decode-only")
        output = decode_video_preflight(args.source, sample_fps=args.fps)
    elif args.embed_text_only:
        if args.manifest is None:
            parser.error("--manifest is required with --embed-text-only")
        from .peav_text_stage import embed_manifest_text
        output = embed_manifest_text(args.manifest)
    else:
        if args.source is None or args.manifest is None:
            parser.error("--manifest and --source are required for summarization")
        output = summarize_manifest(args.manifest, args.source, sample_fps=args.fps)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
