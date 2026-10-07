"""Lazy LAION-CLAP audio/text embeddings; kept separate from PE-AV vectors."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any


class CLAPUnavailable(RuntimeError):
    pass


class CLAPAdapter:
    def __init__(self, checkpoint: str | Path | None = None):
        self.checkpoint = Path(checkpoint or os.environ.get("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT", ""))
        if not str(self.checkpoint) or not self.checkpoint.is_file():
            raise CLAPUnavailable("CLAP checkpoint is not prepared; set VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT")
        try:
            import laion_clap
        except Exception as exc:
            raise CLAPUnavailable(f"laion-clap runtime unavailable in isolated worker: {exc}") from exc
        requested = os.environ.get("VIDEO_AUDIO_ANALYZER_CLAP_DEVICE")
        if requested:
            device = requested
        else:
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        self.model = laion_clap.CLAP_Module(enable_fusion=False, device=device)
        self.model.load_ckpt(str(self.checkpoint))

    def text(self, texts: list[str]) -> list[list[float]]:
        return self.model.get_text_embedding(texts, use_tensor=False).tolist()

    def audio(self, paths: list[str | Path]) -> list[list[float]]:
        return self.model.get_audio_embedding_from_filelist([str(path) for path in paths], use_tensor=False).tolist()


class RemoteCLAPAdapter:
    """Call the isolated audio-model worker without importing its dependencies."""
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def text(self, texts: list[str]) -> list[list[float]]:
        import requests
        output: list[list[float]] = []
        for offset in range(0, len(texts), 256):
            response = requests.post(self.base_url + "/api/clap/text", json={"texts": texts[offset:offset + 256]}, timeout=600)
            response.raise_for_status()
            output.extend(response.json()["embeddings"])
        return output

    def audio(self, paths: list[str | Path]) -> list[list[float]]:
        import requests
        output: list[list[float]] = []
        for offset in range(0, len(paths), 256):
            batch = paths[offset:offset + 256]
            handles = [open(path, "rb") for path in batch]
            try:
                files = [("files", (Path(path).name, handle, "audio/wav")) for path, handle in zip(batch, handles)]
                response = requests.post(self.base_url + "/api/clap/audio", files=files, timeout=1200)
                response.raise_for_status()
                output.extend(response.json()["embeddings"])
            finally:
                for handle in handles:
                    handle.close()
        return output


@lru_cache(maxsize=1)
def configured_adapter() -> CLAPAdapter | RemoteCLAPAdapter:
    """Load weights once per worker process, not once per search request."""
    remote = os.environ.get("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL")
    if remote:
        return RemoteCLAPAdapter(remote)
    return CLAPAdapter(os.environ.get("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT", ""))


def late_fusion(pe_scores: list[float], clap_scores_by_id: dict[str, float], record_ids: list[str],
                pe_weight: float = 0.65) -> list[float]:
    """Fuse normalized scores only; vector spaces are never concatenated."""
    weight = min(1.0, max(0.0, float(pe_weight)))
    clap = [float(clap_scores_by_id.get(key, 0.0)) for key in record_ids]
    if not clap_scores_by_id:
        return list(pe_scores)
    def norm(values: list[float]) -> list[float]:
        lo, hi = min(values, default=0.0), max(values, default=0.0)
        return [0.0 if hi == lo else (v - lo) / (hi - lo) for v in values]
    pn, cn = norm(pe_scores), norm(clap)
    return [weight * p + (1.0 - weight) * c for p, c in zip(pn, cn)]
