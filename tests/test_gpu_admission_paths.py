from __future__ import annotations

from contextlib import contextmanager
import asyncio

import pytest

from story_builder.services import audio_utilities
from story_builder.services import ollama_client
from story_builder.api import main as api


def test_audio_gpu_command_holds_shared_lease_and_waits_for_comfy_queue(monkeypatch):
    events: list[str] = []
    state = {"locked": False}

    @contextmanager
    def fake_guard():
        events.append("lease_acquired")
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False
            events.append("lease_released")

    def fake_wait(*, comfy_url, timeout_seconds):
        assert state["locked"]
        assert comfy_url == audio_utilities.COMFYUI_URL
        assert timeout_seconds > 0
        events.append("comfy_idle")

    def fake_run(command, *, timeout):
        assert state["locked"]
        assert events[-1] == "comfy_idle"
        assert command == ["docker", "exec", "story-audio-demucs"]
        assert timeout == 123
        events.append("gpu_command")

    @contextmanager
    def fake_gpu_guard(**_kwargs):
        with fake_guard():
            fake_wait(comfy_url=audio_utilities.COMFYUI_URL, timeout_seconds=24 * 3600)
            yield

    monkeypatch.setattr(audio_utilities, "gpu_workload_guard", fake_gpu_guard)
    monkeypatch.setattr(audio_utilities, "_run", fake_run)

    audio_utilities._run_gpu_command(["docker", "exec", "story-audio-demucs"], timeout=123)

    assert events == ["lease_acquired", "comfy_idle", "gpu_command", "lease_released"]


def test_audio_gpu_command_fails_closed_when_comfy_queue_cannot_be_verified(monkeypatch):
    command_started = False

    @contextmanager
    def fake_guard():
        yield

    def unavailable_queue(**_kwargs):
        raise RuntimeError("queue unavailable")

    def forbidden_run(*_args, **_kwargs):
        nonlocal command_started
        command_started = True

    @contextmanager
    def unavailable_gpu_guard(**_kwargs):
        with fake_guard():
            unavailable_queue()
            yield

    monkeypatch.setattr(audio_utilities, "gpu_workload_guard", unavailable_gpu_guard)
    monkeypatch.setattr(audio_utilities, "_run", forbidden_run)

    try:
        audio_utilities._run_gpu_command(["docker", "exec", "story-audio-demucs"])
    except RuntimeError as exc:
        assert "queue unavailable" in str(exc)
    else:
        raise AssertionError("GPU audio command should fail closed")

    assert not command_started


def test_non_gpu_audio_extract_does_not_take_gpu_lease(monkeypatch):
    """MP3 extraction remains a CPU/FFmpeg operation and doesn't block GPU work."""
    # This protects the distinction: only the CUDA-backed operations are
    # serialized; ordinary FFmpeg extraction remains unchanged.
    calls: list[tuple[list[str], int]] = []
    monkeypatch.setattr(audio_utilities, "_run", lambda command, timeout=3600: calls.append((command, timeout)))
    audio_utilities._run(["ffmpeg", "-version"], timeout=10)
    assert calls == [(["ffmpeg", "-version"], 10)]


def test_direct_api_gpu_inference_waits_for_comfyui_while_holding_lease(monkeypatch):
    events: list[str] = []
    state = {"locked": False}

    @contextmanager
    def fake_guard():
        events.append("lease_acquired")
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False
            events.append("lease_released")

    def fake_wait(*, comfy_url, timeout_seconds):
        assert state["locked"]
        assert comfy_url == api.COMFYUI_URL
        assert timeout_seconds > 0
        events.append("comfy_idle")

    def inference(query: str) -> dict[str, str]:
        assert state["locked"]
        assert events[-1] == "comfy_idle"
        events.append("inference")
        return {"query": query}

    @contextmanager
    def fake_gpu_guard(**_kwargs):
        with fake_guard():
            fake_wait(comfy_url=api.COMFYUI_URL, timeout_seconds=24 * 3600)
            yield

    monkeypatch.setattr(api, "gpu_workload_guard", fake_gpu_guard)
    result = api._run_with_gpu_admission(inference, query="storm")

    assert result == {"query": "storm"}
    assert events == ["lease_acquired", "comfy_idle", "inference", "lease_released"]


