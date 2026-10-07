from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .evidence import analyze_frame
from .music_features import analyze_music
from .subtitles import extract_embedded
from .voice_embeddings import extract_voice_examples
from .retrieval import build_index


@dataclass
class AnalyzerOptions:
    extract_fps: float = 4.0
    scene_threshold: float = 0.26
    min_scene_seconds: float = 0.5
    cut_boundary_threshold: float = 0.18
    min_cut_seconds: float = 0.5
    extract_cut_clips: bool = True
    frame_change_threshold: float = 0.08
    extract_source_audio: bool = True
    extract_preview_mp3: bool = True
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
    persist_selected_frames: bool = True
    analyze_frame_evidence: bool = True


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _probe(video: Path) -> dict[str, Any]:
    output = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)])
    return json.loads(output.stdout)


def _metadata(video: Path, probe: dict[str, Any]) -> dict[str, Any]:
    stream = next((item for item in probe.get("streams", []) if item.get("codec_type") == "video"), {})
    rate = str(stream.get("r_frame_rate", "0/1")).split("/")
    fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1] or 0) else 0.0
    return {
        "video_id": hashlib.sha256(video.read_bytes()).hexdigest()[:16],
        "file_name": video.name,
        "duration_sec": float(probe.get("format", {}).get("duration") or 0.0),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "source_fps": fps,
        "audio_streams": sum(1 for item in probe.get("streams", []) if item.get("codec_type") == "audio"),
    }


def _extract_audio(video: Path, audio_dir: Path, options: AnalyzerOptions) -> dict[str, Any]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"source_audio": None, "analysis_wav": None, "preview_mp3": None, "warnings": []}
    source = audio_dir / "source_audio.mka"
    if options.extract_source_audio:
        try:
            _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-c:a", "copy", str(source)])
            result["source_audio"] = str(source)
        except Exception as exc:
            result["warnings"].append(f"source bitstream copy unavailable: {exc}")
    wav = audio_dir / "analysis.wav"
    mp3 = audio_dir / "preview.mp3"
    needs_analysis = any((options.detect_speech, options.detect_music, options.detect_sfx,
        options.create_audio_embeddings, options.create_av_embeddings, options.diarize_speakers,
        options.collect_voice_examples, options.collect_music_clips, options.collect_sfx_clips,
        options.run_demucs.lower() != "off"))
    if needs_analysis:
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
    if options.extract_preview_mp3:
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-c:a", "libmp3lame", "-q:a", "4", str(mp3)])
    result["analysis_wav"] = str(wav) if needs_analysis else None
    result["preview_mp3"] = str(mp3) if options.extract_preview_mp3 else None
    return result


def _frame_pair_change(previous: Any, current: Any) -> tuple[float, float]:
    """Return motion-compensated visual change and estimated global camera motion.

    ECC aligns the current low-resolution grayscale sample to the previous one.
    A coherent pan/tilt therefore contributes less to the shaving score than
    local subject/action change, while a hard cut or an unreliable alignment
    falls back to the unregistered pixel difference.
    """
    raw = float(cv2.absdiff(previous, current).mean() / 255.0)
    height, width = previous.shape[:2]
    warp = np.eye(2, 3, dtype="float32")
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, 1e-4)
    try:
        correlation, warp = cv2.findTransformECC(previous, current, warp, cv2.MOTION_AFFINE, criteria)
        linear = warp[:, :2]
        determinant = float(cv2.determinant(linear))
        if correlation < 0.65 or not 0.65 <= determinant <= 1.45:
            return raw, 0.0
        aligned = cv2.warpAffine(current, warp, (width, height), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                 borderMode=cv2.BORDER_REPLICATE)
        residual = float(cv2.absdiff(previous, aligned).mean() / 255.0)
        tx, ty = float(warp[0, 2]), float(warp[1, 2])
        translation = math.hypot(tx, ty) / max(1.0, math.hypot(width, height))
        rotation = abs(math.atan2(float(warp[1, 0]), float(warp[0, 0]))) / math.pi
        scale_change = min(1.0, abs(math.sqrt(max(determinant, 0.0)) - 1.0))
        camera_motion = min(1.0, translation + 0.5 * rotation + 0.5 * scale_change)
        return residual, camera_motion
    except (cv2.error, ValueError, TypeError):
        return raw, 0.0


