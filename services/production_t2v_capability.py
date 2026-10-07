"""Fail-closed preflight for the separately tested H3 T2V production route."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from story_builder.services.audio_catalog import comfyui_root
from story_builder.services.minimax_h3_t2v import T2V_GRAPH_PATH, T2V_WORKFLOW_ID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURE_FLAG = "STORY_BUILDER_ENABLE_H3_T2V"
COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008")


def t2v_capability() -> dict[str, Any]:
    root = comfyui_root()
    required = {"graph": T2V_GRAPH_PATH,
        "unet": root / "models/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "text_encoder": root / "models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "video_vae": root / "models/vae/minimax_h3_video_vae_fp16.safetensors",
        "audio_vae": root / "models/vae/minimax_h3_audio_vae_fp32.safetensors"}
    missing = [name for name, path in required.items() if not path.is_file()]
    graph_ok = False
    try:
        graph = json.loads(T2V_GRAPH_PATH.read_text(encoding="utf-8"))
        kinds = [n.get("class_type") for n in graph.values() if isinstance(n, dict)]
        graph_ok = all(kinds.count(kind) >= count for kind, count in {
            "MiniMaxH3ImageToVideo": 1, "BasicScheduler": 1, "RandomNoise": 1,
            "SaveVideo": 1, "CreateVideo": 1}.items())
    except (OSError, json.JSONDecodeError):
        pass
    smoke_path = PROJECT_ROOT / "output/disposable-h3-t2v-smoke/manifest.json"
    smoke = None
    try:
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    enabled = os.environ.get(FEATURE_FLAG, "0").strip().lower() in {"1", "true", "yes", "on"}
    smoke_output_verified = False
    if isinstance(smoke, dict) and smoke.get("status") == "completed" and smoke.get("has_video") is True and smoke.get("has_audio") is True:
        for item in smoke.get("outputs", []):
            if not isinstance(item, dict) or item.get("kind") != "video":
                continue
            try:
                output = (smoke_path.parent / str(item["relative_path"])).resolve()
                output.relative_to(smoke_path.parent.resolve())
                actual_hash = hashlib.sha256(output.read_bytes()).hexdigest()
                probe = item.get("probe", {})
                streams = probe.get("streams", []) if isinstance(probe, dict) else []
                stream_types = {row.get("codec_type") for row in streams if isinstance(row, dict)}
                if (output.is_file() and actual_hash == item.get("sha256")
                        and {"video", "audio"}.issubset(stream_types)):
                    smoke_output_verified = True
                    break
            except (OSError, KeyError, ValueError, TypeError):
                continue
    passed = isinstance(smoke, dict) and smoke.get("status") == "completed" and smoke.get("has_video") is True and smoke.get("has_audio") is True and smoke_output_verified
    reachable = False
    missing_nodes: list[str] = []
    comfy_error = None
    try:
        # The installed node catalog is several MB; a heavy render can delay this
        # read beyond 1.5 seconds. Keep it bounded without inferring readiness.
        with urlopen(f"{COMFY_URL.rstrip('/')}/object_info", timeout=5) as response:
            info = json.loads(response.read().decode("utf-8"))
        reachable = isinstance(info, dict)
        if reachable:
            missing_nodes = sorted({"MiniMaxH3ImageToVideo", "CreateVideo", "SaveVideo", "BasicScheduler", "RandomNoise"} - set(info))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        comfy_error = f"ComfyUI T2V node preflight unavailable: {type(exc).__name__}: {exc}"
    reasons = []
    if missing: reasons.append("Required local T2V graph/model files are missing: " + ", ".join(missing))
    if not graph_ok: reasons.append("The installed H3 T2V graph contract is invalid.")
    if not reachable: reasons.append(comfy_error or "ComfyUI object_info is unavailable.")
    elif missing_nodes: reasons.append("Required H3 T2V ComfyUI nodes are missing: " + ", ".join(missing_nodes))
    if not enabled: reasons.append(f"Opt-in feature flag {FEATURE_FLAG}=1 is not set.")
    if not passed: reasons.append("No successful disposable H3 T2V video+audio smoke with an intact, hash-verified output is recorded.")
    return {"workflow_id": T2V_WORKFLOW_ID, "workflow_version": 1,
        "label": "MiniMax H3 · Text to video", "available": not missing and graph_ok and reachable and not missing_nodes and enabled and passed,
        "feature_enabled": enabled, "disabled_reason": None if not reasons else " ".join(reasons),
        "workflow_family": "minimax_h3_t2v_local_v1", "base_graph": "workflows/api/minimax_h3_t2v_api.json",
        "accepted_slots": {"images": {"min": 0, "max": 0}, "videos": {"min": 0, "max": 0}, "standalone_audios": {"min": 0, "max": 0}},
        "local_files": {name: {"path": str(path), "present": path.is_file()} for name, path in required.items()},
        "comfyui": {"reachable": reachable, "missing_nodes": missing_nodes, "error": comfy_error},
        "live_smoke": smoke}
