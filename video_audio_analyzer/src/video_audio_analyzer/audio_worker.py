"""Optional isolated NeMo/CLAP/SAM sidecar; no video/ComfyUI duties."""
from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(title="Video Audio Analyzer model worker", version="0.1.0")


@lru_cache(maxsize=1)
def _clap_model():
    """Load the multi-GB CLAP checkpoint once per worker, not once per request."""
    from .clap_adapter import CLAPAdapter
    return CLAPAdapter(os.environ.get("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT", ""))


class TextRequest(BaseModel):
    texts: list[str]


@app.get("/health")
def health() -> dict[str, Any]:
    from .preflight import run_preflight
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory(prefix="vaa-model-health-") as directory:
        report = run_preflight(Path(directory))
    components = report["components"]
    return {"ok": True, "service": "video_audio_analyzer_audio_worker", "torch_version": _torch_version(),
        "cuda_available": _cuda_available(), "nemo": components["NeMo"], "clap": components["CLAP"],
        "sam_audio": components["SAM Audio"]}


def _torch_version() -> str | None:
    try:
        import torch
        return torch.__version__
    except Exception:
        return None


def _cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


@app.post("/api/diarize")
async def diarize_audio(audio: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(audio.filename or "analysis.wav").suffix or ".wav"
    with tempfile.TemporaryDirectory(prefix="vaa-nemo-") as directory:
        source = Path(directory) / f"input{suffix}"
        output = Path(directory) / "output"
        source.write_bytes(await audio.read())
        from .nemo_adapter import diarize
        result = diarize(source, output)
        if result.get("status") in {"error"}:
            raise HTTPException(status_code=503, detail=result)
        rttm_path = result.pop("rttm_path", None)
        if result.get("status") == "completed" and rttm_path and Path(rttm_path).is_file():
            result["rttm_text"] = Path(rttm_path).read_text(encoding="utf-8")
        return result


@app.post("/api/clap/text")
def clap_text(request: TextRequest) -> dict[str, Any]:
    if not request.texts or len(request.texts) > 256:
        raise HTTPException(status_code=422, detail="texts must contain 1–256 entries")
    try:
        vectors = _clap_model().text(request.texts)
        return {"model": "LAION-AI/CLAP", "dimension": len(vectors[0]), "embeddings": vectors}
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"model": "LAION-AI/CLAP", "reason": str(exc)}) from exc


@app.post("/api/clap/audio")
async def clap_audio(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not files or len(files) > 256:
        raise HTTPException(status_code=422, detail="files must contain 1–256 audio clips")
    try:
        adapter = _clap_model()
        with tempfile.TemporaryDirectory(prefix="vaa-clap-upload-") as directory:
            paths = []
            for index, uploaded in enumerate(files):
                suffix = Path(uploaded.filename or "clip.wav").suffix or ".wav"
                path = Path(directory) / f"clip_{index:04d}{suffix}"
                path.write_bytes(await uploaded.read())
                paths.append(path)
            vectors = adapter.audio(paths)
        return {"model": "LAION-AI/CLAP", "dimension": len(vectors[0]), "embeddings": vectors}
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"model": "LAION-AI/CLAP", "reason": str(exc)}) from exc


@app.post("/isolate")
def sam_isolate_unavailable() -> dict[str, Any]:
    # Deliberately explicit until gated SAM Audio weights and its approved
    # runtime adapter are present. The caller must not mistake HTTP availability
    # for successful model inference.
    raise HTTPException(status_code=503, detail={"status": "unavailable", "model": "facebook/sam-audio-large-tv",
        "reason": "SAM Audio checkpoint access/runtime is not prepared; no fallback model is substituted"})
