from __future__ import annotations

import io
import json

from story_builder.services import production_fl2va_capability as capability


def test_fl2va_preflight_is_truthful_and_offline_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(capability, "PROJECT_ROOT", tmp_path)
    root = tmp_path / "comfy"
    monkeypatch.setattr(capability, "comfyui_root", lambda: root)
    graph = tmp_path / "workflows" / "api" / "minimax_h3_i2v_api.json"
    graph.parent.mkdir(parents=True)
    graph.write_text(json.dumps({"a": {"class_type": "LoadImage"}, "b": {"class_type": "LoadImage"},
        "c": {"class_type": "MiniMaxH3ImageToVideo"}, "d": {"class_type": "SaveVideo"}}))
    monkeypatch.setattr(capability, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(ConnectionError("offline")))
    result = capability.fl2va_capability("http://comfy", timeout=0.01)
    assert result["available"] is False
    assert result["comfyui"]["reachable"] is False
    assert "ComfyUI node preflight unavailable" in result["disabled_reason"]


def test_fl2va_preflight_requires_live_nodes_feature_flag_and_exact_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(capability, "PROJECT_ROOT", tmp_path)
    root = tmp_path / "comfy"
    monkeypatch.setattr(capability, "comfyui_root", lambda: root)
    graph = tmp_path / "workflows" / "api" / "minimax_h3_i2v_api.json"
    graph.parent.mkdir(parents=True)
    graph.write_text(json.dumps({"a": {"class_type": "LoadImage"}, "b": {"class_type": "LoadImage"},
        "c": {"class_type": "MiniMaxH3ImageToVideo"}, "d": {"class_type": "SaveVideo"}}))
    for name, relative in {
        "fl2va_unet": "models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "video_vae": "models/vae/minimax_h3_video_vae_fp16.safetensors",
        "text_encoder": "models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")
    smoke = tmp_path / "output/disposable-h3-fl2va-smoke/manifest.json"
    smoke.parent.mkdir(parents=True)
    smoke.write_text(json.dumps({"status": "completed", "has_video": True}))
    monkeypatch.setenv("STORY_BUILDER_ENABLE_FL2VA", "1")

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def read(self):
            return json.dumps({"MiniMaxH3ImageToVideo": {}, "LoadImage": {}, "CreateVideo": {}, "SaveVideo": {}}).encode()

    monkeypatch.setattr(capability, "urlopen", lambda *_a, **_k: Response())
    result = capability.fl2va_capability("http://comfy")
    assert result["available"] is True
    assert result["accepted_slots"] == {"first_frame": {"required": True}, "last_frame": {"required": True}}


def test_fl2va_preflight_rejects_wrong_graph_even_when_comfy_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(capability, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(capability, "comfyui_root", lambda: tmp_path / "comfy")
    graph = tmp_path / "workflows" / "api" / "minimax_h3_i2v_api.json"
    graph.parent.mkdir(parents=True)
    graph.write_text(json.dumps({"a": {"class_type": "LoadImage"}, "b": {"class_type": "SaveVideo"}}))
    monkeypatch.setattr(capability, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(ConnectionError("offline")))
    result = capability.fl2va_capability("http://comfy")
    assert result["graph_contract_error"]
    assert result["available"] is False
