"""Prompt-owned thermal supervision, independent of backend HTTP polling.

Run as a detached child so a backend restart does not abandon an active
ComfyUI prompt. Only the exact sole running prompt may be interrupted.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

if __package__:
    from .gpu_runtime import (GPUAdmissionError, GPU_RENDER_TEMP_CUTOFF,
        GPU_RENDER_CLOCK_CEILING_MHZ, read_gpu_operating_point, interrupt_if_owned_prompt)
else:  # Executed directly with the backend's Python; no model imports.
    from gpu_runtime import (GPUAdmissionError, GPU_RENDER_TEMP_CUTOFF,
        GPU_RENDER_CLOCK_CEILING_MHZ, read_gpu_operating_point, interrupt_if_owned_prompt)


def _request(url, *, method="GET", timeout_seconds=2):
    request = urllib.request.Request(url, method=method,
        data=b"{}" if method == "POST" else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=min(timeout_seconds, 2)) as response:
        return json.loads(response.read())


def _path(comfy_url, prompt_id):
    digest = hashlib.sha256(f"{comfy_url.rstrip('/')}:{prompt_id}".encode()).hexdigest()
    root = Path(tempfile.gettempdir()) / f"story-builder-watchdogs-{os.getuid()}"
    root.mkdir(mode=0o700, exist_ok=True)
    return root / f"{digest}.json"


class PromptWatchdog:
    def __init__(self, path):
        self.path = path

    def check(self):
        if not self.path.exists():
            raise GPUAdmissionError("Independent GPU watchdog state is missing.")
        try:
            state = json.loads(self.path.read_text())
        except (OSError, ValueError) as exc:
            raise GPUAdmissionError(f"Cannot read independent GPU watchdog: {exc}") from exc
        if state.get("tripped"):
            raise GPUAdmissionError(state.get("reason", "Independent GPU watchdog tripped."))
        if not state.get("remote_terminal") and state.get("sampled_at") and time.time() - state["sampled_at"] > 6:
            raise GPUAdmissionError("Independent GPU watchdog telemetry is stale; reconcile this prompt.")


def finish_prompt_watchdog(*, comfy_url, prompt_id):
    """Stop supervision only after a definitive rejection or terminal response."""
    _path(comfy_url, prompt_id).with_suffix(".done").touch()


def ensure_prompt_watchdog(*, comfy_url, prompt_id):
    """Idempotently ensure one detached monitor for a durably reserved prompt."""
    path = _path(comfy_url, prompt_id)
    # The child takes flock for its entire lifetime; repeated recovery calls
    # cannot create competing monitors or overwrite the active monitor's state.
    with path.with_suffix(".lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return PromptWatchdog(path)
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
            comfy_url.rstrip("/"), str(prompt_id), str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        # Close our temporary lock before waiting for the child to acquire it.
        fcntl.flock(lock, fcntl.LOCK_UN)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if process.poll() is not None:
            if path.exists():
                return PromptWatchdog(path)  # Another monitor won the lock.
            raise GPUAdmissionError("Independent GPU watchdog could not start.")
        if path.exists():
            return PromptWatchdog(path)
        time.sleep(.02)
    raise GPUAdmissionError("Independent GPU watchdog did not acknowledge startup.")


def _write(path, state):
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    with temporary.open("w") as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def supervise(comfy_url, prompt_id, path, *, reader=read_gpu_operating_point,
              request=_request, stop=None, interval=1.0):
    """Keep fast thermal sampling independent of all ComfyUI HTTP requests."""
    stopped = stop or threading.Event()
    state = {"prompt_id": prompt_id, "pid": os.getpid(), "tripped": False}
    mutex = threading.Lock()
    trip = threading.Event()
    _write(path, state)

    def remote_control():
        # Network timeouts cannot block the sampling loop below.
        while not stopped.is_set():
            if trip.is_set():
                interrupted, reason = interrupt_if_owned_prompt(comfy_url=comfy_url,
                    prompt_id=prompt_id, request_json=request)
                with mutex:
                    state.update(interrupt_requested=interrupted, interrupt_detail=reason)
                    _write(path, state)
            try:
                history = request(f"{comfy_url}/history/{prompt_id}", timeout_seconds=2)
                status = history.get(prompt_id, {}).get("status", {})
                if status.get("completed") or status.get("status_str") in {"success", "error"}:
                    stopped.set()
                    break
            except Exception:
                pass  # Unknown remote state retains thermal supervision.
            stopped.wait(interval)
    remote = threading.Thread(target=remote_control, daemon=True)
    remote.start()
    while not stopped.is_set():
        if path.with_suffix(".done").exists():
            stopped.set()
            break
        try:
            point = reader()
            reason = None
            if point["temperature_c"] >= GPU_RENDER_TEMP_CUTOFF:
                reason = f"GPU reached {point['temperature_c']} C (cutoff {GPU_RENDER_TEMP_CUTOFF} C)."
            elif point["graphics_clock_mhz"] > GPU_RENDER_CLOCK_CEILING_MHZ:
                reason = f"GPU clock exceeded {GPU_RENDER_CLOCK_CEILING_MHZ} MHz."
        except Exception as exc:
            point, reason = {}, f"GPU temperature/clock telemetry unavailable: {exc}"
        with mutex:
            state.update(gpu=point, sampled_at=time.time())
            if reason:
                state.update(tripped=True, reason=reason)
                trip.set()
            _write(path, state)
        stopped.wait(interval)
    remote.join(timeout=1)
    with mutex:
        state["remote_terminal"] = True
        _write(path, state)


if __name__ == "__main__":
    url, prompt, state_path = sys.argv[1:]
    path = Path(state_path)
    with path.with_suffix(".lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit(0)
        if path.exists() and json.loads(path.read_text()).get("remote_terminal"):
            sys.exit(0)
        supervise(url, prompt, path)
