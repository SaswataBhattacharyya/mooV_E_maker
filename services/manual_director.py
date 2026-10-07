"""Manual, workflow-aware ComfyUI runs stored in the shared video repertoire.

This adapter deliberately limits itself to the known API workflows in
``workflows/api``. It never edits ComfyUI nodes or installs packages.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from story_builder.services.audio_catalog import comfyui_root
from story_builder.services.media_jobs import collect_outputs, submit_and_wait
from story_builder.services.video_repertoire import REPERTOIRE_ROOT, safe_path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_ROOT = PROJECT_ROOT / "workflows" / "api"
MANUAL_ROOT = REPERTOIRE_ROOT / "manual"
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_IMAGE_BYTES = 40 * 1024 * 1024
MAX_AUDIO_BYTES = 200 * 1024 * 1024
MAX_VIDEO_BYTES = 500 * 1024 * 1024
WORKFLOWS: dict[str, dict[str, Any]] = {
    "minimax_text": {
        "file": "minimax_h3_t2v_api.json", "label": "Minimax H3 · Text only",
        "accepted_slots": [], "required_slots": [], "fps": 24,
        "description": "Text-to-video with generated audio; no media reference inputs.",
    },
    "minimax_references": {
        "file": "minimax_h3_r2v_api.json", "label": "Minimax H3 · Reference images",
        "accepted_slots": ["reference_images"], "required_slots": ["reference_images"], "fps": 24,
        "description": "Accepts 1–3 reference images. This installed graph does not accept reference audio or video.",
    },
    "wan_first_last": {
        "file": "wan2_2_flf2v_api.json", "label": "WAN 2.2 · First + last frame",
        "accepted_slots": ["first_frame", "last_frame"], "required_slots": ["first_frame", "last_frame"], "fps": 16,
        "description": "Requires first and last frame images. This installed graph does not accept reference audio or video.",
    },
}
SLOT_TYPES = {
    "reference_images": {"image"}, "first_frame": {"image"}, "last_frame": {"image"},
    "audio": {"audio"}, "video": {"video"},
}
EXTENSIONS = {
    "image": {".png", ".jpg", ".jpeg", ".webp"},
    "audio": {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"},
    "video": {".mp4", ".mov", ".mkv", ".webm", ".m4v"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _load_workflow(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError(f"Workflow is empty or not an API prompt graph: {path.name}")
    return data


def _nodes(workflow: dict[str, Any], class_type: str) -> list[tuple[str, dict[str, Any]]]:
    return sorted(((str(node_id), node) for node_id, node in workflow.items()
                   if isinstance(node, dict) and node.get("class_type") == class_type),
                  key=lambda row: int(row[0]) if row[0].isdigit() else row[0])


def _param_schema(workflow: dict[str, Any], workflow_id: str) -> list[dict[str, Any]]:
    controls: dict[str, dict[str, Any]] = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        cls, inputs = str(node.get("class_type", "")), node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for key in ("width", "height", "length"):
            if isinstance(inputs.get(key), (int, float)):
                controls["duration_seconds" if key == "length" else key] = {
                    "key": "duration_seconds" if key == "length" else key,
                    "label": "Duration (seconds)" if key == "length" else key.title(),
                    "kind": "number", "default": inputs[key] / (24 if workflow_id.startswith("minimax") else 16) if key == "length" else inputs[key],
                    "min": 2 if key == "length" else 256, "max": 10 if key == "length" else 1920,
                    "step": 0.1 if key == "length" else 64,
                    "description": "Converted to workflow frame count." if key == "length" else "Must be a multiple of 64.",
                }
        if cls == "BasicScheduler" and isinstance(inputs.get("steps"), (int, float)):
            controls["steps"] = {"key": "steps", "label": "Quality / sampler steps", "kind": "number",
                "default": inputs["steps"], "min": 8, "max": 40, "step": 1,
                "description": "More steps can improve refinement and take longer."}
        if cls == "KSamplerAdvanced" and isinstance(inputs.get("steps"), (int, float)):
            controls["steps"] = {"key": "steps", "label": "Quality / sampler steps", "kind": "number",
                "default": inputs["steps"], "min": 8, "max": 40, "step": 1,
                "description": "More steps can improve refinement and take longer."}
        if "noise_seed" in inputs:
            controls["seed"] = {"key": "seed", "label": "Seed", "kind": "number",
                "default": inputs["noise_seed"], "min": 0, "max": 4294967295, "step": 1}
    return list(controls.values())


def workflow_catalog() -> list[dict[str, Any]]:
    result = []
    for workflow_id, config in WORKFLOWS.items():
        path = WORKFLOW_ROOT / config["file"]
        available = path.is_file()
        item: dict[str, Any] = {"workflow_id": workflow_id, "label": config["label"],
            "available": available, "file": config["file"], "accepted_slots": config["accepted_slots"],
            "required_slots": config["required_slots"], "fps": config["fps"],
            "description": config["description"], "parameters": [], "reference_limits": {}}
        if available:
            graph = _load_workflow(path)
            loads = _nodes(graph, "LoadImage")
            if workflow_id == "minimax_references":
                item["reference_limits"] = {"reference_images": {"min": 1, "max": min(3, len(loads)), "max_bytes_each": MAX_IMAGE_BYTES}}
            elif workflow_id == "wan_first_last":
                item["reference_limits"] = {"first_frame": {"min": 1, "max": 1, "max_bytes_each": MAX_IMAGE_BYTES},
                    "last_frame": {"min": 1, "max": 1, "max_bytes_each": MAX_IMAGE_BYTES}}
            item["parameters"] = _param_schema(graph, workflow_id)
        result.append(item)
    return result


def _manual_dirs() -> tuple[Path, Path, Path, Path]:
    assets = REPERTOIRE_ROOT / "manual" / "assets"
    inputs = REPERTOIRE_ROOT / "manual" / "inputs"
    outputs = REPERTOIRE_ROOT / "manual" / "outputs"
    jobs = REPERTOIRE_ROOT / "manual" / "jobs"
    for path in (assets, inputs, outputs, jobs):
        path.mkdir(parents=True, exist_ok=True)
    return assets, inputs, outputs, jobs


def upload_asset(filename: str, content: bytes, slot: str) -> dict[str, Any]:
    if slot not in SLOT_TYPES:
        raise ValueError(f"Unsupported reference slot: {slot}")
    suffix = Path(filename or "upload.bin").suffix.lower()
    media_type = next((kind for kind, extensions in EXTENSIONS.items() if suffix in extensions), None)
    if media_type is None or media_type not in SLOT_TYPES[slot]:
        raise ValueError(f"File type {suffix or '(none)'} is not accepted by the {slot} slot")
    cap = MAX_IMAGE_BYTES if media_type == "image" else MAX_AUDIO_BYTES if media_type == "audio" else MAX_VIDEO_BYTES
    if len(content) > min(cap, MAX_UPLOAD_BYTES):
        raise ValueError(f"File exceeds this slot's {cap // (1024 * 1024)} MB upload limit")
    if not content:
        raise ValueError("Cannot add an empty file")
    assets_dir, _, _, _ = _manual_dirs()
    digest = hashlib.sha256(content).hexdigest()
    index_path = assets_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {"assets": []}
    existing = next((row for row in index["assets"] if row.get("sha256") == digest and row.get("media_type") == media_type), None)
    if existing:
        return existing
    asset_id = f"manual-{media_type}-{digest[:14]}"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._") or f"upload{suffix}"
    relative = f"manual/assets/{asset_id}_{safe_name}"
    path = safe_path(REPERTOIRE_ROOT / relative, REPERTOIRE_ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    row = {"asset_id": asset_id, "filename": safe_name, "relative_path": relative,
        "media_type": media_type, "size": len(content), "sha256": digest,
        "content_url": f"/api/video-repertoire/manual/assets/content/{relative}"}
    index["assets"].append(row)
    _json_write(index_path, index)
    return row


def list_manual_assets() -> list[dict[str, Any]]:
    assets_dir, _, _, _ = _manual_dirs()
    index_path = assets_dir / "index.json"
    if not index_path.is_file():
        return []
    try:
        rows = json.loads(index_path.read_text(encoding="utf-8")).get("assets", [])
    except (OSError, json.JSONDecodeError):
        return []
    return [row for row in rows if (REPERTOIRE_ROOT / row.get("relative_path", "")).is_file()]


def resolve_reference(reference: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Resolve a repertoire reference; never trust a client-supplied absolute path."""
    slot = str(reference.get("slot", ""))
    if slot not in SLOT_TYPES:
        raise ValueError(f"Unknown reference slot: {slot}")
    asset_id = str(reference.get("asset_id", ""))
    if asset_id.startswith("manual-"):
        row = next((item for item in list_manual_assets() if item.get("asset_id") == asset_id), None)
        if not row:
            raise FileNotFoundError(f"Manual asset no longer exists: {asset_id}")
        path = safe_path(REPERTOIRE_ROOT / row["relative_path"], REPERTOIRE_ROOT)
        media_type = row["media_type"]
    elif asset_id.startswith("video-"):
        from story_builder.services.video_repertoire import get_asset
        record = get_asset(asset_id)
        path = safe_path(Path(record["path"]), REPERTOIRE_ROOT)
        media_type = "video"
        row = {"asset_id": asset_id, "filename": path.name, "relative_path": path.relative_to(REPERTOIRE_ROOT).as_posix(), "media_type": media_type}
    else:
        relative = str(reference.get("relative_path", ""))
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Reference must use a safe video-repertoire relative path")
        path = safe_path(REPERTOIRE_ROOT / relative, REPERTOIRE_ROOT)
        media_type = next((kind for kind, suffixes in EXTENSIONS.items() if path.suffix.lower() in suffixes), None)
        row = {"asset_id": asset_id or relative, "filename": path.name, "relative_path": relative, "media_type": media_type}
    if media_type not in SLOT_TYPES[slot]:
        raise ValueError(f"{row.get('filename')} is {media_type or 'an unsupported format'}, not valid for {slot}")
    if not path.is_file():
        raise FileNotFoundError(f"Reference file does not exist: {row.get('filename')}")
    limit = MAX_IMAGE_BYTES if media_type == "image" else MAX_AUDIO_BYTES if media_type == "audio" else MAX_VIDEO_BYTES
    if path.stat().st_size > limit:
        raise ValueError(f"{row.get('filename')} is {path.stat().st_size // (1024 * 1024)} MB; this slot limit is {limit // (1024 * 1024)} MB")
    row.update({"slot": slot, "start_time_sec": reference.get("start_time_sec"), "end_time_sec": reference.get("end_time_sec")})
    return path, row


