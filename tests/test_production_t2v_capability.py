from __future__ import annotations

import json
import io
import hashlib
from pathlib import Path

from story_builder.services import production_t2v_capability as capability


def test_t2v_capability_is_unavailable_until_explicit_smoke_and_flag(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    graph_path = project / "workflows/api/minimax_h3_t2v_api.json"
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text(json.dumps({"1": {"class_type": "MiniMaxH3ImageToVideo"},
        "2": {"class_type": "BasicScheduler"}, "3": {"class_type": "RandomNoise"},
        "4": {"class_type": "CreateVideo"}, "5": {"class_type": "SaveVideo"}}))
    comfy = tmp_path / "comfy"
    for relative in ("models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "models/vae/minimax_h3_video_vae_fp16.safetensors",
        "models/vae/minimax_h3_audio_vae_fp32.safetensors"):
        path = comfy / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(capability, "PROJECT_ROOT", project)
    monkeypatch.setattr(capability, "T2V_GRAPH_PATH", graph_path)
    monkeypatch.setattr(capability, "comfyui_root", lambda: comfy)
    monkeypatch.setattr(capability, "urlopen", lambda *_a, **_k: io.BytesIO(json.dumps({
        name: {} for name in ("MiniMaxH3ImageToVideo", "CreateVideo", "SaveVideo", "BasicScheduler", "RandomNoise")}).encode()))
    monkeypatch.setenv(capability.FEATURE_FLAG, "1")
    result = capability.t2v_capability()
    assert result["available"] is False
    assert "No successful disposable H3 T2V" in result["disabled_reason"]
    (project / "output/disposable-h3-t2v-smoke").mkdir(parents=True)
    smoke_root = project / "output/disposable-h3-t2v-smoke"
    video = smoke_root / "run/media/smoke.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"smoke-video-audio")
    (smoke_root / "manifest.json").write_text(json.dumps({
        "status": "completed", "has_video": True, "has_audio": True,
        "outputs": [{"kind": "video", "relative_path": "run/media/smoke.mp4",
            "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "probe": {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}}]}))
    assert capability.t2v_capability()["available"] is True
    video.write_bytes(b"modified")
    assert capability.t2v_capability()["available"] is False


def test_t2v_readiness_timeout_stays_bounded_and_unavailable(monkeypatch):
    observed = []
    def unavailable(url, *, timeout):
        observed.append(timeout)
        raise TimeoutError("busy node catalog")
    monkeypatch.setattr(capability, "urlopen", unavailable)
    result = capability.t2v_capability()
    assert observed == [5]
    assert result["available"] is False
    assert result["comfyui"]["reachable"] is False
    assert "TimeoutError: busy node catalog" in result["disabled_reason"]
