from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from story_builder.services.gpu_runtime import MIN_FREE_BYTES
from story_builder.services.media_jobs import MediaJobError, release_comfyui_models_if_idle, submit_and_wait


def _response(payload: dict):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(payload).encode()
    return response


def test_comfy_cleanup_requests_model_unload_only_when_queue_is_idle():
    with patch("story_builder.services.media_jobs.urllib.request.urlopen",
               side_effect=[_response({"queue_running": [], "queue_pending": []}), _response({}),
                            _response({"devices": [{"vram_free": MIN_FREE_BYTES}]})]) as open_url:
        result = release_comfyui_models_if_idle(comfy_url="http://comfy:3008/")
    assert result == {"status": "headroom_verified", "unload_request_accepted": True,
                      "vram_free_bytes": MIN_FREE_BYTES, "required_free_bytes": MIN_FREE_BYTES}
    request = open_url.call_args_list[1].args[0]
    assert request.full_url == "http://comfy:3008/free"
    assert json.loads(request.data) == {"unload_models": True, "free_memory": True}


def test_comfy_cleanup_reports_unverified_when_headroom_does_not_return():
    with patch("story_builder.services.media_jobs.urllib.request.urlopen", side_effect=[
            _response({"queue_running": [], "queue_pending": []}), _response({}),
            _response({"devices": [{"vram_free": MIN_FREE_BYTES - 1}]})]), \
         patch("story_builder.services.media_jobs.time.monotonic", side_effect=[0, 11]), \
         patch("story_builder.services.media_jobs.time.sleep"):
        result = release_comfyui_models_if_idle(comfy_url="http://comfy:3008", timeout_seconds=10)
    assert result["status"] == "unverified"
    assert result["unload_request_accepted"] is True
    assert result["vram_free_bytes"] == MIN_FREE_BYTES - 1
    assert result["required_free_bytes"] == MIN_FREE_BYTES


def test_comfy_cleanup_polls_until_delayed_headroom_recovery():
    with patch("story_builder.services.media_jobs.urllib.request.urlopen", side_effect=[
            _response({"queue_running": [], "queue_pending": []}), _response({}),
            _response({"devices": [{"vram_free": MIN_FREE_BYTES - 1024}]}),
            _response({"devices": [{"vram_free": MIN_FREE_BYTES + 1024}]})]) as open_url, \
         patch("story_builder.services.media_jobs.time.monotonic", side_effect=[0, 1]), \
         patch("story_builder.services.media_jobs.time.sleep") as sleep:
        result = release_comfyui_models_if_idle(comfy_url="http://comfy:3008", timeout_seconds=3)
    assert result["status"] == "headroom_verified"
    assert result["unload_request_accepted"] is True
    assert result["vram_free_bytes"] == MIN_FREE_BYTES + 1024
    assert open_url.call_count == 4
    sleep.assert_called_once()


def test_comfy_cleanup_does_not_unload_while_other_work_is_queued():
    with patch("story_builder.services.media_jobs.urllib.request.urlopen",
               return_value=_response({"queue_running": [[1]], "queue_pending": []})) as open_url:
        result = release_comfyui_models_if_idle(comfy_url="http://comfy:3008")
    assert result == {"status": "deferred", "reason": "comfyui_queue_not_empty", "running": 1, "pending": 0}
    open_url.assert_called_once()


def test_comfy_cleanup_failure_is_nonfatal():
    with patch("story_builder.services.media_jobs.urllib.request.urlopen", side_effect=OSError("offline")):
        result = release_comfyui_models_if_idle(comfy_url="http://comfy:3008")
    assert result["status"] == "unavailable"
    assert "offline" in result["reason"]