def validate_request(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[tuple[Path, dict[str, Any]]]]:
    workflow_id = str(payload.get("workflow_id", ""))
    config = WORKFLOWS.get(workflow_id)
    if not config:
        raise ValueError("Choose one of the supported Manual Director workflows")
    workflow_path = WORKFLOW_ROOT / config["file"]
    if not workflow_path.is_file():
        raise ValueError(f"Workflow is unavailable: {config['file']}")
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("A text prompt is required")
    refs = payload.get("references", [])
    if not isinstance(refs, list):
        raise ValueError("references must be a list")
    resolved = [resolve_reference(item) for item in refs]
    counts: dict[str, int] = {}
    for _, row in resolved:
        counts[row["slot"]] = counts.get(row["slot"], 0) + 1
        if row["slot"] not in config["accepted_slots"]:
            raise ValueError(f"{config['label']} cannot use the {row['slot']} reference. Remove it or choose a compatible workflow.")
    for slot in config["required_slots"]:
        if counts.get(slot, 0) == 0:
            raise ValueError(f"{config['label']} requires a {slot.replace('_', ' ')} reference")
    if workflow_id == "minimax_references" and not 1 <= counts.get("reference_images", 0) <= 3:
        raise ValueError("Minimax H3 reference-to-video needs between one and three reference images")
    params = payload.get("parameters", {})
    if not isinstance(params, dict):
        raise ValueError("parameters must be an object")
    schema = {row["key"]: row for row in _param_schema(_load_workflow(workflow_path), workflow_id)}
    clean_params: dict[str, Any] = {}
    for key, value in params.items():
        if key not in schema or value in (None, ""):
            if key not in schema:
                raise ValueError(f"Parameter {key} is not supported by this workflow")
            continue
        spec = schema[key]
        numeric = float(value)
        if numeric < spec["min"] or numeric > spec["max"]:
            raise ValueError(f"{spec['label']} must be between {spec['min']} and {spec['max']}")
        if key in {"width", "height"} and int(numeric) % 64:
            raise ValueError(f"{spec['label']} must be a multiple of 64")
        clean_params[key] = int(numeric) if spec["step"] == 1 or key in {"width", "height"} else numeric
    return config, {"prompt": prompt, "negative_prompt": str(payload.get("negative_prompt", "")).strip(),
                    "parameters": clean_params, "workflow_id": workflow_id}, resolved