def _extract_samples_ffmpeg(video: Path, out_dir: Path, fps: float) -> list[tuple[Any, ...]]:
    """Software-decode frames through FFmpeg for codecs OpenCV cannot decode."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "%06d.jpg"
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", f"fps={max(fps, 0.1)}", "-q:v", "3", str(pattern),
    ])
    samples: list[tuple[Any, ...]] = []
    previous: Any = None
    for index, path in enumerate(sorted(out_dir.glob("*.jpg"))):
        frame = cv2.imread(str(path))
        if frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))
        change, camera_motion = (0.0, 0.0) if previous is None else _frame_pair_change(previous, small)
        previous = small
        samples.append((index / max(fps, 0.1), frame, change, camera_motion))
    return samples


def _select_scene_frames(selected: list[tuple[Any, ...]], options: AnalyzerOptions) -> list[tuple[Any, ...]]:
    if not selected:
        return []
    if options.adaptive_sampling:
        # Keep scene anchors and only sufficiently changed samples, with a
        # minimum temporal gap so small pixel noise cannot flood a scene.
        picks = [item for item in selected
                 if ((options.preserve_scene_anchors and (item is selected[0] or item is selected[-1]))
                     or (item[2] >= options.frame_change_threshold
                         and item[0] - selected[0][0] >= 0.75
                         and selected[-1][0] - item[0] >= 0.75))]
        if options.preserve_scene_anchors:
            picks = [selected[0], *picks, selected[-1]]
        if not picks:
            picks = [selected[len(selected) // 2]]
    else:
        # Disabling shaving retains every sampled frame, not every source
        # frame; `extract_fps` remains the explicit sampling rate.
        picks = list(selected)
    unique: list[tuple[Any, ...]] = []
    seen: set[float] = set()
    for item in picks:
        if item[0] not in seen:
            unique.append(item)
            seen.add(item[0])
    return unique


def _cut_interval_records(scene_id: str, start: float, end: float, selected: list[tuple[Any, ...]],
                          options: AnalyzerOptions) -> list[dict[str, Any]]:
    """Build timestamp-only cut subdivisions; source media is never duplicated."""
    if not options.extract_cut_clips or end <= start:
        return []
    boundaries = [start]
    last_boundary = start
    for sample in selected[1:]:
        timestamp, _, change = sample[:3]
        if (float(change) >= options.cut_boundary_threshold
                and float(timestamp) - last_boundary >= options.min_cut_seconds
                and end - float(timestamp) >= options.min_cut_seconds):
            boundaries.append(float(timestamp))
            last_boundary = float(timestamp)
    boundaries.append(end)
    return [{
        "cut_id": f"{scene_id}_cut_{number:04d}",
        "parent_scene_id": scene_id,
        "start_time_sec": round(cut_start, 3),
        "end_time_sec": round(cut_end, 3),
        "duration_sec": round(cut_end - cut_start, 3),
        "boundary_method": "motion_compensated_sampled_frame_difference",
        "boundary_confidence": "estimated",
        "media_storage": "virtual_source_interval",
        "requires_summary": False,
    } for number, (cut_start, cut_end) in enumerate(zip(boundaries[:-1], boundaries[1:]), start=1)]


def _extract_scenes(video: Path, output: Path, options: AnalyzerOptions, duration: float) -> list[dict[str, Any]]:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_step = max(1, int(round(fps / options.extract_fps)))
    samples: list[tuple[Any, ...]] = []
    index = 0
    previous: Any = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index % sample_step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (160, 90))
            change, camera_motion = (0.0, 0.0) if previous is None else _frame_pair_change(previous, small)
            samples.append((index / fps, frame.copy(), change, camera_motion))
            previous = small
        index += 1
    cap.release()
    used_fallback = not samples
    if not samples:
        samples = _extract_samples_ffmpeg(video, output / "_decoded_frames", options.extract_fps)
    boundaries = [0.0]
    for sample in samples[1:]:
        timestamp, _, change = sample[:3]
        if change >= options.scene_threshold and timestamp - boundaries[-1] >= options.min_scene_seconds:
            boundaries.append(timestamp)
    if not boundaries or boundaries[-1] < duration:
        boundaries.append(duration)
    scenes: list[dict[str, Any]] = []
    scene_root = output / "scenes"
    for number, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:]), start=1):
        selected = [item for item in samples if start <= item[0] <= end]
        if not selected:
            continue
        unique = _select_scene_frames(selected, options)
        scene_dir = scene_root / f"scene_{number:04d}"
        if options.persist_selected_frames:
            scene_dir.mkdir(parents=True, exist_ok=True)
        frames: list[dict[str, Any]] = []
        for frame_number, sample in enumerate(unique, start=1):
            timestamp, frame, change = sample[:3]
            camera_motion = float(sample[3]) if len(sample) > 3 else 0.0
            path = scene_dir / f"frame_{frame_number:04d}.jpg"
            if options.persist_selected_frames:
                cv2.imwrite(str(path), frame)
            frames.append({"frame_id": f"scene_{number:04d}_frame_{frame_number:04d}", "timestamp_sec": round(timestamp, 3),
                "path": str(path) if options.persist_selected_frames else None, "change_score": round(change, 5),
                "camera_motion_score": round(camera_motion, 5),
                "persisted": options.persist_selected_frames})
        scene_id = f"scene_{number:04d}"
        cuts = _cut_interval_records(scene_id, start, end, selected, options)
        scenes.append({"scene_id": scene_id, "start_time_sec": round(start, 3), "end_time_sec": round(end, 3), "duration_sec": round(end - start, 3), "frames": frames, "cuts": cuts})
    if used_fallback and options.delete_intermediate_samples and not options.keep_intermediate_samples:
        shutil.rmtree(output / "_decoded_frames", ignore_errors=True)
    return scenes


def _audio_events(audio_path: Path, duration: float, options: AnalyzerOptions) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    enabled = options.detect_speech or options.detect_music or options.detect_sfx
    report: dict[str, Any] = {"status": "disabled" if not enabled else "unavailable", "selected": "Auto: HTS-AT -> PANNs", "resolved": None, "fallbacks": []}
    if not enabled:
        return [], report
    if enabled and os.environ.get("VIDEO_AUDIO_ANALYZER_HTSAT_CHECKPOINT"):
        try:
            from .htsat_adapter import detect
            events = detect(audio_path, detect_speech=options.detect_speech, detect_music=options.detect_music, detect_sfx=options.detect_sfx)
            report.update({"status": "completed", "resolved": "HTS-AT", "event_count": len(events)})
            return events, report
        except Exception as exc:
            report["fallbacks"].append({"backend": "HTS-AT", "reason": str(exc)})
    if enabled and os.environ.get("VIDEO_AUDIO_ANALYZER_PANNS_CHECKPOINT"):
        try:
            from .panns_adapter import configured_detector
            events = configured_detector().detect(audio_path, detect_speech=options.detect_speech,
                detect_music=options.detect_music, detect_sfx=options.detect_sfx)
            report.update({"status": "completed", "resolved": "PANNs", "event_count": len(events)})
            for event in events:
                event["detectors"] = {"speech": options.detect_speech, "music": options.detect_music, "sfx_ambience": options.detect_sfx}
            return events, report
        except Exception as exc:
            report["fallbacks"].append({"backend": "PANNs", "reason": str(exc)})
    try:
        import numpy as np
        import soundfile as sf
        y, sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        if getattr(y, "ndim", 1) > 1:
            y = y.mean(axis=1)
        hop = 16000
        events: list[dict[str, Any]] = []
        for start in np.arange(0.0, max(duration, 0.01), 2.0):
            end = min(duration, float(start + 2.0))
            window = y[int(start * sr): int(end * sr)]
            if window.size == 0:
                continue
            rms = float(np.sqrt(np.mean(np.square(window))))
            zcr = float(np.mean(np.abs(np.diff(np.signbit(window))))) if window.size > 1 else 0.0
            event = {"event_id": f"audio_event_{len(events)+1:04d}", "start_time_sec": round(float(start), 3), "end_time_sec": round(float(end), 3), "label": "audio_activity", "rms": round(rms, 6), "zero_crossing_rate": round(zcr, 6), "classification_status": "model_not_preflighted", "confidence": None, "detectors": {"speech": options.detect_speech, "music": options.detect_music, "sfx_ambience": options.detect_sfx}}
            events.append(event)
        report.update({"status": "metadata_only" if enabled else "disabled", "resolved": "signal_measurements_only", "reason": "semantic event models unavailable" if enabled else "all event types disabled"})
        return events, report
    except Exception as exc:
        report.update({"status": "error", "reason": str(exc)})
        return [{"event_id": "audio_event_error", "start_time_sec": 0.0, "end_time_sec": round(duration, 3), "label": "unavailable", "classification_status": "error", "error": str(exc)}], report


def _music_detected(events: list[dict[str, Any]]) -> bool:
    return any((str(event.get("event_type", "")).lower() == "music"
        or str(event.get("label", "")).strip().lower() in {"music", "music playing"}
        or str(event.get("label", "")).strip().lower().startswith("musical instrument"))
        and float(event.get("confidence") or 0.0) >= 0.25 for event in events)


def _transcribe(audio_path: Path) -> dict[str, Any]:
    from .asr_adapter import transcribe
    return transcribe(audio_path)


def _collect_audio_event_clips(audio_path: Path, events: list[dict[str, Any]], output_dir: Path,
                               *, collect_music: bool, collect_sfx: bool) -> list[dict[str, Any]]:
    """Save bounded, timestamped excerpts only for categories explicitly opted in."""
    collected: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("event_type", "")).lower()
        label = str(event.get("label", "sound event")).lower()
        category = None
        if event_type == "music" and collect_music:
            category = "music"
        elif event_type in {"sfx", "sfx_ambience"} and collect_sfx:
            category = "ambience" if any(term in label for term in ("ambience", "ambient", "room tone", "rain", "wind", "crowd")) else "sfx"
        if category is None:
            continue
        start = max(0.0, float(event.get("start_time_sec", 0.0)))
        end = float(event.get("end_time_sec", 0.0))
        confidence = event.get("confidence")
        # Exclude malformed/very broad classifier intervals. Long detections
        # are chunked so one full-length soundtrack is not duplicated as an
        # event asset.
        if end <= start or (confidence is not None and float(confidence) < 0.35):
            continue
        cursor = start
        part = 0
        while cursor < end:
            part += 1
            part_end = min(end, cursor + 30.0)
            if part_end - cursor < 0.25:
                break
            event_id = str(event.get("event_id", f"event-{len(collected)+1:05d}"))
            safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in event_id)
            target_dir = output_dir / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{safe_id}_{part:02d}.wav"
            try:
                _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{cursor:.3f}",
                      "-t", f"{part_end - cursor:.3f}", "-i", str(audio_path), "-vn", "-ac", "1", "-ar", "16000",
                      "-c:a", "pcm_s16le", str(target)])
                collected.append({"asset_id": f"{category}_{safe_id}_{part:02d}", "category": category,
                    "event_id": event.get("event_id"), "event_type": event_type,
                    "label": event.get("label"), "confidence": confidence,
                    "start_time_sec": round(cursor, 3), "end_time_sec": round(part_end, 3),
                    "path": str(target), "source": "analysis.wav", "persisted_in_run": True,
                    "isolation_status": "unisolated_source_mix" if category in {"sfx", "ambience"} else "mixed_music_excerpt"})
            except Exception as exc:
                collected.append({"asset_id": f"{category}_{safe_id}_{part:02d}", "category": category,
                    "event_id": event.get("event_id"), "status": "error", "reason": str(exc)})
            cursor = part_end
    return collected


def _vector_cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return -1.0
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left)) or 1.0
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right)) or 1.0
    return sum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)


MUSIC_MOOD_PROMPTS = {
    "joyful": "upbeat joyful happy music with a bright celebratory mood",
    "sad": "sad melancholic music with a sorrowful reflective mood",
    "tense": "tense suspenseful music building anxiety and anticipation",
    "calm": "calm peaceful gentle relaxing music",
    "romantic": "warm romantic tender music expressing affection",
    "triumphant": "powerful triumphant heroic music expressing victory",
    "ominous": "dark ominous foreboding music suggesting danger",
    "playful": "light playful whimsical music with a mischievous mood",
}


def _run_peav_embeddings(video: Path, audio: dict[str, Any], scenes: list[dict[str, Any]],
                         audio_events: list[dict[str, Any]], run_dir: Path,
                         *, create_av: bool, create_audio: bool) -> dict[str, Any]:
    """Embed scene AV and timestamped audio events with one resident PE-AV model."""
    if not create_av and not create_audio:
        return {"status": "disabled", "provider": "facebook/pe-av-base", "scenes": 0, "audio_events": 0}
    if not os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_PATH"):
        return {"status": "unavailable", "provider": "facebook/pe-av-base", "reason": "isolated PE-AV worker is not configured", "scenes": 0, "audio_events": 0}
    try:
        from .peav_adapter import PEAVUnavailable, configured_adapter
        adapter = configured_adapter()
    except Exception as exc:
        return {"status": "error", "provider": "facebook/pe-av-base", "reason": str(exc), "scenes": 0, "audio_events": 0}
    embedding_dir = run_dir / "embeddings"
    embedding_dir.mkdir(parents=True, exist_ok=True)
    scene_outputs: list[str] = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        if not create_av:
            continue
        clip_path = embedding_dir / f"{scene_id}.mp4"
        try:
            _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(scene["start_time_sec"]), "-to", str(scene["end_time_sec"]), "-i", str(video), "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(clip_path)])
            output = adapter.embed(video=str(clip_path), audio=str(clip_path) if audio.get("analysis_wav") else None)
            vector = (output.get("audio_video_embeds") or output.get("video_embeds") or output.get("visual_embeds") or [None])[0]
            if vector is None:
                raise RuntimeError("PE-AV returned no video/audio projection")
            scene["embeddings"] = {"provider": "facebook/pe-av-base", "dimension": len(vector), "audio_video": vector}
            scene_file = embedding_dir / f"{scene_id}.json"
            scene_file.write_text(json.dumps(scene["embeddings"], indent=2), encoding="utf-8")
            scene_outputs.append(str(scene_file))
        except Exception as exc:
            scene["embeddings"] = {"provider": "facebook/pe-av-base", "status": "error", "error": str(exc)}
    completed_scenes = sum(1 for scene in scenes if scene.get("embeddings", {}).get("audio_video")) if create_av else 0
    completed_audio = 0
    mood_status = "disabled"
    candidates: list[tuple[int, dict[str, Any]]] = []
    prioritized: list[tuple[int, dict[str, Any]]] = []
    audio_requested_count = 0
    if create_audio and audio.get("analysis_wav"):
        source_audio = Path(str(audio["analysis_wav"]))
        audio_events_dir = embedding_dir / "audio_events"
        audio_events_dir.mkdir(parents=True, exist_ok=True)
        max_events = max(1, int(os.environ.get("VIDEO_AUDIO_ANALYZER_MAX_AUDIO_EMBED_EVENTS", "500")))
        candidates = [(index, event) for index, event in enumerate(audio_events)
            if event.get("event_type") and event.get("label") not in {None, "", "audio_activity", "unavailable"}
            and float(event.get("end_time_sec", 0) or 0) > float(event.get("start_time_sec", 0) or 0)]
        prioritized = sorted(candidates, key=lambda pair: float(pair[1].get("confidence") or 0.0), reverse=True)[:max_events]
        audio_requested_count = len(prioritized)
        mood_text_vectors: dict[str, list[float]] = {}
        try:
            for mood, prompt in MUSIC_MOOD_PROMPTS.items():
                text_output = adapter.embed(text=prompt)
                text_vector = (text_output.get("text_audio_video_embeds") or text_output.get("visual_text_embeds") or [None])[0]
                if isinstance(text_vector, list):
                    mood_text_vectors[mood] = [float(value) for value in text_vector]
            mood_status = "relative_similarity" if mood_text_vectors else "unavailable"
        except Exception as exc:
            mood_status = f"unavailable: {exc}"
        with tempfile.TemporaryDirectory(prefix="vaa-peav-audio-") as temp_name:
            temp_root = Path(temp_name)
            for index, event in prioritized:
                start = max(0.0, float(event.get("start_time_sec", 0) or 0))
                end = float(event.get("end_time_sec", start) or start)
                target = temp_root / f"event_{index:05d}.wav"
                try:
                    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(end - start), "-i", str(source_audio), "-ac", "1", "-ar", "16000", str(target)])
                    output = adapter.embed(audio=str(target))
                    vector = (output.get("audio_embeds") or output.get("audio_video_embeds") or [None])[0]
                    if not isinstance(vector, list):
                        raise RuntimeError("PE-AV returned no audio projection")
                    event.setdefault("embeddings", {}).update({"provider": "facebook/pe-av-base", "dimension": len(vector), "audio": vector})
                    if str(event.get("event_type", "")).lower() == "music" and mood_text_vectors:
                        ranked = sorted(((mood, _vector_cosine(vector, prompt_vector)) for mood, prompt_vector in mood_text_vectors.items()), key=lambda item: item[1], reverse=True)
                        event["semantic_mood"] = {"method": "PE-AV audio/text cosine similarity", "scores_are_calibrated_probabilities": False,
                            "top_match": ranked[0][0], "candidates": [{"label": mood, "similarity": round(score, 6)} for mood, score in ranked]}
                    detail_path = audio_events_dir / f"{event.get('event_id', f'event_{index:05d}')}.json"
                    detail_path.write_text(json.dumps({"provider": "facebook/pe-av-base", "dimension": len(vector), "audio": vector}, indent=2), encoding="utf-8")
                    event["embedding_path"] = detail_path.relative_to(run_dir).as_posix()
                    completed_audio += 1
                except Exception as exc:
                    event.setdefault("embeddings", {}).update({"provider": "facebook/pe-av-base", "status": "error", "error": str(exc)})
    requested_success = ((not create_av or completed_scenes == len(scenes))
        and (not create_audio or not audio.get("analysis_wav") or completed_audio == audio_requested_count))
    status = "completed" if requested_success else "partial"
    return {"status": status, "provider": "facebook/pe-av-base", "dimension": adapter.dimension,
        "scenes": completed_scenes, "audio_events": completed_audio,
        "audio_events_skipped_by_limit": max(0, len(candidates) - len(prioritized)) if create_audio and audio.get("analysis_wav") else 0,
        "music_mood_status": mood_status, "outputs": scene_outputs}


def analyze_video(video: Path, root: Path, options: AnalyzerOptions | None = None) -> dict[str, Any]:
    options = options or AnalyzerOptions()
    video = video.resolve()
    probe = _probe(video)
    metadata = _metadata(video, probe)
    base_run_dir = root / "runs" / metadata["video_id"]
    run_dir = base_run_dir if not base_run_dir.exists() else root / "runs" / f"{metadata['video_id']}-rerun-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    owner_job_id = os.environ.get("VIDEO_AUDIO_ANALYZER_JOB_ID", "").strip()
    if owner_job_id:
        (run_dir / "job_owner.json").write_text(json.dumps({"job_id": owner_job_id}), encoding="utf-8")
    audio = _extract_audio(video, run_dir / "audio", options) if metadata["audio_streams"] else {"warnings": ["no audio stream"]}
    scenes = _extract_scenes(video, run_dir, options, metadata["duration_sec"])
    all_frame_evidence: list[dict[str, Any]] = []
    for scene in scenes:
        for frame in scene["frames"]:
            if options.analyze_frame_evidence and frame.get("path"):
                evidence = analyze_frame(Path(frame["path"]), frame["frame_id"], frame["timestamp_sec"])
                frame["evidence"] = evidence
                all_frame_evidence.append(evidence)
        if options.analyze_frame_evidence and options.persist_selected_frames:
            (run_dir / "scenes" / scene["scene_id"] / "frame_evidence.json").write_text(json.dumps(scene["frames"], indent=2), encoding="utf-8")
    audio_events, event_detection = _audio_events(Path(audio["analysis_wav"]), metadata["duration_sec"], options) if audio.get("analysis_wav") else ([], {"status": "unavailable", "reason": "no analysis audio"})
    music = analyze_music(Path(audio["analysis_wav"]), metadata["duration_sec"], options.detect_music) if audio.get("analysis_wav") else {"status": "unavailable", "backend": "librosa", "segments": [], "reason": "no analysis audio"}
    music_detected = _music_detected(audio_events)
    from .demucs_adapter import separate
    demucs = separate(Path(audio["analysis_wav"]), run_dir / "audio" / "stems", options.run_demucs,
        music_detected, auto_voice_requested=options.collect_voice_examples) if audio.get("analysis_wav") else {
            "status": "unavailable", "mode": options.run_demucs, "outputs": [], "reason": "no analysis audio"}
    transcript = extract_embedded(video, run_dir / "subtitles")
    if transcript.get("status") != "completed" and audio.get("analysis_wav"):
        transcript = _transcribe(Path(audio["analysis_wav"]))
    if options.diarize_speakers and audio.get("analysis_wav"):
        from .nemo_adapter import diarize
        diarization = diarize(Path(audio["analysis_wav"]), run_dir / "audio" / "diarization")
    else:
        diarization = {"status": "disabled" if not options.diarize_speakers else "unavailable", "backend": "nemo-clustering", "segments": [], "reason": "disabled" if not options.diarize_speakers else "no analysis audio"}
    voice_store_root = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_VOICE_STORE_PATH", str(root / "voice_store")))
    if options.collect_voice_examples and audio.get("analysis_wav"):
        # Prefer Demucs' vocals stem for voice examples when available, but
        # retain the original mix as the timestamp/provenance source.
        vocals_stem = next((Path(item) for item in demucs.get("outputs", [])
            if Path(item).name.lower() == "vocals.wav" and Path(item).is_file()), None)
        voice_source = vocals_stem or Path(audio["analysis_wav"])
        voices = extract_voice_examples(voice_source, transcript, run_dir / "audio" / "voices",
            diarization=diarization, store_root=voice_store_root, project_id=os.environ.get("VIDEO_AUDIO_ANALYZER_PROJECT_ID", metadata["video_id"]),
            video_id=metadata["video_id"], identity_scope="project_only", save_audio_examples=True)
        voices["source_audio"] = "demucs_vocals_stem" if vocals_stem else "original_analysis_mix"
    else:
        voices = {"status": "disabled" if not options.collect_voice_examples else "unavailable", "backend": "speechbrain-ecapa",
            "examples": [], "identity_store": {"status": "disabled", "persisted_identities": 0, "director_candidates": 0},
            "reason": "voice collection was not selected for this analysis" if not options.collect_voice_examples else "no analysis audio"}
    media_assets = _collect_audio_event_clips(Path(audio["analysis_wav"]), audio_events, run_dir / "audio" / "collected",
        collect_music=options.collect_music_clips, collect_sfx=options.collect_sfx_clips) if audio.get("analysis_wav") else []
    media_assets.extend({"asset_id": item.get("voice_example_id"), "category": "voices", "speaker_id": item.get("speaker_id"),
        "start_time_sec": item.get("start_time_sec"), "end_time_sec": item.get("end_time_sec"),
        "path": item.get("audio_path"), "persisted_in_run": True} for item in voices.get("examples", []) if item.get("audio_path"))
    character_tracking = {"status": "unavailable", "backend": "person tracker/ReID", "reason": "person-track provider/checkpoint not configured", "tracks": []}
    active_speaker = {"status": "unavailable", "backend": "TalkNet", "reason": "isolated TalkNet runtime/checkpoint not configured", "scores": []}
    talknet_url = os.environ.get("VIDEO_AUDIO_ANALYZER_TALKNET_URL")
    if talknet_url:
        try:
            from .talknet_adapter import detect_active_speakers
            active_speaker = detect_active_speakers(video, talknet_url)
            if active_speaker.get("status") == "completed":
                character_tracking = {"status": "tracks_detected", "backend": "TalkNet S3FD face tracks",
                    "tracks": active_speaker.get("tracks", []),
                    "identity_scope": "within_video_face_track_only",
                    "cross_scene_character_identity": "not_asserted_without_licensed_face_embedding_model"}
        except Exception as exc:
            active_speaker = {"status": "error", "backend": "TalkNet", "reason": str(exc), "scores": []}
    from .identity import associate_speakers
    associations = associate_speakers(diarization.get("segments", []), character_tracking.get("tracks", []), active_speaker.get("scores", []))
    from .sam_audio_adapter import readiness as sam_readiness
    sam_status = sam_readiness()
    pe_av = _run_peav_embeddings(video, audio, scenes, audio_events, run_dir,
        create_av=options.create_av_embeddings, create_audio=options.create_audio_embeddings)
    event_by_id = {str(event.get("event_id")): event for event in audio_events}
    for media_asset in media_assets:
        matched_event = event_by_id.get(str(media_asset.get("event_id")))
        if matched_event and matched_event.get("semantic_mood"):
            media_asset["semantic_mood"] = matched_event["semantic_mood"]
    statuses = {
        "source": "completed",
        "audio_extraction": "completed" if audio.get("analysis_wav") else "unavailable",
        "scene_detection": "completed",
        "frame_selection": "completed" if any(frame.get("path") for scene in scenes for frame in scene.get("frames", [])) else "timestamps_only",
        "compact_frame_evidence": "completed" if options.analyze_frame_evidence else "disabled_direct_video_primary",
        "audio_event_detection": event_detection.get("status", "unavailable"),
        "music_analysis": music.get("status", "unavailable"),
        "transcription": transcript.get("status", "unavailable"),
        "diarization": diarization.get("status", "unavailable"),
        "voice_embeddings": voices.get("status", "unavailable"),
        "pe_av_embeddings": pe_av["status"],
        "pe_av_audio_embeddings": "disabled" if not options.create_audio_embeddings else "completed" if pe_av.get("audio_events", 0) else "unavailable_or_no_classified_events",
        "clap_reranking": "enabled" if (os.environ.get("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT") or os.environ.get("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL")) else "unavailable_checkpoint_not_configured",
        "demucs": demucs.get("status", "unavailable"),
        "sam_audio": "on_demand_ready" if sam_status.get("status") == "ready" else "on_demand_unavailable",
        "voice_store": voices.get("identity_store", {}).get("status", "unavailable"),
        "character_tracking": character_tracking["status"],
        "active_speaker_detection": active_speaker["status"],
        "director_confirmation": "pending_codex_director_integration" if any(e.get("identity_merge_state") == "pending_director_review" for e in voices.get("examples", [])) or any(a.get("candidate_track_id") for a in associations) else "not_run_no_identity_candidates",
    }
    summary = f"{metadata['file_name']} contains {len(scenes)} cut-defined scene(s) over {metadata['duration_sec']:.2f} seconds. Scene timestamps and synchronized audio artifacts were produced. Advanced model stages remain explicitly marked by preflight status."
    manifest = {
        "pipeline": {"name": "video_audio_analyzer", "version": "0.1.0"},
        "run_id": run_dir.name,
        "job_id": owner_job_id or None,
        "run_dir": str(run_dir),
        "source": metadata,
        "options": options.__dict__,
        "frame_shaving": {"sampling_fps": options.extract_fps, "scene_change_sensitivity": options.scene_threshold, "frame_change_threshold": options.frame_change_threshold, "minimum_scene_seconds": options.min_scene_seconds, "adaptive_sampling": options.adaptive_sampling, "preserve_scene_anchors": options.preserve_scene_anchors, "intermediate_samples_kept": options.keep_intermediate_samples, "intermediate_cleanup": options.delete_intermediate_samples and not options.keep_intermediate_samples},
        "statuses": statuses,
        "audio": audio,
        "scenes": scenes,
        "frame_evidence": all_frame_evidence,
        "audio_events": audio_events,
        "sound_event_detection": event_detection,
        "music_features": music,
        "demucs": demucs,
        "transcript": transcript,
        "voices": voices,
        "media_collection": {"settings": {"collect_voice_examples": options.collect_voice_examples,
            "collect_music_clips": options.collect_music_clips, "collect_sfx_clips": options.collect_sfx_clips},
            "status": "completed" if media_assets else "no_assets_collected",
            "assets": media_assets, "asset_count": len(media_assets)},
        "diarization": diarization,
        "speaker_character_associations": associations,
        "character_tracking": character_tracking,
        "active_speaker_detection": active_speaker,
        "sam_audio_readiness": sam_status,
        "embeddings": {"pe_av": pe_av, "clap": None},
        "summary": summary,
        "provenance": {"source_video": str(video), "source_sha256": metadata["video_id"]},
    }
    index_report = build_index(manifest, run_dir)
    manifest["index"] = index_report
    manifest["embeddings"]["clap"] = index_report.get("clap")
    statuses["retrieval_index"] = index_report["backend"]
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    return manifest
