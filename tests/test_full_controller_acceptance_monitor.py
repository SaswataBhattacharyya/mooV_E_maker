import json
import pytest

from story_builder.scripts.full_controller_text_acceptance import terminal_outcome, write_terminal_result


def test_acceptance_runner_help_has_no_provider_or_run_side_effects():
    import os
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "full_controller_text_acceptance.py"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, str(script), "--help"], env=env,
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0
    assert "--model" in result.stdout
    assert "PROVIDER_SMOKE" not in result.stdout
    assert "PROJECT_RUN" not in result.stdout


def test_acceptance_runner_requires_explicit_model_without_provider_side_effects():
    import os
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "full_controller_text_acceptance.py"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, str(script)], env=env,
        capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 2
    assert "--model" in result.stderr
    assert "PROVIDER_SMOKE" not in result.stdout
    assert "PROJECT_RUN" not in result.stdout


def test_terminal_result_is_atomically_persisted(tmp_path):
    result = {"model": "gpt-6-sol", "outcome": {"outcome": "interrupted"}}
    target = write_terminal_result(tmp_path, result)
    assert target.name == "acceptance_result.json"
    assert json.loads(target.read_text()) == result
    assert not target.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_attempt_keeps_monitor_waiting(status):
    assert terminal_outcome([{"task_id": "a", "stage": "controller:scene_outline", "status": status}], {}) is None


@pytest.mark.parametrize("status", ["failed", "cancelled", "recovery_required"])
def test_terminal_outline_stops_without_waiting_for_nonexistent_shot_plans(status):
    result = terminal_outcome([{"task_id": "a", "stage": "controller:scene_outline", "status": status}], {})
    assert result == {"outcome": "held", "stage": "controller:scene_outline", "status": status, "error": None}


def test_completed_but_unaccepted_revision_does_not_pass():
    task = {"task_id": "a", "stage": "text:shot_plans", "status": "completed", "result": {"revision_id": "r"}}
    assert terminal_outcome([task], {})["outcome"] == "held"
    assert terminal_outcome([task], {"r": {"review_status": "pending_director_repair"}})["outcome"] == "held"
    assert terminal_outcome([task], {"r": {"review_status": "accepted"}})["outcome"] == "passed"


def test_failed_attempt_does_not_mask_durable_queued_retry(tmp_path):
    from story_builder.services.production_stage_tasks import ProductionStageTaskStore

    path = tmp_path / "tasks.sqlite3"
    store = ProductionStageTaskStore(path)
    first = store.enqueue(project_id="p", run_id="r", stage="controller:scene_outline",
        idempotency_key="first", request={"source_revision_id": "story"})
    store.claim(task_id=first["task_id"], owner_token="owner")
    store.fail(task_id=first["task_id"], owner_token="owner", error={"code": "unsupported_identity", "retryable": True})
    assert terminal_outcome(store.list_run(project_id="p", run_id="r"), {})["outcome"] == "held"
    retry = store.enqueue(project_id="p", run_id="r", stage="controller:scene_outline",
        idempotency_key="retry", request={"source_revision_id": "story"})
    reopened = ProductionStageTaskStore(path)
    assert terminal_outcome(reopened.list_run(project_id="p", run_id="r"), {}) is None
    reopened.claim(task_id=retry["task_id"], owner_token="owner")
    reopened.complete(task_id=retry["task_id"], owner_token="owner", result={"units": [{"unit_id": "scene"}]})
    shot = reopened.enqueue(project_id="p", run_id="r", stage="text:shot_plans",
        idempotency_key="shot", request={"source_revision_id": "story"})
    reopened.claim(task_id=shot["task_id"], owner_token="owner")
    reopened.complete(task_id=shot["task_id"], owner_token="owner", result={"revision_id": "accepted-shots"})
    assert terminal_outcome(ProductionStageTaskStore(path).list_run(project_id="p", run_id="r"),
        {"accepted-shots": {"review_status": "accepted"}})["outcome"] == "passed"


def test_interruption_during_provider_preflight_writes_terminal_result(tmp_path, monkeypatch, capsys):
    import json
    import sys
    import tempfile
    from story_builder.api import main as api
    from story_builder.scripts import full_controller_text_acceptance as runner
    from story_builder.services import reasoning_provider

    original_model = reasoning_provider.DEFAULT_CODEX_MODEL
    original = {name: getattr(api, name) for name in (
        "STORAGE_ROOT", "PROJECT_STORE", "UPLOADS_ROOT", "OUTPUT_ROOT",
        "AUDIO_LIBRARY_ROOT", "_production_story_task_stop")}
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix: str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["full_controller_text_acceptance.py", "--model", "gpt-6-sol"])
    def interrupt(_provider):
        raise KeyboardInterrupt
    monkeypatch.setattr(reasoning_provider, "test_provider", interrupt)
    try:
        assert runner.main() == 130
        result = json.loads((tmp_path / "acceptance_result.json").read_text())
        assert result["model"] == "gpt-6-sol"
        assert reasoning_provider.DEFAULT_CODEX_MODEL == "gpt-6-sol"
        assert result["outcome"] == {"outcome": "interrupted", "status": "operator_interrupt"}
        assert result["owned_worker_settled"] is True
        assert "ACCEPTANCE_RESULT" in capsys.readouterr().out
    finally:
        for name, value in original.items():
            setattr(api, name, value)
        reasoning_provider.DEFAULT_CODEX_MODEL = original_model