def test_direct_api_gpu_inference_does_not_run_if_queue_check_fails(monkeypatch):
    called = False

    @contextmanager
    def fake_guard():
        yield

    def unavailable_queue(**_kwargs):
        raise RuntimeError("queue unavailable")

    def forbidden_inference():
        nonlocal called
        called = True

    @contextmanager
    def unavailable_gpu_guard(**_kwargs):
        with fake_guard():
            unavailable_queue()
            yield

    monkeypatch.setattr(api, "gpu_workload_guard", unavailable_gpu_guard)

    try:
        api._run_with_gpu_admission(forbidden_inference)
    except RuntimeError as exc:
        assert "queue unavailable" in str(exc)
    else:
        raise AssertionError("GPU inference should fail closed")

    assert not called


def test_ollama_inference_holds_the_shared_gpu_lease(monkeypatch):
    events: list[str] = []
    state = {"locked": False}

    @contextmanager
    def fake_gpu_guard(**kwargs):
        assert kwargs["comfy_url"] == "http://127.0.0.1:3008"
        state["locked"] = True
        events.append("lease_acquired")
        try:
            yield
        finally:
            state["locked"] = False
            events.append("lease_released")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            assert state["locked"]
            events.append("ollama_request")
            return b'{"response":"ready"}'

    monkeypatch.setattr(ollama_client, "gpu_workload_guard", fake_gpu_guard)
    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    answer = ollama_client._generate(prompt="test", model="fixture", temperature=0.0)

    assert answer == "ready"
    assert events == ["lease_acquired", "ollama_request", "lease_released"]


def test_ollama_inference_fails_closed_when_gpu_admission_is_unavailable(monkeypatch):
    from story_builder.services.media_jobs import MediaJobError

    def unavailable_guard(**_kwargs):
        raise MediaJobError("queue unavailable")

    def forbidden_request(*_args, **_kwargs):
        raise AssertionError("Ollama request must not be sent")

    monkeypatch.setattr(ollama_client, "gpu_workload_guard", unavailable_guard)
    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", forbidden_request)

    try:
        ollama_client._generate(prompt="test", model="fixture", temperature=0.0)
    except ollama_client.OllamaError as exc:
        assert "GPU admission blocked" in str(exc)
    else:
        raise AssertionError("Ollama inference should fail closed")


def test_cpu_only_ollama_request_sets_zero_gpu_without_changing_other_options(monkeypatch):
    from contextlib import nullcontext
    import json

    captured = {}
    guard_options = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"response":"ready"}'

    def capture_guard(**kwargs):
        guard_options.update(kwargs)
        return nullcontext()

    monkeypatch.setattr(ollama_client, "gpu_workload_guard", capture_guard)

    def capture(request, **_kwargs):
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", capture)
    assert ollama_client._generate(prompt="test", model="fixture", temperature=0.0, cpu_only=True,
        gpu_admission_timeout_seconds=37) == "ready"
    assert captured["payload"]["options"]["num_gpu"] == 0
    assert guard_options["timeout_seconds"] == 37


def test_default_ollama_request_does_not_override_gpu_placement(monkeypatch):
    from contextlib import nullcontext
    import json

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"response":"ready"}'

    monkeypatch.setattr(ollama_client, "gpu_workload_guard", lambda **_kwargs: nullcontext())

    def capture(request, **_kwargs):
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", capture)
    assert ollama_client._generate(prompt="test", model="fixture", temperature=0.0) == "ready"
    assert "num_gpu" not in captured["payload"]["options"]


def test_sam_route_reports_gpu_admission_failure_as_service_unavailable(monkeypatch):
    from fastapi import HTTPException
    from story_builder.services.media_jobs import MediaJobError

    def unavailable(*_args, **_kwargs):
        raise MediaJobError("ComfyUI queue unavailable")

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(api, "_run_with_gpu_admission", unavailable)
    monkeypatch.setattr(api, "run_in_threadpool", run_inline)

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.isolate_video_audio_event(
            "run-fixture", api.SAMPreviewRequest(event_id="event-fixture", prompt="rain")
        ))

    assert error.value.status_code == 503
    assert "ComfyUI queue unavailable" in error.value.detail
