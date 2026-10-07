"""Generic media job persistence and ComfyUI execution helpers."""

from __future__ import annotations

import json
import logging
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import os
import tempfile
import threading
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from story_builder.services.gpu_runtime import (
    DEFAULT_TELEMETRY_PATH, MIN_FREE_BYTES, GPUAdmissionError, inspect_gpu_runtime, record_gpu_telemetry,
)


from story_builder.services.gpu_watchdog import ensure_prompt_watchdog, finish_prompt_watchdog


class MediaJobError(RuntimeError):
    """Raised when a media job cannot be prepared or executed."""

    def __init__(self, message: str, *, prompt_id: str | None = None,
                 remote_state_unknown: bool = False):
        super().__init__(message)
        self.prompt_id = prompt_id
        self.remote_state_unknown = remote_state_unknown


_COMFY_SUBMISSION_THREAD_LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)


@contextmanager
def comfy_submission_guard():
    """Serialize every Story Builder submitter across threads and backend processes.

    The lock is only an admission guard, not a media/job store. Durable job
    status remains in the owning feature's backend ledger. ``flock`` releases
    automatically if a backend process exits unexpectedly.
    """
    lock_path = Path(os.environ.get("STORY_BUILDER_COMFY_SUBMISSION_LOCK") or
                     (Path(tempfile.gettempdir()) / "story-builder-comfy-submission.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _COMFY_SUBMISSION_THREAD_LOCK:
        with lock_path.open("a+") as lock_file:
            try:
                import fcntl
            except ImportError:  # pragma: no cover - non-POSIX development fallback
                yield
                return
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def wait_for_comfyui_idle(*, comfy_url: str, timeout_seconds: int,
                          poll_interval_seconds: float = 2.0,
                          workload_id: str | None = None,
                          telemetry_path: str | Path | None = None,
                          workload_started_at: str | None = None) -> None:
    """Wait inside the backend dispatcher until ComfyUI has no running/pending prompts."""
    deadline = time.monotonic() + max(0, timeout_seconds)
    last_busy: tuple[int, int] | None = None
    while True:
        try:
            with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/queue", timeout=10) as response:
                queue = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise MediaJobError(f"Cannot verify ComfyUI queue before submit: {type(exc).__name__}: {exc}") from exc
        running, pending = queue.get("queue_running"), queue.get("queue_pending")
        if not isinstance(running, list) or not isinstance(pending, list):
            raise MediaJobError("ComfyUI returned an invalid /queue response; submission was withheld")
        if not running and not pending:
            try:
                sample = inspect_gpu_runtime(comfy_url=comfy_url, workload_started_at=workload_started_at)
            except GPUAdmissionError as exc:
                raise MediaJobError(f"GPU admission failed closed: {exc}") from exc
            record_gpu_telemetry(telemetry_path, sample, workload_id=workload_id, phase="admission")
            return
        last_busy = (len(running), len(pending))
        if time.monotonic() >= deadline:
            raise MediaJobError(f"Timed out waiting for ComfyUI queue to become idle; running={last_busy[0]} pending={last_busy[1]}")
        time.sleep(max(0.05, poll_interval_seconds))


@contextmanager
def gpu_workload_guard(*, comfy_url: str, timeout_seconds: int = 24 * 3600):
    """Admit one app-owned GPU workload after visible ComfyUI work is idle.

    This coordinates Story Builder callers only. It is not a host-wide GPU
    scheduler and cannot lock out unrelated applications or manual clients.
    """
    with comfy_submission_guard():
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stopped = threading.Event()
        monitor_failure: list[str] = []
        workload_id = f"pid:{os.getpid()}"
        telemetry_path = DEFAULT_TELEMETRY_PATH
        wait_for_comfyui_idle(comfy_url=comfy_url, timeout_seconds=timeout_seconds,
                              workload_id=workload_id, telemetry_path=telemetry_path,
                              workload_started_at=started_at)

        def monitor() -> None:
            while not stopped.wait(10):
                try:
                    sample = inspect_gpu_runtime(comfy_url=comfy_url, workload_started_at=started_at)
                    record_gpu_telemetry(telemetry_path, sample, workload_id=workload_id, phase="app_gpu_workload")
                except Exception as exc:
                    message = f"{type(exc).__name__}: {exc}"
                    monitor_failure.append(message)
                    record_gpu_telemetry(telemetry_path, {"recorded_at": datetime.now(timezone.utc).isoformat(),
                        "monitor_error": message}, workload_id=workload_id, phase="monitor_error")
                    stopped.set()

        monitor_thread = threading.Thread(target=monitor, name="story-builder-gpu-monitor", daemon=True)
        monitor_thread.start()
        try:
            yield
        except BaseException:
            stopped.set()
            monitor_thread.join(timeout=15)
            raise
        stopped.set()
        monitor_thread.join(timeout=15)
        if monitor_failure:
            raise MediaJobError(f"GPU state changed during the workload: {monitor_failure[0]}")


def release_comfyui_models_if_idle(*, comfy_url: str, timeout_seconds: int = 10,
                                   poll_interval_seconds: float = 0.5) -> dict[str, Any]:
    """Ask ComfyUI to unload VRAM models only when its shared queue is idle.

    This is best-effort housekeeping: it must never turn a successful render
    into a failed job, and it must not disrupt a queued/running workflow owned
    by another Story Builder page or a direct ComfyUI user.
    """
    try:
        with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/queue", timeout=timeout_seconds) as response:
            queue = json.loads(response.read().decode("utf-8"))
        running = queue.get("queue_running", [])
        pending = queue.get("queue_pending", [])
        if running or pending:
            return {"status": "deferred", "reason": "comfyui_queue_not_empty",
                    "running": len(running), "pending": len(pending)}
        request = urllib.request.Request(
            f"{comfy_url.rstrip('/')}/free",
            data=json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read()
        # /free acknowledges a request; it does not prove the model has been
        # evicted or that another GPU job can safely be admitted. Observe the
        # ComfyUI device telemetry and report success only after the configured
        # pre-submit headroom is visible again.
        deadline = time.monotonic() + max(0, timeout_seconds)
        last_free_bytes: int | None = None
        while True:
            try:
                with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/system_stats", timeout=timeout_seconds) as response:
                    stats = json.loads(response.read().decode("utf-8"))
                devices = stats.get("devices") if isinstance(stats, dict) else None
                if not isinstance(devices, list) or len(devices) != 1 or not isinstance(devices[0], dict):
                    raise ValueError("ComfyUI did not report exactly one GPU device")
                last_free_bytes = int(devices[0].get("vram_free", 0))
                if last_free_bytes >= MIN_FREE_BYTES:
                    return {"status": "headroom_verified", "unload_request_accepted": True,
                            "vram_free_bytes": last_free_bytes,
                            "required_free_bytes": MIN_FREE_BYTES}
            except Exception as exc:
                return {"status": "unverified", "unload_request_accepted": True,
                        "reason": f"VRAM verification failed: {type(exc).__name__}: {exc}"}
            if time.monotonic() >= deadline:
                return {"status": "unverified", "unload_request_accepted": True,
                        "reason": "ComfyUI acknowledged /free but did not restore required GPU headroom",
                        "vram_free_bytes": last_free_bytes, "required_free_bytes": MIN_FREE_BYTES}
            time.sleep(max(0.05, poll_interval_seconds))
    except Exception as exc:  # cleanup failure must not mask the workflow result
        return {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}


def apply_media_inputs(workflow: dict[str, Any], payload: dict[str, Any], filename_prefix: str) -> dict[str, Any]:
    prompt = payload.get("prompt", "")
    negative_prompt = payload.get("negative_prompt", "")
    images = payload.get("images", []) or []
    number_overrides = {key: payload.get(key) for key in ("width", "height", "steps", "cfg", "seed", "length", "frame_rate")}

    image_index = 0
    for node in workflow.values():
        class_type = node.get("class_type", "")
        inputs = node.setdefault("inputs", {})
        if class_type == "LoadImage" and image_index < len(images):
            inputs["image"] = images[image_index]
            image_index += 1
        if class_type in {"CLIPTextEncode", "TextEncodeQwenImageEditPlus"}:
            if "prompt" in inputs:
                default_prompt = str(inputs.get("prompt", ""))
                inputs["prompt"] = negative_prompt if _looks_negative(default_prompt) and negative_prompt else prompt
            if "text" in inputs:
                default_text = str(inputs.get("text", ""))
                if _looks_negative(default_text):
                    if negative_prompt:
                        inputs["text"] = negative_prompt
                else:
                    inputs["text"] = prompt
        for key, value in number_overrides.items():
            if value is not None and key in inputs:
                inputs[key] = value
        if class_type in {"SaveImage", "SaveVideo"} and "filename_prefix" in inputs:
            inputs["filename_prefix"] = filename_prefix
    return workflow


def _looks_negative(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ("low quality", "deformed", "ugly", "bad "))


def submit_and_wait(workflow: dict[str, Any], *, comfy_url: str, timeout_seconds: int = 600,
                    prompt_id: str | None = None, telemetry_path: str | Path | None = None,
                    workload_id: str | None = None) -> tuple[str, dict[str, Any]]:
    # Keep the shared lock through completion, not just POST: otherwise a
    # second website operation could be added to ComfyUI's own pending queue.
    telemetry_path = telemetry_path or DEFAULT_TELEMETRY_PATH
    workload_id = workload_id or f"pid:{os.getpid()}:comfy_render"
    with comfy_submission_guard():
        workload_started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        wait_for_comfyui_idle(comfy_url=comfy_url, timeout_seconds=timeout_seconds,
                              workload_id=workload_id, telemetry_path=telemetry_path,
                              workload_started_at=workload_started_at)
        requested_prompt_id = prompt_id
        try:
            watchdog = ensure_prompt_watchdog(comfy_url=comfy_url, prompt_id=prompt_id) if prompt_id else None
            if watchdog:
                watchdog.check()
        except GPUAdmissionError as exc:
            if prompt_id:
                finish_prompt_watchdog(comfy_url=comfy_url, prompt_id=prompt_id)
            raise MediaJobError(f"GPU watchdog admission failed before POST: {exc}") from exc
        payload: dict[str, Any] = {"prompt": workflow}
        if requested_prompt_id is not None:
            payload["prompt_id"] = requested_prompt_id
        request = urllib.request.Request(
            f"{comfy_url}/prompt",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if requested_prompt_id:
                finish_prompt_watchdog(comfy_url=comfy_url, prompt_id=requested_prompt_id)
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            raise MediaJobError(f"ComfyUI rejected the workflow (HTTP {exc.code}): {detail[:2000]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MediaJobError(
                "ComfyUI submission outcome is unknown after the request was sent; "
                "do not blindly resubmit. Check the ComfyUI queue/history first.",
                prompt_id=requested_prompt_id, remote_state_unknown=True) from exc
        except json.JSONDecodeError as exc:
            raise MediaJobError(
                "ComfyUI returned an unreadable submission response; the render may still be queued. "
                "Check the ComfyUI queue/history before retrying.",
                prompt_id=requested_prompt_id, remote_state_unknown=True) from exc
        prompt_id = data.get("prompt_id")
        if not prompt_id or (requested_prompt_id is not None and prompt_id != requested_prompt_id):
            raise MediaJobError(
                f"ComfyUI returned an unexpected prompt_id {prompt_id!r}; "
                "reconcile queue/history before retrying.",
                prompt_id=requested_prompt_id, remote_state_unknown=True)

        watchdog = watchdog or ensure_prompt_watchdog(comfy_url=comfy_url, prompt_id=prompt_id)
        history_url = f"{comfy_url}/history/{prompt_id}"
        deadline = time.time() + timeout_seconds
        consecutive_poll_errors = 0
        next_telemetry = time.monotonic()
        while time.time() < deadline:
            try:
                watchdog.check()
            except GPUAdmissionError as exc:
                raise MediaJobError(str(exc), prompt_id=str(prompt_id), remote_state_unknown=True) from exc
            if time.monotonic() >= next_telemetry:
                try:
                    sample = inspect_gpu_runtime(comfy_url=comfy_url, expected_prompt_id=str(prompt_id),
                                                 workload_started_at=workload_started_at)
                except GPUAdmissionError as exc:
                    raise MediaJobError(
                        f"GPU runtime monitoring failed; remote render may still be active: {exc}",
                        prompt_id=str(prompt_id), remote_state_unknown=True) from exc
                record_gpu_telemetry(telemetry_path, sample, workload_id=workload_id, phase="render")
                next_telemetry = time.monotonic() + 10
            try:
                with urllib.request.urlopen(history_url, timeout=30) as response:
                    history = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                # A transient health/API miss does not mean a costly model
                # render stopped. Keep its prompt ID and continue polling up
                # to the job deadline; never submit a replacement here.
                consecutive_poll_errors += 1
                if consecutive_poll_errors == 1 or consecutive_poll_errors % 10 == 0:
                    LOGGER.warning("Comfy history polling temporarily unavailable prompt_id=%s "
                                   "consecutive_errors=%d error=%s: %s",
                                   prompt_id, consecutive_poll_errors, type(exc).__name__, exc)
                time.sleep(2)
                continue
            if consecutive_poll_errors:
                LOGGER.info("Comfy history polling recovered prompt_id=%s after transient_errors=%d",
                            prompt_id, consecutive_poll_errors)
                consecutive_poll_errors = 0
            prompt_state = history.get(prompt_id)
            if prompt_state:
                status = prompt_state.get("status", {})
                if status.get("status_str") == "error":
                    raise MediaJobError(f"ComfyUI prompt failed: {status.get('messages', [])}",
                                        prompt_id=str(prompt_id))
                if status.get("completed"):
                    release_comfyui_models_if_idle(comfy_url=comfy_url)
                    try:
                        sample = inspect_gpu_runtime(comfy_url=comfy_url, workload_started_at=workload_started_at)
                    except GPUAdmissionError as exc:
                        LOGGER.warning("GPU post-release verification unavailable prompt_id=%s error=%s",
                                       prompt_id, exc)
                        record_gpu_telemetry(telemetry_path,
                            {"recorded_at": datetime.now(timezone.utc).isoformat(),
                             "post_release_verification_error": str(exc)},
                            workload_id=workload_id, phase="after_model_release_unverified")
                    else:
                        record_gpu_telemetry(telemetry_path, sample, workload_id=workload_id,
                                             phase="after_model_release")
                    return str(prompt_id), prompt_state
            time.sleep(2)
        raise MediaJobError(
            f"Timed out waiting for ComfyUI prompt {prompt_id}; remote state is unknown. "
            "Reconcile this exact prompt before retrying.",
            prompt_id=str(prompt_id), remote_state_unknown=True)


def collect_outputs(history: dict[str, Any], *, destination_dir: Path, comfy_url: str) -> list[dict[str, Any]]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    collected: list[dict[str, Any]] = []
    for node_output in history.get("outputs", {}).values():
        for image in node_output.get("images", []):
            copied = _copy_image_output(image, destination_dir, comfy_url)
            if copied is not None:
                kind = "video" if copied.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"} else "image"
                collected.append({"kind": kind, "relative_path": copied.name, "filename": copied.name})
        for video in node_output.get("gifs", []) + node_output.get("videos", []):
            copied = _copy_binary_output(video, destination_dir, comfy_url)
            if copied is not None:
                collected.append({"kind": "video", "relative_path": copied.name, "filename": copied.name})
        audio_items = node_output.get("audio", []) + node_output.get("audios", [])
        for audio in audio_items:
            copied = _copy_binary_output(audio, destination_dir, comfy_url)
            if copied is not None:
                collected.append({"kind": "audio", "relative_path": copied.name, "filename": copied.name})
    return collected


def _copy_image_output(image: dict[str, Any], destination_dir: Path, comfy_url: str) -> Path | None:
    params = urllib.parse.urlencode(
        {"filename": image.get("filename", ""), "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}
    )
    view_url = f"{comfy_url}/view?{params}"
    return _download_output(view_url, destination_dir, image.get("filename", "output.png"))


def _copy_binary_output(data: dict[str, Any], destination_dir: Path, comfy_url: str) -> Path | None:
    params = urllib.parse.urlencode(
        {"filename": data.get("filename", ""), "subfolder": data.get("subfolder", ""), "type": data.get("type", "output")}
    )
    view_url = f"{comfy_url}/view?{params}"
    return _download_output(view_url, destination_dir, data.get("filename", "output.bin"))


def _download_output(url: str, destination_dir: Path, filename: str) -> Path | None:
    safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
    path = destination_dir / safe_name
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    except urllib.error.URLError:
        return None
    return path


def save_uploaded_asset(upload_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / f"{uuid.uuid4().hex}_{upload_path.name}"
    shutil.copy2(upload_path, target)
    return target
