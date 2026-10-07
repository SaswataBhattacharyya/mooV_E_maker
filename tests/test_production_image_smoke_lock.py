from __future__ import annotations

from contextlib import contextmanager
import urllib.error
from unittest.mock import patch

import pytest
from scripts import smoke_production_image_workflow as smoke


def test_image_smoke_holds_shared_comfy_lock_for_entire_job(monkeypatch):
    events: list[str] = []

    @contextmanager
    def guard():
        events.append("lock_acquired")
        try:
            yield
        finally:
            events.append("lock_released")

    def run_locked():
        events.append("job")
        assert events == ["lock_acquired", "job"]
        return 23

    monkeypatch.setattr(smoke, "comfy_submission_guard", guard)
    monkeypatch.setattr(smoke, "_main_locked", run_locked)

    assert smoke.main() == 23
    assert events == ["lock_acquired", "job", "lock_released"]


@pytest.mark.parametrize(
    ("submitted", "status", "expected"),
    [
        (False, "failed", False),
        (False, "completed", False),
        (True, "running", False),
        (True, "recovery_pending", False),
        (True, "failed", True),
        (True, "completed", True),
    ],
)
def test_image_smoke_unloads_only_its_own_terminal_job(submitted, status, expected):
    assert smoke.may_release_models(submitted=submitted, status=status) is expected


def test_image_smoke_http_error_keeps_comfy_validation_body(monkeypatch):
    error = urllib.error.HTTPError(
        "http://comfy/prompt", 400, "Bad Request", {}, None
    )
    error.read = lambda: b'{"node_errors":{"17":{"errors":["invalid image size"]}}}'
    monkeypatch.setattr(smoke, "COMFY_URL", "http://comfy")
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(RuntimeError, match="invalid image size"):
            smoke.request_json("/prompt", payload={"prompt": {}})
