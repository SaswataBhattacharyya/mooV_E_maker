"""Host-side GPU admission checks and durable telemetry for local ComfyUI work."""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


MIN_FREE_BYTES = 20 * 1024**3
GPU_RENDER_TEMP_CUTOFF = 83.0
GPU_RENDER_CLOCK_CEILING_MHZ = 2100.0
DEFAULT_TELEMETRY_PATH = Path(os.environ.get("STORY_BUILDER_GPU_TELEMETRY_PATH") or
                              (Path(os.environ.get("TMPDIR", "/tmp")) / "story-builder-gpu-telemetry.jsonl"))
_TELEMETRY_LOCK = threading.Lock()


class GPUAdmissionError(RuntimeError):
    """Raised when the host cannot prove that one GPU workload is safe to run."""


def read_gpu_operating_point() -> dict[str, float]:
    """Read only the two live controls used to protect sustained render work."""
    output = _run(["nvidia-smi", "--query-gpu=temperature.gpu,clocks.current.graphics",
                   "--format=csv,noheader,nounits"], timeout=2)
    rows = list(csv.reader(output.splitlines(), skipinitialspace=True))
    if len(rows) != 1 or len(rows[0]) != 2:
        raise GPUAdmissionError("Could not read one GPU temperature and graphics clock.")
    try:
        point = {"temperature_c": float(rows[0][0].strip()),
                 "graphics_clock_mhz": float(rows[0][1].strip())}
        if not all(math.isfinite(value) and value >= 0 for value in point.values()):
            raise ValueError("Non-finite or negative operating point")
        return point
    except ValueError as exc:
        raise GPUAdmissionError(f"NVIDIA returned invalid temperature/clock telemetry: {rows[0]!r}") from exc


def _run(command: list[str], *, timeout: float = 10) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GPUAdmissionError(f"Could not run {command[0]} for GPU admission: {type(exc).__name__}: {exc}") from exc
    if result.returncode:
        raise GPUAdmissionError(f"{command[0]} failed during GPU admission: {result.stderr.strip()[-1200:]}")
    return result.stdout


def _json_url(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            value = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise GPUAdmissionError(f"Cannot verify ComfyUI runtime at {url}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise GPUAdmissionError(f"ComfyUI returned an invalid response at {url}.")
    return value


def _comfy_processes(comfy_url: str) -> dict[int, str]:
    container = os.environ.get("STORY_BUILDER_COMFYUI_CONTAINER", "comfy-stack")
    output = _run(["docker", "top", container, "-eo", "pid,args"])
    rows: dict[int, str] = {}
    for line in output.splitlines()[1:]:
        fields = line.strip().split(None, 1)
        if len(fields) != 2:
            continue
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        rows[pid] = fields[1]
    port = urlparse(comfy_url).port or (443 if urlparse(comfy_url).scheme == "https" else 80)
    matching = {pid: command for pid, command in rows.items()
                if "main.py" in command and "--port" in command and str(port) in command.split()}
    if not matching:
        raise GPUAdmissionError(
            f"Cannot identify the ComfyUI process in Docker container {container!r} on port {port}; refusing GPU admission.")
    return matching


def _compute_processes() -> list[dict[str, Any]]:
    output = _run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory",
                   "--format=csv,noheader,nounits"])
    processes: list[dict[str, Any]] = []
    for row in csv.reader(output.splitlines(), skipinitialspace=True):
        if len(row) != 3:
            if row and any(field.strip() for field in row):
                raise GPUAdmissionError(f"Cannot parse NVIDIA compute-process row: {row!r}")
            continue
        try:
            pid = int(row[0].strip())
        except ValueError as exc:
            raise GPUAdmissionError(f"Cannot identify NVIDIA compute PID: {row[0]!r}") from exc
        memory_text = row[2].strip().split()[0]
        processes.append({"pid": pid, "process_name": row[1].strip(),
                          "used_memory_mib": int(memory_text) if memory_text.isdigit() else None})
    return processes


