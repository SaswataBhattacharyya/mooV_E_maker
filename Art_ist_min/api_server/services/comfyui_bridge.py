"""ComfyUI prompt submission for OpenClaw image review batches."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from app_config import load_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = load_config(PROJECT_ROOT)
WORKFLOW_TEMPLATE = PROJECT_ROOT / "workflows" / "api" / "gsl_starter_1_1_api.json"


class ComfyUIError(RuntimeError):
    """Raised when a local ComfyUI request fails."""


def request_memory_release() -> dict[str, Any]:
    endpoints = (
        ("/free", {"unload_models": True, "free_memory": True}),
        ("/free_memory", {"unload_models": True, "free_memory": True}),
    )
    attempted: list[str] = []
    for path, payload in endpoints:
        attempted.append(path)
        request = urllib.request.Request(
            f"http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="replace").strip()
            return {
                "kind": "comfyui_memory_release",
                "status": "succeeded",
                "endpoint": path,
                "attempted_endpoints": attempted,
                "response": body,
            }
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            detail = exc.read().decode("utf-8", errors="replace").strip()
            return {
                "kind": "comfyui_memory_release",
                "status": "failed",
                "endpoint": path,
                "attempted_endpoints": attempted,
                "error": detail or f"HTTP {exc.code}",
            }
        except urllib.error.URLError as exc:
            return {
                "kind": "comfyui_memory_release",
                "status": "failed",
                "endpoint": path,
                "attempted_endpoints": attempted,
                "error": str(exc),
            }
    return {
        "kind": "comfyui_memory_release",
        "status": "skipped",
        "endpoint": None,
        "attempted_endpoints": attempted,
        "error": "No supported ComfyUI memory-release endpoint was available",
    }


def load_workflow_template() -> dict[str, Any]:
    return json.loads(WORKFLOW_TEMPLATE.read_text(encoding="utf-8"))


def submit_image_batch(
    *,
    project_id: str,
    job: dict[str, Any],
    batch_index: int,
    batch_size: int,
    destination_dir: Path,
) -> dict[str, Any]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    batch_id = f"{job['job_id']}-batch-{batch_index:03d}"
    candidates: list[dict[str, Any]] = []

    for candidate_index in range(batch_size):
        prompt = load_workflow_template()
        seed = int(time.time() * 1000) + candidate_index
        prefix = f"{project_id}_{job['job_id']}_{batch_index:03d}_{candidate_index + 1:02d}"
        prompt["45"]["inputs"]["text"] = job["prompt"]
        prompt["41"]["inputs"]["width"] = int(job.get("width", 1280))
        prompt["41"]["inputs"]["height"] = int(job.get("height", 720))
        prompt["44"]["inputs"]["seed"] = seed
        prompt["76"]["inputs"]["filename_prefix"] = prefix
        prompt_id = _submit_prompt(prompt)
        history = _wait_for_history(prompt_id)
        images = _collect_images_from_history(history, destination_dir)
        if not images:
            raise ComfyUIError("ComfyUI completed but did not produce any images")
        image_path = images[0]
        candidates.append(
            {
                "candidate_id": f"{batch_id}-cand-{candidate_index + 1:02d}",
                "filename": image_path.name,
                "relative_path": str(image_path.relative_to(destination_dir.parents[2])),
                "status": "pending",
                "seed": seed,
                "prompt_id": prompt_id,
            }
        )

    return {
        "batch_id": batch_id,
        "job_id": job["job_id"],
        "title": job["title"],
        "prompt": job["prompt"],
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidates": candidates,
    }


def _submit_prompt(prompt: dict[str, Any]) -> str:
    payload = {"prompt": prompt}
    request = urllib.request.Request(
        f"http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}/prompt",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ComfyUIError(
            f"Could not reach ComfyUI at http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}"
        ) from exc
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise ComfyUIError("ComfyUI did not return a prompt_id")
    return str(prompt_id)


def _wait_for_history(prompt_id: str, timeout_seconds: int = 300) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    history_url = f"http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}/history/{prompt_id}"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(history_url, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyUIError("Failed while polling ComfyUI history") from exc
        prompt_state = data.get(prompt_id)
        if prompt_state:
            status = prompt_state.get("status", {})
            if status.get("status_str") == "error":
                raise ComfyUIError(f"ComfyUI prompt failed: {status.get('messages', [])}")
            if status.get("completed"):
                return prompt_state
        time.sleep(2)
    raise ComfyUIError(f"Timed out waiting for ComfyUI prompt {prompt_id}")


def _collect_images_from_history(history: dict[str, Any], destination_dir: Path) -> list[Path]:
    copied: list[Path] = []
    outputs = history.get("outputs", {})
    for node_output in outputs.values():
        for image in node_output.get("images", []):
            copied_path = _copy_output_image(image, destination_dir)
            if copied_path is not None:
                copied.append(copied_path)
    return copied


def _copy_output_image(image: dict[str, Any], destination_dir: Path) -> Path | None:
    filename = image.get("filename")
    if not filename:
        return None
    subfolder = image.get("subfolder", "")
    source_path = CONFIG.comfyui_path / "output" / subfolder / filename
    destination_path = destination_dir / f"{uuid.uuid4().hex}_{Path(filename).name}"
    if source_path.exists():
        shutil.copy2(source_path, destination_path)
        return destination_path

    params = urllib.parse.urlencode(
        {
            "filename": filename,
            "subfolder": subfolder,
            "type": image.get("type", "output"),
        }
    )
    view_url = f"http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}/view?{params}"
    try:
        with urllib.request.urlopen(view_url, timeout=60) as response:
            destination_path.write_bytes(response.read())
            return destination_path
    except urllib.error.URLError:
        return None