def test_site_submission_waits_for_shared_comfy_queue_before_posting(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_BUILDER_COMFY_SUBMISSION_LOCK", str(tmp_path / "comfy.lock"))
    events = []
    queue_responses = iter([
        {"queue_running": [[1, "external"]], "queue_pending": []},
        {"queue_running": [], "queue_pending": []},
    ])

    def open_url(target, timeout=0):
        if isinstance(target, str) and target.endswith("/queue"):
            events.append("queue")
            return _response(next(queue_responses))
        if isinstance(target, str) and "/history/" in target:
            events.append("history")
            return _response({"p-1": {"status": {"completed": True}, "outputs": {}}})
        if getattr(target, "full_url", "").endswith("/prompt"):
            events.append("submit")
            return _response({"prompt_id": "p-1"})
        raise AssertionError(f"Unexpected URL: {target}")

    with patch("story_builder.services.media_jobs.urllib.request.urlopen", side_effect=open_url), \
         patch("story_builder.services.media_jobs.time.sleep"), \
         patch("story_builder.services.media_jobs.release_comfyui_models_if_idle", return_value={"status": "requested"}):
        prompt_id, _ = submit_and_wait({"1": {"class_type": "Test"}}, comfy_url="http://comfy", timeout_seconds=5)

    assert prompt_id == "p-1"
    assert events == ["queue", "queue", "submit", "history"]


def test_site_submission_fails_closed_if_comfy_queue_cannot_be_verified(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_BUILDER_COMFY_SUBMISSION_LOCK", str(tmp_path / "comfy.lock"))
    with patch("story_builder.services.media_jobs.urllib.request.urlopen", return_value=_response({"unexpected": []})) as open_url:
        with pytest.raises(MediaJobError, match="invalid /queue"):
            submit_and_wait({"1": {"class_type": "Test"}}, comfy_url="http://comfy", timeout_seconds=1)
    open_url.assert_called_once()


def test_transient_history_api_failure_does_not_fail_or_resubmit_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_BUILDER_COMFY_SUBMISSION_LOCK", str(tmp_path / "comfy.lock"))
    events = []

    def open_url(target, timeout=0):
        if isinstance(target, str) and target.endswith("/queue"):
            events.append("queue")
            return _response({"queue_running": [], "queue_pending": []})
        if getattr(target, "full_url", "").endswith("/prompt"):
            events.append("submit")
            return _response({"prompt_id": "long-render-1"})
        if isinstance(target, str) and "/history/" in target:
            events.append("history")
            if events.count("history") == 1:
                raise urllib.error.URLError("temporary ComfyUI health miss")
            return _response({"long-render-1": {"status": {"completed": True}, "outputs": {}}})
        raise AssertionError(f"Unexpected URL: {target}")

    with patch("story_builder.services.media_jobs.urllib.request.urlopen", side_effect=open_url), \
         patch("story_builder.services.media_jobs.time.sleep"), \
         patch("story_builder.services.media_jobs.release_comfyui_models_if_idle", return_value={"status": "requested"}):
        prompt_id, history = submit_and_wait({"1": {"class_type": "Test"}},
            comfy_url="http://comfy", timeout_seconds=5)

    assert prompt_id == "long-render-1"
    assert history["status"]["completed"] is True
    assert events.count("submit") == 1
    assert events.count("history") == 2


def test_render_timeout_keeps_prompt_id_and_marks_remote_state_unknown(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_BUILDER_COMFY_SUBMISSION_LOCK", str(tmp_path / "comfy.lock"))
    clock = iter([0.0, 2.0, 2.0, 4.0, 4.0])

    def open_url(target, timeout=0):
        if isinstance(target, str) and target.endswith("/queue"):
            return _response({"queue_running": [], "queue_pending": []})
        if getattr(target, "full_url", "").endswith("/prompt"):
            return _response({"prompt_id": "long-render-timeout"})
        if isinstance(target, str) and "/history/" in target:
            return _response({})
        raise AssertionError(f"Unexpected URL: {target}")

    with patch("story_builder.services.media_jobs.urllib.request.urlopen", side_effect=open_url), \
         patch("story_builder.services.media_jobs.time.time", side_effect=lambda: next(clock)), \
         patch("story_builder.services.media_jobs.time.sleep"), \
         pytest.raises(MediaJobError, match="Reconcile this exact prompt") as error:
        submit_and_wait({"1": {"class_type": "Test"}}, comfy_url="http://comfy", timeout_seconds=3)

    assert error.value.prompt_id == "long-render-timeout"
    assert error.value.remote_state_unknown is True


def test_ambiguous_prompt_post_is_not_reported_as_a_safe_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_BUILDER_COMFY_SUBMISSION_LOCK", str(tmp_path / "comfy.lock"))
    calls = []

    def open_url(target, timeout=0):
        calls.append(target)
        if isinstance(target, str) and target.endswith("/queue"):
            return _response({"queue_running": [], "queue_pending": []})
        raise urllib.error.URLError("connection closed after POST")

    with patch("story_builder.services.media_jobs.urllib.request.urlopen", side_effect=open_url):
        with pytest.raises(MediaJobError, match="outcome is unknown") as error:
            submit_and_wait({"1": {"class_type": "Test"}}, comfy_url="http://comfy", timeout_seconds=2)

    assert error.value.remote_state_unknown is True
    assert error.value.prompt_id is None
    assert sum(1 for target in calls if isinstance(target, urllib.request.Request)) == 1


def test_reserved_prompt_id_is_posted_and_returned(monkeypatch, tmp_path):
    monkeypatch.setenv('STORY_BUILDER_COMFY_SUBMISSION_LOCK', str(tmp_path / 'comfy.lock'))
    requests = []
    def open_url(target, timeout=0):
        if isinstance(target, str) and target.endswith('/queue'):
            return _response({'queue_running': [], 'queue_pending': []})
        if getattr(target, 'full_url', '').endswith('/prompt'):
            requests.append(json.loads(target.data))
            return _response({'prompt_id': 'reserved-render'})
        if isinstance(target, str) and '/history/' in target:
            return _response({'reserved-render': {'status': {'completed': True}, 'outputs': {}}})
        raise AssertionError(target)
    with patch('story_builder.services.media_jobs.urllib.request.urlopen', side_effect=open_url), \
         patch('story_builder.services.media_jobs.release_comfyui_models_if_idle'):
        prompt_id, _ = submit_and_wait({}, comfy_url='http://comfy', prompt_id='reserved-render')
    assert prompt_id == 'reserved-render'
    assert requests == [{'prompt': {}, 'prompt_id': 'reserved-render'}]


@pytest.mark.parametrize('response', [{}, {'prompt_id': 'unexpected-id'}])
def test_unexpected_submission_response_retains_reserved_id_for_recovery(monkeypatch, tmp_path, response):
    monkeypatch.setenv('STORY_BUILDER_COMFY_SUBMISSION_LOCK', str(tmp_path / 'comfy.lock'))
    with patch('story_builder.services.media_jobs.urllib.request.urlopen', side_effect=[
            _response({'queue_running': [], 'queue_pending': []}), _response(response)]) as open_url:
        with pytest.raises(MediaJobError) as error:
            submit_and_wait({}, comfy_url='http://comfy', prompt_id='reserved-render')
    assert error.value.prompt_id == 'reserved-render'
    assert error.value.remote_state_unknown is True
    assert open_url.call_count == 2


def test_submission_socket_timeout_retains_reserved_id(monkeypatch, tmp_path):
    monkeypatch.setenv('STORY_BUILDER_COMFY_SUBMISSION_LOCK', str(tmp_path / 'comfy.lock'))
    with patch('story_builder.services.media_jobs.urllib.request.urlopen', side_effect=[
            _response({'queue_running': [], 'queue_pending': []}), TimeoutError('POST timed out')]):
        with pytest.raises(MediaJobError) as error:
            submit_and_wait({}, comfy_url='http://comfy', prompt_id='reserved-render')
    assert error.value.prompt_id == 'reserved-render'
    assert error.value.remote_state_unknown is True
