"""Read-only preflight for the existing local H3 first/last-frame API graph."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from story_builder.services.audio_catalog import comfyui_root


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ID = "minimax_h3_fl2va_first_last_v1"


def fl2va_capability(comfy_url: str, *, timeout: float = 1.5) -> dict[str, Any]:
    graph = PROJECT_ROOT / "workflows" / "api" / "minimax_h3_i2v_api.json"
    root = comfyui_root()
    required = {
        "base_graph": graph,
        "fl2va_unet": root / "models" / "diffusion_models" / "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "video_vae": root / "models" / "vae" / "minimax_h3_video_vae_fp16.safetensors",
        "text_encoder": root / "models" / "text_encoders" / "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    }
    missing = [key for key, path in required.items() if not path.is_file()]
    graph_contract_error = None
    try:
        graph_data = json.loads(graph.read_text(encoding="utf-8"))
        graph_types = [node.get("class_type") for node in graph_data.values() if isinstance(node, dict)]
        if ("MiniMaxH3ImageToVideo" not in graph_types or graph_types.count("LoadImage") < 2
                or "SaveVideo" not in graph_types):
            graph_contract_error = "The API graph does not contain the expected FL2VA first/last, input and save nodes."
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        graph_contract_error = f"The FL2VA API graph could not be validated: {type(exc).__name__}: {exc}"
    reachable = False
    nodes: set[str] = set()
    error = None
    try:
        with urlopen(f"{comfy_url.rstrip('/')}/object_info", timeout=timeout) as response:
            object_info = json.loads(response.read().decode("utf-8"))
        if isinstance(object_info, dict):
            nodes = set(object_info)
            reachable = True
        else:
            error = "ComfyUI returned an invalid object_info document."
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        error = f"ComfyUI node preflight unavailable: {type(exc).__name__}: {exc}"
    needed_nodes = {"MiniMaxH3ImageToVideo", "LoadImage", "CreateVideo", "SaveVideo"}
    missing_nodes = sorted(needed_nodes - nodes) if reachable else sorted(needed_nodes)
    smoke_path = PROJECT_ROOT / "output" / "disposable-h3-fl2va-smoke" / "manifest.json"
    smoke = None
    if smoke_path.is_file():
        try:
            smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            smoke = {"status": "invalid_manifest"}
    enabled = os.environ.get("STORY_BUILDER_ENABLE_FL2VA", "0").strip().lower() in {"1", "true", "yes", "on"}
    passed_smoke = isinstance(smoke, dict) and smoke.get("status") == "completed" and smoke.get("has_video") is True
    reasons = []
    if missing:
        reasons.append("Required graph/checkpoint files are missing: " + ", ".join(missing))
    if graph_contract_error:
        reasons.append(graph_contract_error)
    if not reachable:
        reasons.append(error or "ComfyUI is offline.")
    elif missing_nodes:
        reasons.append("Required ComfyUI nodes are missing: " + ", ".join(missing_nodes))
    if not enabled:
        reasons.append("Opt-in feature flag STORY_BUILDER_ENABLE_FL2VA=1 is not set.")
    if not passed_smoke:
        reasons.append("No successful disposable FL2VA first/last-frame render is recorded.")
    available = not missing and not graph_contract_error and reachable and not missing_nodes and enabled and passed_smoke
    return {
        "workflow_id": WORKFLOW_ID,
        "workflow_version": 1,
        "label": "MiniMax H3 · First/last frame (FL2VA)",
        "workflow_family": "minimax_h3_fl2va_local_v1",
        "available": available,
        "feature_enabled": enabled,
        "disabled_reason": None if available else " ".join(reasons),
        "base_graph": "workflows/api/minimax_h3_i2v_api.json",
        "graph_contract_error": graph_contract_error,
        "accepted_slots": {"first_frame": {"required": True}, "last_frame": {"required": True}},
        "settings": {"fps": 24, "resolution_presets": {"0.98": [1344, 768], "0.4": [864, 480]},
                     "duration_seconds": {"min": 5, "max": 15}},
        "local_files": {name: {"path": str(path), "present": path.is_file()} for name, path in required.items()},
        "comfyui": {"reachable": reachable, "missing_nodes": missing_nodes, "error": error},
        "live_smoke": smoke,
    }
