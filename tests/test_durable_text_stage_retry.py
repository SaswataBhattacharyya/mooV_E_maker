import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from retry_durable_text_stage import (_require_api_stopped, retry_idempotency_key,
    settled_retry_outcome, validate_retry_history)


@pytest.mark.parametrize("error", [PermissionError("sandbox"), TimeoutError("uncertain"), OSError("offline")])
def test_api_stopped_check_preserves_uncertain_network_state(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr("retry_durable_text_stage.socket.create_connection", fail)
    with pytest.raises(RuntimeError, match="Cannot verify"):
        _require_api_stopped(3010)


def test_api_stopped_check_accepts_only_connection_refused(monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionRefusedError("no listener")
    monkeypatch.setattr("retry_durable_text_stage.socket.create_connection", fail)
    _require_api_stopped(3010)


@pytest.mark.parametrize("change,reason", [
    ({"review_status": "pending_director_repair"}, "director_not_accepted"),
    ({"review_status": "pending_review"}, "director_not_accepted"),
    ({"stage_task_request_hash": "changed"}, "canonical_revision_or_provenance_mismatch"),
    ({"stage_task_id": "other"}, "canonical_revision_or_provenance_mismatch"),
    ({"model": "gpt-6-luna"}, "canonical_revision_or_provenance_mismatch"),
    ({"run_id": "other"}, "canonical_revision_or_provenance_mismatch"),
    ({}, None),
])
def test_retry_exit_requires_canonical_director_acceptance_after_reopen(tmp_path, change, reason):
    from story_builder.services import production_story_revisions as revisions
    task = {"task_id": "retry", "request_hash": "hash", "status": "completed",
        "result": {"revision_id": "shot_plans-012345abcdef", "provider": "codex", "model": "gpt-6-sol"}}
    revision = {"schema_version": 1, "revision_id": "shot_plans-012345abcdef",
        "project_id": "project", "run_id": "12345678-1234-5678-1234-567812345678", "stage": "shot_plans",
        "stage_task_id": "retry", "stage_task_request_hash": "hash", "provider": "codex",
        "model": "gpt-6-sol", "review_status": "accepted", "items": [], **change}
    # Save/load real canonical JSON; a completed queue row cannot invent its review.
    revisions.write_stage_revision(tmp_path, "project", "12345678-1234-5678-1234-567812345678", "shot_plans", revision)
    reopened = revisions.load_stage_revision(tmp_path, "project", "12345678-1234-5678-1234-567812345678", "shot_plans", "shot_plans-012345abcdef")
    result = settled_retry_outcome(task, reopened, project_id="project", run_id="12345678-1234-5678-1234-567812345678", model="gpt-6-sol")
    assert result["outcome"] == ("held" if reason else "passed")
    if reason:
        assert result["reason"] == reason


def _failed(task_id: str, created_at: str, *, key: str | None = None, request_hash: str = "same"):
    return {"task_id": task_id, "stage": "text:shot_plans", "created_at": created_at,
        "status": "failed", "error": {"retryable": True}, "request_hash": request_hash,
        "idempotency_key": key or task_id}


def test_retry_preflight_selects_only_latest_of_exactly_two_identical_failed_requests():
    tasks = [_failed("first", "2026-01-01T00:00:00+00:00"),
        _failed("second", "2026-01-01T00:00:01+00:00")]
    target = validate_retry_history(tasks, task_id="second", key="stage-only:second:gpt-6-sol:v1")
    assert target["task_id"] == "second"
    assert retry_idempotency_key(task_id="second", model="gpt-6-sol") == "stage-only:second:gpt-6-sol:v1"


@pytest.mark.parametrize("change,match", [
    (lambda rows: rows.append(_failed("third", "2026-01-01T00:00:02+00:00")), "exactly two"),
    (lambda rows: rows.append({"task_id": "active", "status": "running", "stage": "text:dialogue"}), "running"),
    (lambda rows: rows[0].update(request_hash="different"), "exact saved request"),
    (lambda rows: rows[1].update(error={"retryable": False}), "not marked retryable"),
])
def test_retry_preflight_fails_closed_on_budget_or_state_drift(change, match):
    tasks = [_failed("first", "2026-01-01T00:00:00+00:00"),
        _failed("second", "2026-01-01T00:00:01+00:00")]
    change(tasks)
    with pytest.raises(ValueError, match=match):
        validate_retry_history(tasks, task_id="second", key="new-key")


def test_retry_preflight_rejects_reusing_its_stable_key():
    tasks = [_failed("first", "2026-01-01T00:00:00+00:00"),
        _failed("second", "2026-01-01T00:00:01+00:00"),
        {"task_id": "retry", "stage": "text:shot_plans",
            "idempotency_key": "stage-only:second:gpt-6-sol:v1", "status": "completed"}]
    with pytest.raises(ValueError, match="already been used"):
        validate_retry_history(tasks, task_id="second", key="stage-only:second:gpt-6-sol:v1")


@pytest.mark.parametrize("runner", ["retry_durable_text_stage.py", "repair_held_shot_plan.py"])
def test_cli_help_is_side_effect_free(tmp_path, runner):
    root = Path(__file__).resolve().parents[1]
    # Fail if argument inspection reaches application imports. API imports can
    # initialize stores; checking stdout alone would not detect that side effect.
    marker = tmp_path / "application-import-attempted"
    (tmp_path / "sitecustomize.py").write_text(
        "import builtins\n"
        "from pathlib import Path\n"
        "original_import = builtins.__import__\n"
        "def guarded_import(name, *args, **kwargs):\n"
        "    if name == 'story_builder' or name.startswith('story_builder.'):\n"
        f"        Path({str(marker)!r}).write_text(name)\n"
        "        raise RuntimeError('help must not initialize the application')\n"
        "    return original_import(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded_import\n"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(root.parent)]),
        "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, str(root / "scripts" / runner),
        "--help"], cwd=root, env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert "--execute" in result.stdout
    assert "--confirm-provider-content-egress" in result.stdout
    assert "preflight_passed" not in result.stdout
    assert not marker.exists(), result.stderr


