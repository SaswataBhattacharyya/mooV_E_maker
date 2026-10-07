"""Explicit host-I/O isolation for ComfyUI state-machine unit tests.

These tests exercise queue/recovery behavior using synthetic ComfyUI replies;
GPU policy and watchdog behavior have separate tests with injected readers.
"""
from types import SimpleNamespace
import pytest


@pytest.fixture(autouse=True)
def isolate_comfy_state_machine_host_io(request, monkeypatch, tmp_path):
    if request.module.__name__.split(".")[-1] not in {
        "test_media_jobs", "test_production_job_worker", "test_production_image_jobs"
    }:
        return
    from story_builder.services import media_jobs, production_job_worker, production_image_worker
    monkeypatch.setenv("STORY_BUILDER_COMFY_SUBMISSION_LOCK", str(tmp_path / "comfy.lock"))
    for module in (media_jobs, production_job_worker, production_image_worker):
        monkeypatch.setattr(module, "inspect_gpu_runtime", lambda **kwargs: {
            "gpu": {"temperature_c": 45, "graphics_clock_mhz": 300},
            "comfyui": {"free_bytes": 100 * 1024**3}})
        monkeypatch.setattr(module, "record_gpu_telemetry", lambda *args, **kwargs: None)
        monkeypatch.setattr(module, "ensure_prompt_watchdog", lambda **kwargs: SimpleNamespace(check=lambda: None))
        monkeypatch.setattr(module, "finish_prompt_watchdog", lambda **kwargs: None)
    for module in (production_job_worker, production_image_worker):
        monkeypatch.setattr(module, "read_gpu_operating_point", lambda: {
            "temperature_c": 45., "graphics_clock_mhz": 300.})
