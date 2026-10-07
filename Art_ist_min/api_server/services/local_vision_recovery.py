"""Bounded local GPU recovery for native OpenClaw vision review."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from app_config import load_config

from api_server.services.comfyui_bridge import request_memory_release
from api_server.services.native_openclaw_client import gateway_runtime_summary
from api_server.services.ollama_client import (
    OllamaError,
    list_running_models,
    stop_model,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = load_config(PROJECT_ROOT)
GPU_RECHECK_DELAY_SECONDS = float(os.environ.get("VISION_RECOVERY_RECHECK_DELAY_SECONDS", "2"))


def is_resource_exhaustion_error(error_text: str) -> bool:
    text = error_text.lower()
    markers = (
        "out of memory",
        "not enough memory",
        "cuda",
        "vram",
        "failed to load model",
        "load model",
        "memory",
        "model requires more system memory",
        "insufficient",
        "gpu",
    )
    return any(marker in text for marker in markers)


def _run_command(command: list[str], timeout: int = 10) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)

    output = (result.stdout or result.stderr or "").strip()
    return result.returncode == 0, output


def _collect_gpu_snapshot() -> dict[str, Any]:
    gpu_summary: dict[str, Any] = {
        "available": False,
        "driver_ready": False,
        "memory": None,
        "processes": [],
        "error": None,
    }
    if shutil.which("nvidia-smi") is None:
        gpu_summary["error"] = "nvidia-smi not found"
        return gpu_summary

    ok_memory, memory_output = _run_command(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        timeout=8,
    )
    if ok_memory:
        first_line = next((line.strip() for line in memory_output.splitlines() if line.strip()), "")
        if first_line:
            parts = [part.strip() for part in first_line.split(",")]
            if len(parts) >= 2:
                try:
                    gpu_summary["memory"] = {
                        "used_mb": int(parts[0]),
                        "total_mb": int(parts[1]),
                    }
                except ValueError:
                    gpu_summary["memory"] = None
        gpu_summary["available"] = True
        gpu_summary["driver_ready"] = True
    else:
        gpu_summary["error"] = memory_output or "nvidia-smi query failed"
        return gpu_summary

    ok_processes, process_output = _run_command(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"],
        timeout=8,
    )
    if ok_processes and process_output:
        processes = []
        for line in process_output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                used_mb = int(parts[2])
            except ValueError:
                used_mb = None
            processes.append(
                {
                    "pid": parts[0],
                    "process_name": parts[1],
                    "used_gpu_memory_mb": used_mb,
                }
            )
        gpu_summary["processes"] = processes

    return gpu_summary


def _collect_process_snapshot(limit: int = 8) -> dict[str, Any]:
    ok, output = _run_command(
        ["ps", "-eo", "pid,comm,args", "--sort=-rss"],
        timeout=8,
    )
    if not ok:
        return {"available": False, "processes": [], "error": output or "ps failed"}

    rows = []
    for line in output.splitlines()[1 : limit + 1]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 2)
        rows.append(
            {
                "pid": parts[0] if len(parts) > 0 else "",
                "command": parts[1] if len(parts) > 1 else "",
                "args": parts[2] if len(parts) > 2 else "",
            }
        )
    return {"available": True, "processes": rows, "error": None}


def _collect_ollama_snapshot() -> dict[str, Any]:
    try:
        models = list_running_models()
        return {
            "available": True,
            "running_models": models,
            "error": None,
        }
    except OllamaError as exc:
        return {
            "available": False,
            "running_models": [],
            "error": str(exc),
        }


def collect_resource_snapshot() -> dict[str, Any]:
    comfyui_url = f"http://{CONFIG.comfyui_host}:{CONFIG.comfyui_port}/system_stats"
    return {
        "gateway": gateway_runtime_summary(),
        "gpu": _collect_gpu_snapshot(),
        "ollama": _collect_ollama_snapshot(),
        "processes": _collect_process_snapshot(),
        "comfyui": {
            "reachable": _service_reachable(comfyui_url),
            "system_stats_url": comfyui_url,
        },
    }


def _service_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3):
            return True
    except urllib.error.URLError:
        return False


def classify_resource_contention(snapshot: dict[str, Any], protected_models: set[str]) -> str:
    running_models = snapshot.get("ollama", {}).get("running_models", [])
    model_names = {str(model.get("name", "")).strip() for model in running_models}
    non_protected = {name for name in model_names if name and name not in protected_models}

    gpu_processes = snapshot.get("gpu", {}).get("processes", [])
    comfy_present = any(
        "comfy" in str(item.get("process_name", "")).lower() or "comfy" in str(item.get("args", "")).lower()
        or "python" in str(item.get("process_name", "")).lower() and "comfy" in json.dumps(item).lower()
        for item in [*gpu_processes, *snapshot.get("processes", {}).get("processes", [])]
    )

    if comfy_present and non_protected:
        return "mixed_contention"
    if comfy_present:
        return "comfyui_holding_vram"
    if non_protected:
        return "ollama_resident_models"
    if snapshot.get("gpu", {}).get("available"):
        memory = snapshot.get("gpu", {}).get("memory") or {}
        used = int(memory.get("used_mb") or 0)
        total = int(memory.get("total_mb") or 0)
        if total and used / total >= 0.9:
            return "gpu_pressure_without_owner"
        return "no_visible_contention"
    return "diagnostics_unavailable"


def _select_ollama_models_to_stop(snapshot: dict[str, Any], protected_models: set[str]) -> list[str]:
    selected: list[str] = []
    for model in snapshot.get("ollama", {}).get("running_models", []):
        name = str(model.get("name", "")).strip()
        if name and name not in protected_models:
            selected.append(name)
    return selected


def run_local_vision_recovery(
    *,
    error_text: str,
    vision_model: str,
    reasoning_model: str,
    coder_model: str,
) -> dict[str, Any]:
    gateway = gateway_runtime_summary()
    if not gateway.get("is_local", True):
        return {
            "eligible": False,
            "attempted": False,
            "reason": "native OpenClaw runtime is not local",
            "contention_class": "skipped_non_local",
            "snapshot_before": {"gateway": gateway},
            "snapshot_after": None,
            "cleanup_actions": [],
            "retry_recommended": False,
        }

    if not is_resource_exhaustion_error(error_text):
        return {
            "eligible": False,
            "attempted": False,
            "reason": "vision failure does not look like GPU or model-load contention",
            "contention_class": "skipped_non_resource_error",
            "snapshot_before": {"gateway": gateway},
            "snapshot_after": None,
            "cleanup_actions": [],
            "retry_recommended": False,
        }

    protected_models = {name for name in {vision_model, "", None} if name}
    snapshot_before = collect_resource_snapshot()
    contention_class = classify_resource_contention(snapshot_before, protected_models)
    cleanup_actions: list[dict[str, Any]] = []

    for model_name in _select_ollama_models_to_stop(snapshot_before, protected_models):
        try:
            stop_model(model_name)
            cleanup_actions.append(
                {
                    "kind": "ollama_stop_model",
                    "target": model_name,
                    "status": "succeeded",
                }
            )
        except OllamaError as exc:
            cleanup_actions.append(
                {
                    "kind": "ollama_stop_model",
                    "target": model_name,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    comfy_action = request_memory_release()
    cleanup_actions.append(comfy_action)

    time.sleep(max(0.0, GPU_RECHECK_DELAY_SECONDS))
    snapshot_after = collect_resource_snapshot()

    stopped_models = {
        action["target"]
        for action in cleanup_actions
        if action.get("kind") == "ollama_stop_model" and action.get("status") == "succeeded"
    }
    retry_recommended = bool(stopped_models) or comfy_action.get("status") == "succeeded"

    return {
        "eligible": True,
        "attempted": True,
        "reason": "bounded local recovery executed",
        "contention_class": contention_class,
        "snapshot_before": snapshot_before,
        "snapshot_after": snapshot_after,
        "cleanup_actions": cleanup_actions,
        "protected_models": sorted(protected_models),
        "support_models": [model for model in [reasoning_model, coder_model] if model],
        "retry_recommended": retry_recommended or contention_class == "gpu_pressure_without_owner",
    }
