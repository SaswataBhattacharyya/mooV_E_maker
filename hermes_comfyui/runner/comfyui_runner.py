#!/usr/bin/env python3
"""Deterministic Hermes entry point for repo-approved ComfyUI workflows."""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

from comfyui_client import ComfyUIClient, ComfyUIError
from request_schema import MediaRequest, RequestError
from workflow_registry import REPO_ROOT, get_spec


OUTPUT_ROOT = REPO_ROOT / "output" / "comfyui"


def prepare_workflow(request: MediaRequest, uploaded_images: list[str], prefix: str) -> dict[str, Any]:
    spec = get_spec(request.workflow)
    spec.validate(request)
    workflow = json.loads(spec.path.read_text(encoding="utf-8"))
    _remove_unused_optional_images(request.workflow, workflow, len(uploaded_images))
    positive_used = negative_used = False
    image_index = 0
    for node in workflow.values():
        class_type = str(node.get("class_type", ""))
        inputs = node.setdefault("inputs", {})
        if class_type == "LoadImage" and image_index < len(uploaded_images):
            inputs["image"] = uploaded_images[image_index]
            image_index += 1
        if class_type in {"CLIPTextEncode", "TextEncodeQwenImageEditPlus"}:
            key = "prompt" if "prompt" in inputs else "text" if "text" in inputs else None
            if key:
                old = str(inputs.get(key, "")).lower()
                is_negative = any(word in old for word in ("low quality", "deformed", "ugly", "bad anatomy"))
                if is_negative and request.negative_prompt:
                    inputs[key] = request.negative_prompt
                    negative_used = True
                elif not is_negative and not positive_used:
                    inputs[key] = request.prompt
                    positive_used = True
        if class_type in {"MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo"}:
            inputs["prompt"] = request.prompt
            if request.duration is not None:
                inputs["length"] = _minimax_frames(request.duration)
            positive_used = True
        for key, value in (("width", request.width), ("height", request.height), ("seed", request.seed), ("noise_seed", request.seed)):
            if value is not None and key in inputs:
                inputs[key] = value
        if class_type in {"SaveImage", "SaveVideo"} and "filename_prefix" in inputs:
            inputs["filename_prefix"] = prefix
    if not positive_used:
        raise RequestError(f"No registered prompt input was found in {request.workflow}")
    if image_index < len(uploaded_images):
        raise RequestError(f"Workflow consumed {image_index} of {len(uploaded_images)} uploaded images")
    return workflow


def _remove_unused_optional_images(workflow_id: str, workflow: dict[str, Any], image_count: int) -> None:
    if workflow_id == "qwen-image-edit-2511":
        for index, node_id in enumerate(("78", "120", "121")):
            if index >= image_count:
                workflow.pop(node_id, None)
                for encoder_id in ("110", "111"):
                    workflow[encoder_id]["inputs"].pop(f"image{index + 1}", None)
    if workflow_id == "qwen-image-refine-2512" and image_count == 1:
        workflow.pop("241", None)
        for encoder_id in ("308", "309"):
            workflow[encoder_id]["inputs"].pop("image3", None)
    if workflow_id == "minimax-h3-i2v" and image_count == 1:
        workflow.pop("2", None)
        workflow["104"]["inputs"].pop("last_frame", None)
    if workflow_id == "minimax-h3-r2v":
        for index in range(image_count, 3):
            workflow.pop(str(101 + index), None)
            workflow["136"]["inputs"].pop(f"ref_images.ref_image_{index}", None)


def _minimax_frames(duration: float) -> int:
    base = max(5, round(duration * 24))
    return base + (5 - base % 17) % 17


def execute(request_path: Path) -> dict[str, Any]:
    raw = json.loads(request_path.read_text(encoding="utf-8"))
    request = MediaRequest.from_dict(raw)
    spec = get_spec(request.workflow)
    spec.validate(request)
    client = ComfyUIClient()
    client.health()
    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{random.randrange(16**6):06x}"
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "request.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    (run_dir / "prompt.txt").write_text(request.prompt + "\n", encoding="utf-8")
    uploaded = [client.upload_image(path) for path in request.input_images]
    all_outputs: list[dict[str, str]] = []
    prompt_ids: list[str] = []
    for index in range(request.count):
        prefix = f"hermes/{run_id}/{request.workflow}-{index + 1:02d}"
        workflow = prepare_workflow(request, uploaded, prefix)
        if request.seed is not None and request.count > 1:
            for node in workflow.values():
                for key in ("seed", "noise_seed"):
                    if key in node.get("inputs", {}):
                        node["inputs"][key] = request.seed + index
        if index == 0:
            (run_dir / "submitted_workflow.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        prompt_id = client.submit(copy.deepcopy(workflow))
        prompt_ids.append(prompt_id)
        history = client.wait(prompt_id)
        all_outputs.extend(client.download_outputs(history, run_dir / "outputs"))
    if not all_outputs:
        raise ComfyUIError("ComfyUI completed but exposed no downloadable outputs")
    result = {"status": "completed", "run_id": run_id, "workflow": request.workflow, "prompt_ids": prompt_ids, "output_dir": str(run_dir.resolve()), "outputs": all_outputs}
    (run_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = execute(args.request.resolve())
        print(json.dumps(result))
        return 0
    except (OSError, json.JSONDecodeError, RequestError, ComfyUIError) as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
