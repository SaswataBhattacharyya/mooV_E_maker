"""Official SAM Audio text+time isolation, isolated from analyzer workers."""
from __future__ import annotations

import os
import json
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

app = FastAPI(title="Video Audio Analyzer SAM Audio worker", version="0.1.0")
MODEL_ID = os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_MODEL", "facebook/sam-audio-large-tv")
CHECKPOINT = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_PATH", "/models/sam-audio-large-tv"))
CHECKPOINT_FILENAME = os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_CHECKPOINT_FILENAME", "sam-audio-large-tv_checkpoint.pt")
T5_CHECKPOINT = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_T5_PATH", "/models/sam-audio-t5-base"))
_model_alias_dir: tempfile.TemporaryDirectory[str] | None = None
_gpu_lock = Lock()


def _checkpoint_ready() -> bool:
    if not CHECKPOINT.is_dir() or not (CHECKPOINT / "config.json").is_file():
        return False
    return any((CHECKPOINT / name).is_file() for name in ("checkpoint.pt", CHECKPOINT_FILENAME))


def _loader_checkpoint_dir() -> Path:
    """Expose the HF-standard checkpoint filename without copying 14.9 GB."""
    global _model_alias_dir
    standard = CHECKPOINT / "checkpoint.pt"
    if standard.is_file():
        return CHECKPOINT
    actual = CHECKPOINT / CHECKPOINT_FILENAME
    if not actual.is_file():
        raise RuntimeError(f"SAM Audio checkpoint file is missing: expected {standard.name} or {actual.name} in {CHECKPOINT}")
    if _model_alias_dir is None:
        _model_alias_dir = tempfile.TemporaryDirectory(prefix="vaa-sam-checkpoint-")
        alias = Path(_model_alias_dir.name)
        config = json.loads((CHECKPOINT / "config.json").read_text(encoding="utf-8"))
        # SAM's text encoder calls Transformers.from_pretrained internally.
        # Redirect it to the separately preflighted local T5 files and omit
        # ranking/span auxiliaries that are not used by our anchored,
        # one-candidate isolation path. This keeps inference offline.
        config["text_encoder"]["name"] = str(T5_CHECKPOINT)
        config["span_predictor"] = None
        config["text_ranker"] = None
        config["visual_ranker"] = None
        (alias / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (alias / "checkpoint.pt").symlink_to(actual)
    return Path(_model_alias_dir.name)


def _t5_ready() -> bool:
    return (T5_CHECKPOINT / "config.json").is_file() and any((T5_CHECKPOINT / name).is_file()
        for name in ("model.safetensors", "pytorch_model.bin")) and any((T5_CHECKPOINT / name).is_file()
        for name in ("spiece.model", "tokenizer.json"))


@app.get("/health")
def health() -> dict[str, Any]:
    ready = _checkpoint_ready()
    t5_ready = _t5_ready()
    return {"ok": ready and t5_ready and torch.cuda.is_available(), "service": "sam_audio_isolation",
        "repository": "facebookresearch/sam-audio", "model": MODEL_ID,
        "license": "SAM License; review the official terms before redistribution/commercial use",
        "checkpoint_path": str(CHECKPOINT), "checkpoint_present": ready,
        "checkpoint_filename": CHECKPOINT_FILENAME,
        "auxiliary_models": {"t5": {"model": "google-t5/t5-base", "path": str(T5_CHECKPOINT), "ready": t5_ready}},
        "authentication_required_for_download": True, "cuda_available": bool(torch.cuda.is_available()),
        "download_on_request": False}


@lru_cache(maxsize=1)
def _load_model() -> tuple[Any, Any, str]:
    if not _checkpoint_ready():
        raise RuntimeError(f"gated SAM Audio checkpoint is not prepared at {CHECKPOINT}")
    from sam_audio import SAMAudio, SAMAudioProcessor
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device != "cuda":
        raise RuntimeError("SAM Audio worker requires the configured CUDA device for this deployment")
    # Local-only loading ensures the worker never silently downloads gated
    # weights. The user's accepted HF access is used during explicit setup.
    if not _t5_ready():
        raise RuntimeError(f"local SAM text-encoder dependency is missing/incomplete at {T5_CHECKPOINT}; expected config, weights, and tokenizer files")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    model_path = _loader_checkpoint_dir()
    # SAM Audio's BaseModel._from_pretrained still requires the Hub 0.x
    # `proxies` and `resume_download` arguments, while Hub 1.x's public mixin
    # wrapper no longer forwards them. Call SAM's own loader directly with a
    # local path and downloads disabled; this keeps the model API and runtime
    # version intact without monkey-patching dependencies.
    model = SAMAudio._from_pretrained(model_id=str(model_path), cache_dir=None,
        force_download=False, proxies=None, resume_download=False,
        local_files_only=True, token=None, strict=False).to(device).eval()
    processor = SAMAudioProcessor.from_pretrained(str(model_path))
    return model, processor, device


@app.post("/isolate")
async def isolate(audio: UploadFile = File(...), prompt: str = Form(...),
                  start_sec: float = Form(...), end_sec: float = Form(...),
                  model: str = Form("facebook/sam-audio-large-tv")) -> Response:
    if model != MODEL_ID:
        raise HTTPException(status_code=422, detail=f"only the configured checkpoint {MODEL_ID} is supported")
    if end_sec <= start_sec or start_sec < 0 or not prompt.strip():
        raise HTTPException(status_code=422, detail="prompt and a positive time span are required")
    if not _checkpoint_ready():
        raise HTTPException(status_code=503, detail={"status": "unavailable", "model": model,
            "reason": "official gated checkpoint missing; inference never downloads weights"})
    source_bytes = await audio.read()
    maximum_bytes = int(os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))
    if len(source_bytes) > maximum_bytes:
        raise HTTPException(status_code=413, detail="audio exceeds configured SAM worker upload limit")
    with tempfile.TemporaryDirectory(prefix="vaa-sam-audio-") as directory:
        source = Path(directory) / "analysis.wav"
        target = Path(directory) / "target.wav"
        source.write_bytes(source_bytes)
        try:
            audio_info = sf.info(str(source))
            duration = float(audio_info.duration)
            if start_sec >= duration:
                raise HTTPException(status_code=422, detail="start time is outside the uploaded audio")
            end_sec_clamped = min(float(end_sec), duration)
            with _gpu_lock:
                sam_model, processor, device = _load_model()
                anchors = [[["+", float(start_sec), end_sec_clamped]]]
                batch = processor(audios=[str(source)], descriptions=[prompt.strip().lower()], anchors=anchors).to(device)
                with torch.inference_mode():
                    result = sam_model.separate(batch, predict_spans=False, reranking_candidates=1)
                isolated = result.target[0].detach().float().cpu().numpy()
            isolated = np.asarray(isolated).squeeze()
            if isolated.ndim != 1 or isolated.size == 0:
                raise RuntimeError(f"SAM returned unexpected target waveform shape {isolated.shape}")
            sf.write(str(target), isolated, int(processor.audio_sampling_rate), subtype="PCM_16")
            if not target.is_file() or target.stat().st_size < 44:
                raise RuntimeError("SAM returned an empty isolated WAV")
            return Response(content=target.read_bytes(), media_type="audio/wav", headers={
                "X-SAM-Audio-Model": model, "X-SAM-Audio-Prompt": prompt.strip()[:256],
                "X-SAM-Audio-Start": str(float(start_sec)), "X-SAM-Audio-End": str(end_sec_clamped),
                "X-SAM-Audio-Sample-Rate": str(int(processor.audio_sampling_rate)),
            })
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"status": "error", "model": model,
                "reason": f"SAM Audio isolation failed: {exc}"}) from exc