def _apply_inputs(graph: dict[str, Any], workflow_id: str, payload: dict[str, Any], refs: list[tuple[Path, dict[str, Any]]], staged_names: list[str], run_id: str) -> None:
    config = WORKFLOWS[workflow_id]
    prompt = payload["prompt"]
    negative = payload["negative_prompt"]
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        cls, inputs = node.get("class_type"), node.setdefault("inputs", {})
        # ComfyUI's installed CreateVideo node schema exposes ``fps`` on this
        # host, while the checked-in WAN API graph was exported with
        # ``frame_rate``. Keep both graph variants compatible without editing
        # the user's ComfyUI workflow or node installation.
        if cls == "CreateVideo":
            inputs["fps"] = int(config["fps"])
            if "frame_rate" in inputs:
                inputs["frame_rate"] = int(config["fps"])
        if cls in {"MiniMaxH3TextToVideo", "MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo"} and "prompt" in inputs:
            inputs["prompt"] = prompt
        elif cls in {"CLIPTextEncode", "TextEncodeQwenImageEditPlus"}:
            for key in ("text", "prompt"):
                if key in inputs:
                    default = str(inputs.get(key, "")).lower()
                    inputs[key] = negative if negative and any(word in default for word in ("overexposed", "low quality", "deformed", "bad hands")) else prompt
        if cls == "LoadImage":
            index = len([name for name in staged_names if name])
            # The explicit slot lookup below determines the stage order.
            loads = _nodes(graph, "LoadImage")
            ordered = [row for row in refs if row[1]["slot"] == "reference_images"]
            if workflow_id == "wan_first_last":
                ordered = [next(row for row in refs if row[1]["slot"] == slot) for slot in ("first_frame", "last_frame")]
            elif workflow_id == "minimax_references":
                ordered = [row for row in refs if row[1]["slot"] == "reference_images"]
            else:
                ordered = []
            node_position = next((i for i, (candidate_id, _) in enumerate(loads) if candidate_id == str(node_id)), -1)
            if workflow_id == "minimax_references" and ordered and 0 <= node_position < len(loads):
                # The installed H3 reference graph wires all three LoadImage
                # nodes even when the user selects only one or two references.
                # Reuse the last provided image for unused slots so stale
                # default filenames cannot make ComfyUI reject the graph.
                inputs["image"] = staged_names[min(node_position, len(staged_names) - 1)]
            elif 0 <= node_position < len(ordered):
                inputs["image"] = staged_names[node_position]
        for key, value in payload["parameters"].items():
            if key == "duration_seconds":
                frame_key = "length"
                if frame_key in inputs:
                    fps = int(config["fps"])
                    frames = max(1, round(float(value) * fps))
                    # WAN's first/last-frame latent length must be 4n+1.
                    if workflow_id == "wan_first_last":
                        frames = max(5, ((frames - 1 + 2) // 4) * 4 + 1)
                    inputs[frame_key] = frames
            elif key in inputs:
                inputs[key] = value
            elif key == "steps" and cls in {"BasicScheduler", "KSamplerAdvanced"} and "steps" in inputs:
                inputs["steps"] = value
            elif key == "seed" and "noise_seed" in inputs:
                inputs["noise_seed"] = value
        if cls in {"SaveVideo", "VHS_VideoCombine"} and "filename_prefix" in inputs:
            inputs["filename_prefix"] = f"story_builder_manual/{run_id}"


def create_job(payload: dict[str, Any], comfy_url: str) -> dict[str, Any]:
    config, clean, refs = validate_request(payload)
    assets_dir, inputs_dir, outputs_dir, jobs_dir = _manual_dirs()
    run_id = f"manual-{uuid.uuid4().hex[:12]}"
    input_record = {"run_id": run_id, "created_at": _now(), "prompt": clean["prompt"],
        "negative_prompt": clean["negative_prompt"], "workflow_id": clean["workflow_id"],
        "workflow_file": config["file"], "parameters": clean["parameters"],
        "references": [row for _, row in refs], "reference_bytes_copied": False,
        "media_storage_root": str(REPERTOIRE_ROOT)}
    _json_write(inputs_dir / f"{run_id}.json", input_record)
    job = {"run_id": run_id, "status": "queued", "stage": "queued", "progress": 0,
        "message": "Waiting to submit the selected workflow to ComfyUI.", "created_at": _now(),
        "updated_at": _now(), "input_path": f"manual/inputs/{run_id}.json", "outputs": [], "error": None}
    _json_write(jobs_dir / f"{run_id}.json", job)
    return job


def read_job(run_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"manual-[a-f0-9]{12}", run_id):
        raise FileNotFoundError(run_id)
    _, _, _, jobs_dir = _manual_dirs()
    path = jobs_dir / f"{run_id}.json"
    if not path.is_file():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_jobs() -> list[dict[str, Any]]:
    _, _, _, jobs_dir = _manual_dirs()
    rows = []
    for path in jobs_dir.glob("manual-*.json"):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)


def _update_job(run_id: str, **changes: Any) -> dict[str, Any]:
    job = read_job(run_id)
    job.update(changes, updated_at=_now())
    _, _, _, jobs_dir = _manual_dirs()
    _json_write(jobs_dir / f"{run_id}.json", job)
    return job


def run_job(run_id: str, comfy_url: str) -> None:
    job = read_job(run_id)
    _, inputs_dir, outputs_dir, _ = _manual_dirs()
    input_path = inputs_dir / f"{run_id}.json"
    staged: list[Path] = []
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        config = WORKFLOWS[payload["workflow_id"]]
        graph = _load_workflow(WORKFLOW_ROOT / config["file"])
        # Resolve again immediately before use; files can disappear after request validation.
        refs = [resolve_reference(row) for row in payload["references"]]
        comfy_input = Path(os.environ.get("COMFYUI_INPUT_DIR", str(comfyui_root() / "input")))
        comfy_input.mkdir(parents=True, exist_ok=True)
        staged_names: list[str] = []
        load_count = len(_nodes(graph, "LoadImage"))
        if payload["workflow_id"] == "wan_first_last":
            slots = ("first_frame", "last_frame")
            ordered_refs = [next((row for row in refs if row[1]["slot"] == slot), None) for slot in slots]
            if any(row is None for row in ordered_refs):
                raise ValueError("WAN workflow requires both endpoint frames")
            refs_for_workflow = [row for row in ordered_refs if row is not None]
        elif payload["workflow_id"] == "minimax_references":
            refs_for_workflow = [row for row in refs if row[1]["slot"] == "reference_images"]
        else:
            refs_for_workflow = []
        if len(refs_for_workflow) > load_count:
            raise ValueError(f"Selected workflow has {load_count} image input(s), but {len(refs_for_workflow)} were supplied")
        for path, metadata in refs_for_workflow:
            # This installed set currently consumes images only. Never silently drop audio/video assets.
            if metadata["media_type"] != "image":
                raise ValueError(f"{config['label']} cannot use {metadata['media_type']} reference '{metadata['filename']}'")
            target = comfy_input / f"story_builder_{run_id}_{uuid.uuid4().hex[:8]}{path.suffix.lower()}"
            shutil.copy2(path, target)
            staged.append(target)
            staged_names.append(target.name)
        _apply_inputs(graph, payload["workflow_id"], {"prompt": payload["prompt"],
            "negative_prompt": payload.get("negative_prompt", ""), "parameters": payload.get("parameters", {})},
            refs_for_workflow, staged_names, run_id)
        _update_job(run_id, status="running", stage="submitting", progress=5,
                    message=f"Submitting {config['label']} to ComfyUI.", started_at=_now())
        prompt_id, history = submit_and_wait(graph, comfy_url=comfy_url, timeout_seconds=3600)
        _update_job(run_id, stage="collecting_outputs", progress=90, message="Generation completed; collecting output into video repertoire.", prompt_id=prompt_id)
        output_dir = outputs_dir / run_id
        outputs = collect_outputs(history, destination_dir=output_dir, comfy_url=comfy_url)
        for output in outputs:
            output["relative_path"] = f"manual/outputs/{run_id}/{output['relative_path']}"
            output["content_url"] = f"/api/video-repertoire/manual/files/{run_id}/{Path(output['relative_path']).name}"
        if not outputs:
            raise RuntimeError("ComfyUI reported completion but returned no collectible output files")
        _update_job(run_id, status="completed", stage="completed", progress=100,
                    message=f"Generation complete; {len(outputs)} output(s) saved in video repertoire.", outputs=outputs, completed_at=_now())
    except Exception as exc:
        _update_job(run_id, status="failed", stage="failed", progress=100,
                    message="Manual generation failed.", error=f"{type(exc).__name__}: {exc}", failed_at=_now())
    finally:
        for path in staged:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def delete_job(run_id: str) -> dict[str, Any]:
    job = read_job(run_id)
    if job.get("status") in {"queued", "running"}:
        raise ValueError("Cannot delete a queued or running generation; wait for it to finish")
    _, inputs_dir, outputs_dir, jobs_dir = _manual_dirs()
    output_dir = outputs_dir / run_id
    if output_dir.exists():
        shutil.rmtree(safe_path(output_dir, outputs_dir), ignore_errors=False)
    (inputs_dir / f"{run_id}.json").unlink(missing_ok=True)
    (jobs_dir / f"{run_id}.json").unlink(missing_ok=True)
    return {"deleted": run_id, "source_references_preserved": True}


def output_path(run_id: str, filename: str) -> Path:
    if not re.fullmatch(r"manual-[a-f0-9]{12}", run_id) or Path(filename).name != filename:
        raise FileNotFoundError(filename)
    _, _, outputs_dir, _ = _manual_dirs()
    path = safe_path(outputs_dir / run_id / filename, outputs_dir)
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path


def manual_asset_path(relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
        raise FileNotFoundError(relative_path)
    assets_dir, _, _, _ = _manual_dirs()
    path = safe_path(REPERTOIRE_ROOT / relative_path, assets_dir)
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    return path
