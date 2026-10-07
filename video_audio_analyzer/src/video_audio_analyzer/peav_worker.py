"""Minimal standard-library HTTP API for PE-AV text-query embeddings.

This worker intentionally avoids adding FastAPI/Uvicorn to the isolated model
image. The model is loaded once, lazily, on the first embedding request.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import torch

from .peav_adapter import PEAVAdapter


MODEL_ID = "facebook/pe-av-base"
MAX_BODY_BYTES = 16_384


@lru_cache(maxsize=1)
def _adapter() -> PEAVAdapter:
    path = os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", "/models/pe-av-base")
    return PEAVAdapter(Path(path))


def health() -> dict[str, Any]:
    checkpoint = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", "/models/pe-av-base"))
    ready = (checkpoint / "config.json").is_file() and (checkpoint / "model.safetensors").is_file()
    return {
        "ok": ready,
        "service": "video_audio_analyzer_peav_query",
        "model": MODEL_ID,
        "status": "checkpoint_ready_lazy_load" if ready else "checkpoint_unavailable",
        "checkpoint": str(checkpoint),
        "cuda_available": torch.cuda.is_available(),
    }


def embed_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text or len(text) > 2000:
        raise ValueError("text must contain 1–2000 non-whitespace characters")
    result = _adapter().embed(text=text)
    vectors = result.get("text_audio_video_embeds") or result.get("visual_text_embeds") or result.get("text_video_embeds")
    if not vectors or not vectors[0]:
        raise RuntimeError("PE-AV returned no text embedding")
    vector = [float(value) for value in vectors[0]]
    return {"model": MODEL_ID, "dimension": len(vector), "embedding": vector}


class _Handler(BaseHTTPRequestHandler):
    server_version = "VideoAudioAnalyzerPEAV/0.1"

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        if urlparse(self.path).path != "/health":
            self._respond(404, {"detail": "not found"})
            return
        report = health()
        self._respond(200 if report["ok"] else 503, report)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler protocol
        if urlparse(self.path).path != "/embed/text":
            self._respond(404, {"detail": "not found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, {"detail": "invalid Content-Length"})
            return
        if content_length < 1 or content_length > MAX_BODY_BYTES:
            self._respond(413, {"detail": "request body must be between 1 and 16384 bytes"})
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise ValueError("JSON body must contain a string 'text' field")
            self._respond(200, embed_text(payload["text"]))
        except (json.JSONDecodeError, ValueError) as exc:
            self._respond(422, {"detail": str(exc)})
        except Exception as exc:
            self._respond(503, {"model": MODEL_ID, "detail": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[peav-query-worker] {self.address_string()} {format % args}", flush=True)


def main() -> None:
    host = os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_HOST", "0.0.0.0")
    port = int(os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_PORT", "8034"))
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"PE-AV query worker listening on {host}:{port}; checkpoint is lazy-loaded", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