def test_accepted_text_first_image_preflight_does_not_require_or_create_image_schema(tmp_path):
    import json
    import sqlite3
    from acceptance_automatic_image_master import validate_accepted_text_root_readonly
    from story_builder.services.production_ledger import ProductionLedger
    from story_builder.services.production_stage_tasks import ProductionStageTaskStore
    from story_builder.services import production_story_revisions as revisions
    db_path = tmp_path / "storage" / "production" / "v2_ledger.sqlite3"
    ledger = ProductionLedger(db_path)
    run = ledger.create_run(project_id="prefix", idempotency_key="prefix",
        config={"control_mode": "fully_automated", "making_route": "reference_built"})
    store = ProductionStageTaskStore(db_path)
    output = tmp_path / "output"
    report = {"project_id": "prefix", "run_id": run["run_id"],
        "outcome": {"outcome": "passed", "stage": "text:shot_plans"}, "revisions": []}
    for stage in ("story_detail", "scenes", "dialogue", "visual_briefs", "shot_plans"):
        rid = ("story-canon" if stage == "story_detail" else stage) + "-012345abcdef"
        revision = {"revision_id": rid, "review_status": "accepted"}
        if stage == "story_detail":
            revisions.write_revision(output, "prefix", run["run_id"], revision)
        else:
            revisions.write_stage_revision(output, "prefix", run["run_id"], stage, revision)
        task = store.enqueue(project_id="prefix", run_id=run["run_id"],
            stage="story_detail" if stage == "story_detail" else f"text:{stage}",
            idempotency_key=stage, request={})
        assert store.claim(task_id=task["task_id"], owner_token="owner")
        store.complete(task_id=task["task_id"], owner_token="owner", result={"revision_id": rid})
        report["revisions"].append({"stage": stage, **revision})
    (tmp_path / "targeted_resume_result.json").write_text(json.dumps(report))
    actual = validate_accepted_text_root_readonly(tmp_path)
    assert actual["image_queue_not_prepared"] is True
    assert actual["controller_queued_jobs"] == []
    with sqlite3.connect(db_path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='production_image_jobs'").fetchone()
    ledger.record_run_event(project_id="prefix", run_id=run["run_id"],
        event_type="controller_image_masters_queued", payload={"pending": []})
    with pytest.raises(RuntimeError, match="prior media work"):
        validate_accepted_text_root_readonly(tmp_path)
