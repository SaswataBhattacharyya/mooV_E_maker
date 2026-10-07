"""Capability catalog for the opt-in dynamic H3 production path.

The catalog is intentionally read-only: merely listing a workflow never
submits a ComfyUI graph or loads a model.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

from story_builder.services.audio_catalog import comfyui_root


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ID = "minimax_h3_r2v_dynamic_v1"
COMPILER_VERSION = "1.0.0"
FEATURE_FLAG = "STORY_BUILDER_ENABLE_DYNAMIC_H3"


def _enabled() -> bool:
    return os.environ.get(FEATURE_FLAG, "0").strip().lower() in {"1", "true", "yes", "on"}


def _last_live_smoke() -> dict[str, Any] | None:
    runs = PROJECT_ROOT / "output" / "disposable-h3-reference-smoke" / "runs"
    candidates = sorted(runs.glob("phase-a-*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("status") in {"completed", "failed"}:
            output = next((row for row in data.get("outputs", []) if row.get("kind") == "video"), {})
            probe = output.get("probe", {})
            return {
                "status": data.get("status"),
                "run_id": data.get("run_id"),
                "resolution": [probe.get("width"), probe.get("height")] if probe else None,
                "fps": probe.get("fps"),
                "duration_seconds": probe.get("duration_seconds"),
                "has_audio": probe.get("has_audio"),
                "note": "One live input combination only; this does not certify all slot combinations.",
            }
    return None


def dynamic_h3_capability() -> dict[str, Any]:
    """Return honest local readiness and a fail-closed activation state."""
    comfy_root = comfyui_root()
    required_files = {
        "base_graph": PROJECT_ROOT / "workflows" / "api" / "minimax_h3_r2v_api.json",
        "unet": comfy_root / "models" / "diffusion_models" / "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "text_encoder": comfy_root / "models" / "text_encoders" / "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "video_vae": comfy_root / "models" / "vae" / "minimax_h3_video_vae_fp16.safetensors",
        "audio_vae": comfy_root / "models" / "vae" / "minimax_h3_audio_vae_fp32.safetensors",
    }
    missing = [name for name, path in required_files.items() if not path.is_file()]
    feature_enabled = _enabled()
    last_smoke = _last_live_smoke()
    reasons: list[str] = []
    if missing:
        reasons.append("Required local graph/model files are missing: " + ", ".join(missing))
    if not feature_enabled:
        reasons.append(f"Opt-in feature flag {FEATURE_FLAG}=1 is not set.")
    if not last_smoke or last_smoke.get("status") != "completed" or last_smoke.get("has_audio") is not True:
        reasons.append("No successful live H3 video+audio smoke is recorded.")
    available = feature_enabled and not missing and bool(last_smoke and last_smoke.get("status") == "completed" and last_smoke.get("has_audio") is True)
    return {
        "workflow_id": WORKFLOW_ID,
        "workflow_version": 1,
        "label": "MiniMax H3 · Dynamic references (experimental)",
        "available": available,
        "feature_enabled": feature_enabled,
        "disabled_reason": None if available else " ".join(reasons),
        "workflow_family": "minimax_h3_r2v_local_v1",
        "graph_compiler_version": COMPILER_VERSION,
        "base_graph": "workflows/api/minimax_h3_r2v_api.json",
        "accepted_slots": {
            "images": {"min": 0, "max": 9},
            "videos": {"min": 0, "max": 3, "paired_audio_from_same_loader": True},
            "standalone_audios": {"min": 0, "max": 3},
        },
        "settings": {
            "resolution_presets": {"0.98": [1344, 768], "0.4": [864, 480]},
            "fps": 24,
            "duration_seconds": {"min": 5, "max": 15},
            "steps": {"default": 20, "min": 8, "max": 40},
            "ref_image_size": ["match", "max"],
        },
        "local_files": {name: {"path": str(path), "present": path.is_file()} for name, path in required_files.items()},
        "last_live_smoke": last_smoke,
    }
