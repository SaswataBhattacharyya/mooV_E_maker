"""Typed, fail-closed adapters for the project's ComfyUI image workflows.

This module only prepares graphs and reports readiness. It does not submit a
ComfyUI prompt or load a model; job dispatch is owned by the production worker.
"""
from __future__ import annotations

import copy
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from story_builder.services.audio_catalog import comfyui_root


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:3008").rstrip("/")
SMOKE_ROOT = PROJECT_ROOT / "storage" / "production" / "image_workflow_smokes"
SAFE_STAGED_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,180}$")
U32_MAX = 0xFFFFFFFF

SPECS: dict[str, dict[str, Any]] = {
    "qwen_image_2512": {
        "label": "Qwen Image 2512 · text to image", "version": "1",
        "graph": "qwen_2512_t2i_api.json", "models": {
            "diffusion_model": ("diffusion_models", "qwen_image_2512_bf16.safetensors"),
            "text_encoder": ("text_encoders", "qwen_2.5_vl_7b_fp8_scaled.safetensors"),
            "vae": ("vae", "qwen_image_vae.safetensors")},
        "required_nodes": ["UNETLoader", "CLIPLoader", "VAELoader", "KSampler", "CLIPTextEncode", "SaveImage"],
        "defaults": {"width": 1664, "height": 928, "steps": 50, "cfg": 4.0},
    },
    "z_image_turbo": {
        "label": "Z-Image Turbo · text to image", "version": "1",
        "graph": "gsl_starter_1_1_api.json", "models": {
            "diffusion_model": ("diffusion_models", "z_image_turbo_bf16.safetensors"),
            "text_encoder": ("text_encoders", "qwen_3_4b.safetensors"),
            "vae": ("vae", "ae.safetensors")},
        "required_nodes": ["UNETLoader", "CLIPLoader", "VAELoader", "KSampler", "CLIPTextEncode", "SaveImage"],
        "defaults": {"width": 1280, "height": 720, "steps": 8, "cfg": 1.0},
    },
    "qwen_image_edit_2511": {
        "label": "Qwen Image Edit 2511 · image edit (4-step Lightning)", "version": "1",
        "graph": "qwen_edit_2511_api.json", "models": {
            "diffusion_model": ("diffusion_models", "qwen_image_edit_2511_bf16.safetensors"),
            "text_encoder": ("text_encoders", "qwen_2.5_vl_7b_fp8_scaled.safetensors"),
            "vae": ("vae", "qwen_image_vae.safetensors"),
            "lightning_lora": ("loras", "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors")},
        "required_nodes": ["UNETLoader", "CLIPLoader", "VAELoader", "KSampler", "TextEncodeQwenImageEditPlus", "FluxKontextMultiReferenceLatentMethod", "LoraLoaderModelOnly", "SaveImage"],
        "defaults": {"width": 1024, "height": 1024, "steps": 4, "cfg": 1.0},
    },
}


class ImageWorkflowError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def generation_policy(control_mode: str, *, full_retake_budget: int = 2) -> dict[str, int | str]:
    if control_mode in {"manual", "semi", "semi_automated"}:
        return {"initial_candidates": 4, "full_retake_budget": 0,
                "selection_authority": "user"}
    if control_mode == "fully_automated":
        if not isinstance(full_retake_budget, int) or not 0 <= full_retake_budget <= 4:
            raise ImageWorkflowError("invalid_retake_budget", "Full-mode image retake budget must be from 0 to 4.")
        return {"initial_candidates": 1, "full_retake_budget": full_retake_budget,
                "selection_authority": "director"}
    raise ImageWorkflowError("invalid_control_mode", "Choose manual, semi, semi_automated, or fully_automated.")


def _read_smoke(smoke_root: Path, workflow_id: str) -> dict[str, Any] | None:
    path = smoke_root / f"{workflow_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("workflow_id") != workflow_id or data.get("status") != "passed":
        return None
    return data