def _kernel_errors(since: str) -> list[str]:
    command = ["journalctl", "-k", "--boot=0", f"--since={since}",
               "--grep=(NVRM|Xid|NV_ERR|nvAssert|oom-kill|out of memory|thermal|watchdog|panic)",
               "--case-sensitive=no", "--no-pager", "--output=cat"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GPUAdmissionError(f"Could not run journalctl for GPU event monitoring: {type(exc).__name__}: {exc}") from exc
    if result.returncode == 1 and not result.stdout.strip():
        return []
    if result.returncode:
        raise GPUAdmissionError(f"journalctl failed during GPU monitoring: {result.stderr.strip()[-1200:]}")
    output = result.stdout
    return [line[-1200:] for line in output.splitlines() if line.strip()][-20:]


def _queue_prompt_ids(queue: dict[str, Any], key: str) -> list[str]:
    entries = queue.get(key)
    if not isinstance(entries, list):
        raise GPUAdmissionError(f"ComfyUI /queue has no valid {key} list.")
    ids: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            prompt_id = entry.get("prompt_id") or entry.get("id")
        elif isinstance(entry, (tuple, list)) and len(entry) > 1:
            prompt_id = entry[1]
        else:
            prompt_id = None
        if prompt_id is None:
            raise GPUAdmissionError(f"Cannot identify a prompt in ComfyUI {key}; refusing GPU admission.")
        ids.append(str(prompt_id))
    return ids


def interrupt_if_owned_prompt(*, comfy_url: str, prompt_id: str,
                               request_json: Any) -> tuple[bool, str]:
    """Interrupt only when the exact target is ComfyUI's sole running prompt."""
    try:
        queue = request_json(f"{comfy_url.rstrip('/')}/queue", timeout_seconds=5)
        running = _queue_prompt_ids(queue, "queue_running")
        pending = _queue_prompt_ids(queue, "queue_pending")
    except Exception as exc:
        return False, f"Cannot verify ComfyUI ownership before interrupt ({type(exc).__name__}: {exc})."
    if running != [str(prompt_id)] or pending:
        return False, f"Refused interrupt because ComfyUI is not running only prompt {prompt_id} with an empty pending queue."
    try:
        request_json(f"{comfy_url.rstrip('/')}/interrupt", method="POST", timeout_seconds=5)
    except Exception as exc:
        return False, f"ComfyUI interrupt request failed ({type(exc).__name__}: {exc})."
    return True, f"Requested interrupt for sole running prompt {prompt_id}; reconcile its final remote state."


def inspect_gpu_runtime(*, comfy_url: str, expected_prompt_id: str | None = None,
                        workload_started_at: str | None = None) -> dict[str, Any]:
    """Verify NVIDIA, Docker-owned ComfyUI compute, queue and memory in host context."""
    since = workload_started_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    point = read_gpu_operating_point()
    if point["temperature_c"] >= GPU_RENDER_TEMP_CUTOFF or point["graphics_clock_mhz"] > GPU_RENDER_CLOCK_CEILING_MHZ:
        raise GPUAdmissionError(f"GPU operating limit reached: {point!r}; submission withheld.")
    smi = _run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,"
                "clocks_throttle_reasons.hw_thermal_slowdown,clocks_throttle_reasons.sw_thermal_slowdown",
                "--format=csv,noheader,nounits"])
    gpu_rows = list(csv.reader(smi.splitlines(), skipinitialspace=True))
    if len(gpu_rows) != 1 or len(gpu_rows[0]) != 5:
        raise GPUAdmissionError("Expected one readable NVIDIA GB10 device; refusing GPU admission.")
    try:
        gpu = {"name": gpu_rows[0][0].strip(), "temperature_c": float(gpu_rows[0][1].strip()),
               "utilization_percent": float(gpu_rows[0][2].strip()),
               "graphics_clock_mhz": point["graphics_clock_mhz"],
               "hw_thermal_slowdown": gpu_rows[0][3].strip(),
               "sw_thermal_slowdown": gpu_rows[0][4].strip()}
    except ValueError as exc:
        raise GPUAdmissionError(f"NVIDIA returned invalid temperature/utilization telemetry: {gpu_rows[0]!r}") from exc
    thermal_active = any(value.casefold() == "active" for value in
                         (gpu["hw_thermal_slowdown"], gpu["sw_thermal_slowdown"]))
    if thermal_active and expected_prompt_id is None:
        raise GPUAdmissionError(
            "NVIDIA reports active thermal slowdown; keep new jobs queued until the GPU returns to an unthrottled idle state.")

    stats = _json_url(f"{comfy_url.rstrip('/')}/system_stats")
    devices = stats.get("devices")
    if not isinstance(devices, list) or len(devices) != 1 or not isinstance(devices[0], dict):
        raise GPUAdmissionError("ComfyUI did not report exactly one usable GPU device.")
    device = devices[0]
    if "cuda" not in str(device.get("name", "")).lower() and str(device.get("type", "")).lower() != "cuda":
        raise GPUAdmissionError(f"ComfyUI is not using the expected CUDA GPU: {device.get('name')!r}.")
    try:
        free_bytes = int(device.get("vram_free", 0))
    except (ValueError, TypeError) as exc:
        raise GPUAdmissionError("ComfyUI did not report numeric free GPU memory.") from exc
    # The 20 GiB reserve is a pre-submit admission check. Once the exact
    # owned prompt is running, its model allocations are expected to consume
    # that reserve; rejecting the monitor sample here would abandon active
    # supervision precisely when memory use is highest. Ownership, temperature,
    # clock, queue, compute-process and driver checks still apply in-flight.
    if expected_prompt_id is None and free_bytes < MIN_FREE_BYTES:
        raise GPUAdmissionError(f"ComfyUI reports only {free_bytes / 1024**3:.1f} GiB free; 20 GiB is required.")

    queue = _json_url(f"{comfy_url.rstrip('/')}/queue")
    running = _queue_prompt_ids(queue, "queue_running")
    pending = _queue_prompt_ids(queue, "queue_pending")
    if pending:
        raise GPUAdmissionError(f"ComfyUI has {len(pending)} pending prompt(s); keep new work in Story Builder's backend queue.")
    foreign_running = [prompt_id for prompt_id in running if prompt_id != expected_prompt_id]
    if foreign_running:
        raise GPUAdmissionError(f"ComfyUI is running an unowned prompt: {foreign_running[0]}.")

    comfy_processes = _comfy_processes(comfy_url)
    processes = _compute_processes()
    unknown = [item for item in processes if item["pid"] not in comfy_processes]
    if unknown:
        summary = ", ".join(f"PID {item['pid']} ({item['process_name']})" for item in unknown)
        raise GPUAdmissionError(f"GPU compute is owned by another or unidentifiable workload: {summary}.")
    nvidia_errors = _kernel_errors(since)
    if nvidia_errors:
        raise GPUAdmissionError(f"NVIDIA driver errors occurred during this workload: {nvidia_errors[-1]}")

    return {"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "gpu": gpu, "comfyui": {"device": device.get("name"), "free_bytes": free_bytes,
              "free_gib": round(free_bytes / 1024**3, 2), "running_prompt_ids": running,
            "pending_prompt_ids": pending}, "compute_processes": processes,
            "comfyui_container_pids": sorted(comfy_processes), "nvidia_kernel_errors": [],
            "thermal_slowdown_active": thermal_active}


def record_gpu_telemetry(path: str | Path | None, sample: dict[str, Any], *,
                         workload_id: str | None, phase: str) -> None:
    """Append and sync one bounded sample so a reboot preserves the last readings."""
    if path is None:
        return
    row = json.dumps({"workload_id": workload_id, "phase": phase, **sample}, sort_keys=True) + "\n"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _TELEMETRY_LOCK, target.open("a", encoding="utf-8") as handle:
        handle.write(row)
        handle.flush()
        os.fsync(handle.fileno())
