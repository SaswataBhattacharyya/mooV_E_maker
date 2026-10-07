"""Isolated TalkNet worker; all job output is created under a fresh temp dir."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="Video Audio Analyzer TalkNet worker", version="0.1.0")
REPO = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_TALKNET_REPO", "/opt/TalkNet-ASD"))
MODEL = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_TALKNET_CHECKPOINT", "/models/talknet/pretrain_TalkSet.model"))
FACE_MODEL = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_S3FD_CHECKPOINT", "/models/talknet/sfd_face.pth"))


@app.get("/health")
def health() -> dict[str, Any]:
    dependencies = {}
    for module in ("torch", "torchvision", "scenedetect", "python_speech_features", "cv2"):
        try:
            __import__(module)
            dependencies[module] = True
        except Exception as exc:  # report exact missing/incompatible dependency
            dependencies[module] = {"available": False, "reason": str(exc)}
    try:
        import torch
        cuda_available = bool(torch.cuda.is_available())
        cuda_device = torch.cuda.get_device_name(0) if cuda_available else None
    except Exception as exc:
        cuda_available, cuda_device = False, str(exc)
    return {"ok": all(value is True for value in dependencies.values()) and cuda_available, "service": "talknet_active_speaker",
            "repository": "TaoRuijie/TalkNet-ASD", "model": "TalkSet pretrained checkpoint",
            "checkpoint_present": MODEL.is_file(), "face_checkpoint_present": FACE_MODEL.is_file(),
            "dependencies": dependencies, "device": "cuda", "cuda_available": cuda_available,
            "cuda_device": cuda_device}


def _compact_tracks(tracks: list[dict[str, Any]], score_sets: list[Any], fps: float = 25.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import numpy as np

    output_tracks: list[dict[str, Any]] = []
    scores_out: list[dict[str, Any]] = []
    for index, row in enumerate(tracks):
        track = row.get("track", {})
        detections = row.get("proc_track", {})
        frames = np.asarray(track.get("frame", []), dtype="int64").reshape(-1)
        score = np.asarray(score_sets[index] if index < len(score_sets) else [], dtype="float32").reshape(-1)
        count = min(len(frames), len(score))
        if not count:
            continue
        frames, score = frames[:count], score[:count]
        # Match TalkNet's published visualization: 5-frame moving mean and
        # zero logit threshold. Keep per-frame evidence for later diarization.
        smoothed_logits = np.asarray([score[max(i - 2, 0):min(i + 3, count)].mean() for i in range(count)])
        probabilities = 1.0 / (1.0 + np.exp(-np.clip(smoothed_logits, -80.0, 80.0)))
        track_id = f"talknet_face_track_{index + 1:04d}"
        active = smoothed_logits >= 0.0
        output_tracks.append({"track_id": track_id, "start_time_sec": round(float(frames.min()) / fps, 3),
            "end_time_sec": round(float(frames.max() + 1) / fps, 3), "frame_count": int(count),
            "face_evidence": "S3FD detections linked by TalkNet shot tracker", "body_reid_evidence": None,
            "identity_scope": "within_video_track_only", "persistent_character_identity": False})
        for i, frame_number in enumerate(frames):
            box = {}
            for key in ("x", "y", "s"):
                values = detections.get(key)
                if values is not None and i < len(values):
                    box[key] = float(values[i])
            scores_out.append({"track_id": track_id, "timestamp_sec": round(float(frame_number) / fps, 3),
                "score": round(float(probabilities[i]), 6), "talknet_logit": round(float(smoothed_logits[i]), 6),
                "raw_score": round(float(score[i]), 6),
                "is_active_speaker": bool(active[i]), "face_box": box, "detector": "TalkNet"})
    return output_tracks, scores_out


@app.post("/api/active-speaker")
async def active_speaker(video: UploadFile = File(...)) -> dict[str, Any]:
    if not MODEL.is_file() or not FACE_MODEL.is_file():
        raise HTTPException(status_code=503, detail={"status": "unavailable", "reason": "TalkNet or S3FD checkpoint not mounted"})
    if not (REPO / "demoTalkNet.py").is_file():
        raise HTTPException(status_code=503, detail={"status": "unavailable", "reason": f"TalkNet source missing at {REPO}"})
    suffix = Path(video.filename or "source.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        suffix = ".mp4"
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="vaa-talknet-") as temp:
        root = Path(temp)
        source_dir = root / "input"
        source_dir.mkdir()
        name = f"source-{uuid.uuid4().hex[:8]}"
        source_path = source_dir / f"{name}{suffix}"
        source_path.write_bytes(await video.read())
        # The upstream script checks this path relative to cwd and may try an
        # implicit gdown download. Copy a verified mounted checkpoint into its
        # isolated temporary checkout so inference stays offline.
        runtime_repo = root / "TalkNet-ASD"
        shutil.copytree(REPO, runtime_repo)
        face_path = runtime_repo / "model" / "faceDetector" / "s3fd" / "sfd_face.pth"
        face_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FACE_MODEL, face_path)
        # The upstream demo removes only <videoFolder>/<videoName>. This is a
        # newly-created job-scoped directory, never an existing analyzer run.
        output_dir = root / "work"
        output_dir.mkdir()
        shutil.copy2(source_path, output_dir / source_path.name)
        command = ["python3", "demoTalkNet.py", "--videoName", name, "--videoFolder", str(output_dir),
                   "--pretrainModel", str(MODEL), "--nDataLoaderThread", "2"]
        try:
            result = subprocess.run(command, cwd=runtime_repo, capture_output=True, text=True,
                timeout=int(os.environ.get("VIDEO_AUDIO_ANALYZER_TALKNET_TIMEOUT_SEC", "900")), check=False)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail={"status": "error", "reason": "TalkNet timed out",
                "timeout_sec": int(os.environ.get("VIDEO_AUDIO_ANALYZER_TALKNET_TIMEOUT_SEC", "900"))}) from exc
        result_dir = output_dir / name / "pywork"
        tracks_file, scores_file = result_dir / "tracks.pckl", result_dir / "scores.pckl"
        if result.returncode or not tracks_file.is_file() or not scores_file.is_file():
            detail = {"status": "error", "returncode": result.returncode,
                "stdout_tail": result.stdout[-3000:], "stderr_tail": result.stderr[-6000:],
                "expected_tracks": str(tracks_file), "expected_scores": str(scores_file)}
            raise HTTPException(status_code=503, detail=detail)
        import pickle
        with tracks_file.open("rb") as handle:
            tracks_data = pickle.load(handle)
        with scores_file.open("rb") as handle:
            scores_data = pickle.load(handle)
        tracks, scores = _compact_tracks(tracks_data, scores_data)
        return {"status": "completed", "backend": "TalkNet-ASD", "model": "TalkSet pretrained model",
            "face_detector": "S3FD", "fps": 25.0, "tracks": tracks, "scores": scores,
            "track_count": len(tracks), "active_frame_count": sum(s["is_active_speaker"] for s in scores),
            "elapsed_sec": round(time.monotonic() - started, 3), "artifacts_retained": False,
            "log_tail": result.stderr[-1200:]}