def image_workflow_catalog(*, comfy_root: Path | None = None, workflow_root: Path | None = None,
                           smoke_root: Path | None = None,
                           comfy_url: str | None = None,
                           object_info: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Report model/file/node/smoke readiness without executing any workflow."""
    models_root = Path(comfy_root or comfyui_root()) / "models"
    graphs_root = Path(workflow_root or (PROJECT_ROOT / "workflows" / "api"))
    evidence_root = Path(smoke_root or SMOKE_ROOT)
    url = (comfy_url or COMFYUI_BASE_URL).rstrip("/")
    live_info = object_info
    comfy_online = live_info is not None
    connection_error = None
    if live_info is None:
        try:
            with urllib.request.urlopen(url + "/object_info", timeout=1.5) as response:
                live_info = json.loads(response.read())
            comfy_online = isinstance(live_info, dict)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            connection_error = f"ComfyUI object_info unavailable at {url}: {exc}"
            live_info = {}
    entries = []
    for workflow_id, spec in SPECS.items():
        graph_path = graphs_root / spec["graph"]
        missing_models = [key for key, (folder, filename) in spec["models"].items()
                          if not (models_root / folder / filename).is_file()]
        present_nodes = live_info if isinstance(live_info, Mapping) else {}
        missing_nodes = [name for name in spec["required_nodes"] if name not in present_nodes] if comfy_online else list(spec["required_nodes"])
        smoke = _read_smoke(evidence_root, workflow_id)
        reasons = []
        if not graph_path.is_file():
            reasons.append(f"Versioned API graph is missing: {graph_path.name}.")
        if missing_models:
            reasons.append("Missing model files: " + ", ".join(missing_models) + ".")
        if not comfy_online:
            reasons.append(connection_error or "ComfyUI is offline; live node capabilities are unknown.")
        elif missing_nodes:
            reasons.append("Required ComfyUI nodes are missing: " + ", ".join(missing_nodes) + ".")
        if smoke is None:
            reasons.append("No successful disposable live smoke is recorded for this exact workflow version.")
        available = graph_path.is_file() and not missing_models and comfy_online and not missing_nodes and smoke is not None
        entries.append({"workflow_id": workflow_id, "label": spec["label"], "version": spec["version"],
            "available": available, "disabled_reason": None if available else " ".join(reasons),
            "graph": f"workflows/api/{spec['graph']}",
            "models": {key: {"folder": folder, "filename": filename,
                "present": (models_root / folder / filename).is_file()}
                for key, (folder, filename) in spec["models"].items()},
            "missing_nodes": missing_nodes if comfy_online else None,
            "comfyui_online": comfy_online, "live_smoke": smoke,
            "defaults": dict(spec["defaults"])})
    return {"schema_version": 1, "workflows": entries,
            "generation_policy": {"manual_and_semi": {"initial_candidates": 4, "selection_authority": "user"},
                "fully_automated": {"initial_candidates": 1, "bounded_retake_budget": [0, 4], "selection_authority": "director"}}}


def _safe_basename(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not SAFE_STAGED_NAME.fullmatch(value) or Path(value).name != value or value in {".", ".."}:
        raise ImageWorkflowError("unsafe_staged_name", f"{field} must be a staged basename, never a path.")
    return value


def _safe_output_prefix(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 180 or "\\" in value
            or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(not SAFE_STAGED_NAME.fullmatch(part) for part in value.split("/"))):
        raise ImageWorkflowError("unsafe_output_prefix", "output_prefix must be a safe relative ComfyUI output path.")
    return value


def _positive_int(value: int, field: str, low: int, high: int, *, multiple: int = 1) -> None:
    if not isinstance(value, int) or not low <= value <= high or value % multiple:
        raise ImageWorkflowError("invalid_image_setting", f"{field} must be {low}–{high} and divisible by {multiple}.")


def compile_image_candidates(*, workflow_id: str, prompt: str, control_mode: str, seed: int,
                             output_prefix: str, width: int | None = None, height: int | None = None,
                             steps: int | None = None, cfg: float | None = None,
                             source_images: list[str] | None = None,
                             workflow_root: Path | None = None,
                             full_retake_budget: int = 2) -> dict[str, Any]:
    """Compile safe independent candidates; caller owns project-asset staging/dispatch."""
    if workflow_id not in SPECS:
        raise ImageWorkflowError("unknown_image_workflow", f"Unknown image workflow {workflow_id!r}.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise ImageWorkflowError("invalid_image_prompt", "Image prompt must contain 1–20,000 characters.")
    if not isinstance(seed, int) or not 0 <= seed <= U32_MAX:
        raise ImageWorkflowError("invalid_image_seed", "Image seed must be an unsigned 32-bit integer.")
    policy = generation_policy(control_mode, full_retake_budget=full_retake_budget)
    spec = SPECS[workflow_id]
    defaults = spec["defaults"]
    width = defaults["width"] if width is None else width
    height = defaults["height"] if height is None else height
    steps = defaults["steps"] if steps is None else steps
    cfg = defaults["cfg"] if cfg is None else cfg
    _positive_int(width, "width", 256, 2048, multiple=8)
    _positive_int(height, "height", 256, 2048, multiple=8)
    step_limits = (4, 16) if workflow_id == "z_image_turbo" or workflow_id == "qwen_image_edit_2511" else (20, 80)
    _positive_int(steps, "steps", *step_limits)
    cfg_max = 2.0 if workflow_id == "z_image_turbo" else 8.0
    if not isinstance(cfg, (float, int)) or not 0.1 <= float(cfg) <= cfg_max:
        raise ImageWorkflowError("invalid_image_setting", f"cfg must be from 0.1 to {cfg_max} for {workflow_id}.")
    prefix = _safe_output_prefix(output_prefix)
    names = [_safe_basename(name, field="source_images[]") for name in (source_images or [])]
    if workflow_id == "qwen_image_edit_2511" and not 1 <= len(names) <= 3:
        raise ImageWorkflowError("edit_source_required", "Qwen Image Edit 2511 requires a primary image and accepts at most two additional references.")
    if workflow_id != "qwen_image_edit_2511" and names:
        raise ImageWorkflowError("unexpected_edit_sources", "Text-to-image workflows do not accept source images.")
    graph_path = Path(workflow_root or (PROJECT_ROOT / "workflows" / "api")) / spec["graph"]
    try:
        base = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImageWorkflowError("image_graph_unavailable", f"Could not read {spec['graph']}: {exc}") from exc

    def node(graph: dict[str, Any], node_id: str, expected_class: str) -> dict[str, Any]:
        value = graph.get(node_id)
        if not isinstance(value, dict) or value.get("class_type") != expected_class:
            raise ImageWorkflowError("image_graph_contract_mismatch", f"{spec['graph']} node {node_id} must be {expected_class}.")
        return value["inputs"]

    graphs = []
    count = int(policy["initial_candidates"])
    if seed + count - 1 > U32_MAX:
        raise ImageWorkflowError("candidate_seed_overflow", "Candidate seeds exceed unsigned 32-bit range.")
    for index in range(count):
        graph = copy.deepcopy(base)
        candidate_seed = seed + index
        if workflow_id == "qwen_image_2512":
            node(graph, "227", "CLIPTextEncode")["text"] = prompt.strip()
            sampler = node(graph, "230", "KSampler")
            sampler.update({"seed": candidate_seed, "steps": steps, "cfg": float(cfg)})
            node(graph, "232", "EmptySD3LatentImage").update({"width": width, "height": height, "batch_size": 1})
            node(graph, "60", "SaveImage")["filename_prefix"] = f"{prefix}/candidate-{index + 1}"
        elif workflow_id == "z_image_turbo":
            node(graph, "45", "CLIPTextEncode")["text"] = prompt.strip()
            sampler = node(graph, "44", "KSampler")
            sampler.update({"seed": candidate_seed, "steps": steps, "cfg": float(cfg)})
            node(graph, "41", "EmptySD3LatentImage").update({"width": width, "height": height, "batch_size": 1})
            node(graph, "76", "SaveImage")["filename_prefix"] = f"{prefix}/candidate-{index + 1}"
        else:
            for node_id, filename in zip(("78", "120", "121"), names):
                node(graph, node_id, "LoadImage")["image"] = filename
            for node_id in ("120", "121"):
                if node_id not in names_by_slot(names):
                    graph.pop(node_id, None)
                    for encoder_id in ("111", "110"):
                        node(graph, encoder_id, "TextEncodeQwenImageEditPlus").pop(
                            "image2" if node_id == "120" else "image3", None)
            for encoder_id, text in (("111", prompt.strip()), ("110", "low quality, extra limbs, unwanted drift, identity mismatch, broken perspective")):
                inputs = node(graph, encoder_id, "TextEncodeQwenImageEditPlus")
                inputs["prompt"] = text
                inputs["image1"] = ["93", 0]
            sampler = node(graph, "3", "KSampler")
            sampler.update({"seed": candidate_seed, "steps": steps, "cfg": float(cfg)})
            node(graph, "60", "SaveImage")["filename_prefix"] = f"{prefix}/candidate-{index + 1}"
            scale = node(graph, "93", "ImageScaleToTotalPixels")
            scale["megapixels"] = min(2.0, max(0.3, round(width * height / 1_000_000, 2)))
        graphs.append({"candidate_index": index + 1, "seed": candidate_seed, "graph": graph})
    return {"workflow_id": workflow_id, "workflow_version": spec["version"],
            "control_mode": control_mode, "initial_candidate_count": count,
            "full_retake_budget": int(policy["full_retake_budget"]),
            "selection_authority": policy["selection_authority"], "prompt": prompt.strip(),
            "settings": {"width": width, "height": height, "steps": steps, "cfg": float(cfg)},
            "candidates": graphs}


def names_by_slot(names: list[str]) -> set[str]:
    """Return connected optional image node IDs for one-to-three edit inputs."""
    return {node_id for node_id, _name in zip(("78", "120", "121"), names)}


def image_output_provenance(*, project_id: str, run_id: str, asset_role: str,
                            workflow_id: str, prompt: str, seed: int,
                            settings: Mapping[str, Any], candidate_index: int,
                            accepted: bool = False) -> dict[str, Any]:
    if workflow_id not in SPECS or candidate_index < 1:
        raise ImageWorkflowError("invalid_image_provenance", "Workflow ID and positive candidate index are required.")
    return {"schema_version": 1, "project_id": project_id, "run_id": run_id,
            "asset_role": asset_role, "workflow_id": workflow_id,
            "workflow_version": SPECS[workflow_id]["version"], "prompt": prompt,
            "seed": seed, "settings": dict(settings), "candidate_index": candidate_index,
            "accepted": bool(accepted)}
