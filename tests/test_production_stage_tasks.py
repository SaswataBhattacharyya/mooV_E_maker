from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import threading

import pytest

from story_builder.services.production_stage_tasks import ProductionStageTaskStore, StageTaskConflict
from story_builder.api import main as api


def test_live_worker_fences_recovery_even_after_lease_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path)
    store = api._production_stage_task_store()
    task = store.enqueue(project_id="p", run_id="r", stage="story_detail", idempotency_key="live",
                         request={})
    entered, finish = threading.Event(), threading.Event()
    calls = []

    def provider(*_args):
        calls.append(1)
        entered.set()
        assert finish.wait(10)
        return {"revision": {"revision_id": "story-canon-aabbccddeeff"}}

    monkeypatch.setattr(api, "detail_production_v2_story", provider)
    worker = threading.Thread(target=api._execute_production_story_stage_task, args=(task["task_id"],))
    worker.start()
    try:
        assert entered.wait(5)
        with store._connect() as db:
            db.execute("UPDATE production_stage_tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                       (task["task_id"],))
        assert store.get(project_id="p", run_id="r", task_id=task["task_id"])["status"] == "recovery_required"
        with pytest.raises(StageTaskConflict, match="still active"):
            store.resolve_recovery(project_id="p", run_id="r", task_id=task["task_id"],
                                   confirm_no_durable_result=True)
        api._execute_production_story_stage_task(task["task_id"])
        assert calls == [1]
    finally:
        finish.set()
        worker.join(5)
    assert not worker.is_alive()
    completed = store.get(project_id="p", run_id="r", task_id=task["task_id"])
    assert completed["status"] == "completed"
    assert completed["result"]["revision_id"] == "story-canon-aabbccddeeff"


def test_stage_only_text_execution_does_not_advance_controller(tmp_path, monkeypatch):
    """A bounded acceptance retry must stop before downstream image admission."""
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    store = api._production_stage_task_store()
    task = store.enqueue(project_id="p", run_id="r", stage="text:shot_plans",
        idempotency_key="stage-only", request={"source_revision_id": "story-canon-abcdef123456",
            "units": [{"unit_id": "shot-1", "approved_dialogue_lines": []}], "context": {}})
    advances = []
    monkeypatch.setattr(api, "generate_production_v2_text_stage", lambda *_args, **_kwargs: {
        "revision": {"revision_id": "shot_plans-abcdef123456",
            "provider": "codex", "model": "gpt-6-sol"}})
    monkeypatch.setattr(api, "_advance_production_text_controller",
        lambda *args: advances.append(args))

    api._execute_production_story_stage_task(task["task_id"], advance_controller=False)

    settled = store.get(project_id="p", run_id="r", task_id=task["task_id"])
    assert settled["status"] == "completed"
    assert settled["result"]["revision_id"] == "shot_plans-abcdef123456"
    assert settled["result"]["provider"] == "codex"
    assert settled["result"]["model"] == "gpt-6-sol"
    assert advances == []


def test_stage_only_retryable_failure_does_not_auto_retry_or_advance(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    store = api._production_stage_task_store()
    task = store.enqueue(project_id="p", run_id="r", stage="text:shot_plans",
        idempotency_key="stage-only-failure", request={"source_revision_id": "story-canon-abcdef123456",
            "units": [{"unit_id": "shot-1", "approved_dialogue_lines": []}], "context": {}})
    advances = []

    def fail_provider(*_args, **_kwargs):
        raise RuntimeError("synthetic provider failure")

    monkeypatch.setattr(api, "generate_production_v2_text_stage", fail_provider)
    monkeypatch.setattr(api, "_advance_production_text_controller",
        lambda *args: advances.append(args))

    api._execute_production_story_stage_task(task["task_id"], advance_controller=False)

    settled = store.get(project_id="p", run_id="r", task_id=task["task_id"])
    assert settled["status"] == "failed"
    assert settled["error"]["retryable"] is True
    assert advances == []


def test_execution_lock_released_when_owner_process_exits(tmp_path):
    import subprocess
    import sys
    import os
    from pathlib import Path
    store = ProductionStageTaskStore(tmp_path / "stage.sqlite3")
    task = store.enqueue(project_id="p", run_id="r", stage="story_detail", idempotency_key="owner", request={})
    script = ("import sys,time; from story_builder.services.production_stage_tasks import ProductionStageTaskStore; "
              "s=ProductionStageTaskStore(sys.argv[1]); "
              "lock=s.execution_lock(sys.argv[2]); lock.__enter__(); print('locked',flush=True); time.sleep(30)")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    child = subprocess.Popen([sys.executable, "-c", script, str(store.path), task["task_id"]],
                             stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(StageTaskConflict, match="still active"):
            with store.execution_lock(task["task_id"]):
                pass
    finally:
        child.terminate()
        child.wait(timeout=5)
    with store.execution_lock(task["task_id"]):
        assert child.poll() is not None


def test_worker_process_exit_during_provider_call_requires_reconciliation_not_resubmit(tmp_path):
    """A fresh worker process must not repeat an ambiguous in-flight provider call."""
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    storage = tmp_path / "storage"
    path = storage / "production" / "v2_ledger.sqlite3"
    store = ProductionStageTaskStore(path)
    task = store.enqueue(project_id="p", run_id="r", stage="story_detail",
                         idempotency_key="process-crash", request={})
    provider_started = tmp_path / "provider-started"
    provider_calls = tmp_path / "provider-calls"
    worker_script = r'''import pathlib, sys, time
from story_builder.api import main as api
api.STORAGE_ROOT = pathlib.Path(sys.argv[1])
task_id, marker, calls = sys.argv[2:]
def blocked_provider(*args, **kwargs):
    with open(calls, "a", encoding="utf-8") as handle:
        handle.write("call\\n")
    pathlib.Path(marker).write_text("inference started", encoding="utf-8")
    while True:
        time.sleep(0.05)
api.detail_production_v2_story = blocked_provider
api._execute_production_story_stage_task(task_id)
'''
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    def start_worker():
        return subprocess.Popen([sys.executable, "-c", worker_script, str(storage), task["task_id"],
                                 str(provider_started), str(provider_calls)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

    first = start_worker()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not provider_started.exists():
            if first.poll() is not None:
                pytest.fail("Worker exited before entering the blocked provider call")
            time.sleep(0.025)
        assert provider_started.exists(), "Worker did not enter the blocked provider call"
        running = ProductionStageTaskStore(path).get(project_id="p", run_id="r", task_id=task["task_id"])
        assert running["status"] == "running"
        assert running["attempt_count"] == 1
    finally:
        first.kill()
        first.wait(timeout=5)

    # Simulate the expired lease observed on backend restart. The second worker
    # can read the task, but recovery_required is not a submission-ready state.
    with store._connect() as db:
        db.execute("UPDATE production_stage_tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                   (task["task_id"],))
    recovered = ProductionStageTaskStore(path).get(project_id="p", run_id="r", task_id=task["task_id"])
    assert recovered["status"] == "recovery_required"
    restarted = start_worker()
    assert restarted.wait(timeout=10) == 0
    final = ProductionStageTaskStore(path).get(project_id="p", run_id="r", task_id=task["task_id"])
    assert final["status"] == "recovery_required"
    assert final["attempt_count"] == 1
    assert provider_calls.read_text(encoding="utf-8") == "call\\n"


def test_backend_kill_stops_real_guarded_cli_and_keeps_claim_for_reconciliation(tmp_path):
    """Exercise the durable claim and Linux provider guard in one process boundary."""
    import os
    import signal
    import subprocess
    import sys
    import time
    from pathlib import Path

    if not sys.platform.startswith("linux"):
        pytest.skip("Linux PR_SET_PDEATHSIG is the target host lifecycle guarantee")

    db_path = tmp_path / "production.sqlite3"
    store = ProductionStageTaskStore(db_path)
    task = store.enqueue(project_id="p", run_id="r", stage="story_detail",
                         idempotency_key="guarded-backend-crash", request={})
    provider_script = tmp_path / "blocked_provider.py"
    provider_pid_path = tmp_path / "provider.pid"
    provider_call_log = tmp_path / "provider.calls"
    worker_started = tmp_path / "worker.started"
    provider_script.write_text(
        "import os, pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "with open(sys.argv[2], 'a', encoding='utf-8') as calls: calls.write('called\\n')\n"
        "while True: time.sleep(0.05)\n",
        encoding="utf-8",
    )
    worker_script = r'''import pathlib, sys
from story_builder.services.production_stage_tasks import ProductionStageTaskStore
from story_builder.services.reasoning_provider import _run_json_command
db, task_id, provider_script, pid_path, calls, started = sys.argv[1:]
store = ProductionStageTaskStore(db)
claim = store.claim(task_id=task_id, owner_token="backend-process", lease_seconds=60)
if not claim:
    raise SystemExit(0)
pathlib.Path(started).write_text("claimed")
with store.execution_lock(task_id):
    _run_json_command([sys.executable, provider_script, pid_path, calls], "private prompt", timeout_seconds=60)
'''
    environment = dict(os.environ)
    package_root = str(Path(__file__).resolve().parents[2])
    environment["PYTHONPATH"] = package_root + os.pathsep + environment.get("PYTHONPATH", "")

    def start_worker():
        return subprocess.Popen(
            [sys.executable, "-c", worker_script, str(db_path), task["task_id"],
             str(provider_script), str(provider_pid_path), str(provider_call_log), str(worker_started)],
            cwd=tmp_path, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    worker = start_worker()
    provider_pid = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not provider_pid_path.exists():
            if worker.poll() is not None:
                stdout, stderr = worker.communicate(timeout=1)
                pytest.fail(f"backend worker exited before guarded provider started: {stderr or stdout}")
            time.sleep(0.025)
        assert worker_started.exists() and provider_pid_path.exists()
        provider_pid = int(provider_pid_path.read_text(encoding="utf-8"))
        running = store.get(project_id="p", run_id="r", task_id=task["task_id"])
        assert running["status"] == "running" and running["attempt_count"] == 1

        os.kill(worker.pid, signal.SIGKILL)
        worker.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            stat = Path(f"/proc/{provider_pid}/stat")
            if not stat.exists() or stat.read_text().split(") ", 1)[1].startswith("Z "):
                break
            time.sleep(0.025)
        stat = Path(f"/proc/{provider_pid}/stat")
        assert not stat.exists() or stat.read_text().split(") ", 1)[1].startswith("Z "), \
            "guarded provider CLI survived backend SIGKILL"
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)
        if provider_pid is not None:
            stat = Path(f"/proc/{provider_pid}/stat")
            if stat.exists() and not stat.read_text().split(") ", 1)[1].startswith("Z "):
                os.kill(provider_pid, signal.SIGKILL)

    with store._connect() as db:
        db.execute("UPDATE production_stage_tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                   (task["task_id"],))
    recovered = ProductionStageTaskStore(db_path).get(project_id="p", run_id="r", task_id=task["task_id"])
    assert recovered["status"] == "recovery_required"
    restarted_claim = ProductionStageTaskStore(db_path).claim(
        task_id=task["task_id"], owner_token="restarted-backend")
    assert restarted_claim is None
    assert recovered["attempt_count"] == 1
    assert provider_call_log.read_text(encoding="utf-8") == "called\n"


def test_blank_task_keys_rejected_at_request_boundary():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        api.ProductionV2StoryTaskRequest(idempotency_key="   ")
    with pytest.raises(ValidationError):
        api.ProductionV2TextStageTaskRequest(idempotency_key="\n ", source_revision_id="story-canon-aabbccddeeff",
                                            units=[{"unit_id": "scene-1"}])


def test_stage_tasks_are_idempotent_scoped_and_survive_store_restart(tmp_path):
    path = tmp_path / "stage.sqlite3"
    store = ProductionStageTaskStore(path)
    request = {"max_chars_per_chunk": 1200, "parent_revision_id": None}
    first = store.enqueue(project_id="p", run_id="r", stage="story", idempotency_key="click-1", request=request)
    duplicate = ProductionStageTaskStore(path).enqueue(project_id="p", run_id="r", stage="story",
        idempotency_key="click-1", request=request)
    assert duplicate["task_id"] == first["task_id"]
    with pytest.raises(StageTaskConflict):
        store.enqueue(project_id="p", run_id="r", stage="story", idempotency_key="click-1",
                      request={**request, "max_chars_per_chunk": 2400})
    with pytest.raises(StageTaskConflict, match="inspect or reconcile"):
        store.enqueue(project_id="p", run_id="r", stage="story", idempotency_key="click-2", request=request)
    other_project = store.enqueue(project_id="other", run_id="r", stage="story",
        idempotency_key="click-1", request=request)
    assert other_project["task_id"] != first["task_id"]

    claimed = store.claim(task_id=first["task_id"], owner_token="worker-a", lease_seconds=30)
    assert claimed["status"] == "running" and claimed["attempt_count"] == 1
    assert not ProductionStageTaskStore(path).claim(task_id=first["task_id"], owner_token="worker-b")
    completed = store.complete(task_id=first["task_id"], owner_token="worker-a",
                               result={"revision_id": "story-canon-0123456789ab"})
    reopened = ProductionStageTaskStore(path).get(project_id="p", run_id="r", task_id=first["task_id"])
    assert completed["status"] == reopened["status"] == "completed"
    assert reopened["result"] == {"revision_id": "story-canon-0123456789ab"}
    next_attempt = store.enqueue(project_id="p", run_id="r", stage="story", idempotency_key="click-2", request=request)
    assert next_attempt["status"] == "queued" and next_attempt["task_id"] != first["task_id"]


def test_simultaneous_workers_can_claim_a_stage_task_only_once(tmp_path):
    path = tmp_path / "stage.sqlite3"
    store = ProductionStageTaskStore(path)
    task = store.enqueue(project_id="p", run_id="r", stage="scenes", idempotency_key="scene-1",
                         request={"units": [{"unit_id": "scene-001"}]})

    def claim(owner):
        return ProductionStageTaskStore(path).claim(task_id=task["task_id"], owner_token=owner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("worker-a", "worker-b")))
    assert sum(item is not None for item in claims) == 1
    assert ProductionStageTaskStore(path).get(project_id="p", run_id="r", task_id=task["task_id"])["attempt_count"] == 1


def test_expired_worker_lease_fails_closed_for_explicit_recovery(tmp_path):
    path = tmp_path / "stage.sqlite3"
    store = ProductionStageTaskStore(path)
    task = store.enqueue(project_id="p", run_id="r", stage="story", idempotency_key="lost-worker",
                         request={"max_chars_per_chunk": 2400})
    store.claim(task_id=task["task_id"], owner_token="dead-worker", lease_seconds=60)
    with store._connect() as db:
        db.execute("UPDATE production_stage_tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                   (task["task_id"],))
    recovered = ProductionStageTaskStore(path).get(project_id="p", run_id="r", task_id=task["task_id"])
    assert recovered["status"] == "recovery_required"
    assert recovered["error"]["code"] == "stage_task_lease_expired"
    assert ProductionStageTaskStore(path).claim(task_id=task["task_id"], owner_token="new-worker") is None


def test_recovery_requires_explicit_operator_confirmation_and_allows_new_key(tmp_path):
    store = ProductionStageTaskStore(tmp_path / "stage.sqlite3")
    task = store.enqueue(project_id="p", run_id="r", stage="text:scenes", idempotency_key="lost",
                         request={"source_revision_id": "story-canon-123456789abc"})
    store.claim(task_id=task["task_id"], owner_token="dead", lease_seconds=60)
    with store._connect() as db:
        db.execute("UPDATE production_stage_tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE task_id=?",
                   (task["task_id"],))
    assert store.get(project_id="p", run_id="r", task_id=task["task_id"])["status"] == "recovery_required"
    with pytest.raises(StageTaskConflict, match="confirmation"):
        store.resolve_recovery(project_id="p", run_id="r", task_id=task["task_id"],
                               confirm_no_durable_result=False)
    resolved = store.resolve_recovery(project_id="p", run_id="r", task_id=task["task_id"],
                                      confirm_no_durable_result=True)
    assert resolved["status"] == "failed"
    assert resolved["error"]["code"] == "stage_task_reconciled_without_result"
    assert resolved["error"]["retryable"] is True
    retry = store.enqueue(project_id="p", run_id="r", stage="text:scenes", idempotency_key="retry-1",
                          request={"source_revision_id": "story-canon-123456789abc"})
    assert retry["status"] == "queued"


def test_text_stage_task_api_persists_revision_and_does_not_repeat_provider(tmp_path, monkeypatch):
    project_store = api.ProjectStore(tmp_path / "projects")
    project = project_store.create_project(title="Queued scenes", story_input="Mira opens an observatory.",
                                           automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", project_store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api.reasoning_provider, "model_for", lambda _provider: "gpt-6-sol")
    monkeypatch.setattr(api, "generate_story_canon", lambda **kwargs: {
        "schema_version": 1, "revision_id": "story-canon-aabbccddeeff", "title": kwargs["title"],
        "user_story_input": kwargs["source_text"], "source_hash": hashlib.sha256(kwargs["source_text"].encode()).hexdigest(),
        "provider": kwargs["provider"], "expanded_story": kwargs["source_text"], "story_goal": "Open the observatory",
        "tone": [], "continuity_rules": [], "visual_style_notes": [], "source_facts": [], "inferred_details": [],
        "chunks": [{"chunk_id": "story_chunk_0001", "index": 1, "source_start": 0,
            "source_end": len(kwargs["source_text"]), "source_excerpt": kwargs["source_text"],
            "expanded_text": kwargs["source_text"], "source_facts": [], "inferred_details": [],
            "continuity_summary": "Mira opens observatory."}],
        "completeness": {"expected_chunk_ids": ["story_chunk_0001"], "completed_chunk_ids": ["story_chunk_0001"],
            "source_coverage": [0, len(kwargs["source_text"])], "all_source_chunks_echoed": True,
            "all_fact_evidence_verified": True}})
    calls = []
    monkeypatch.setattr(api, "generate_chunked_units", lambda **kwargs: (calls.append(kwargs["stage"]) or {
        "stage": kwargs["stage"], "items": [{"unit_id": "scene-001", "content": {"description": "Mira opens it."}}],
        "expected_unit_ids": ["scene-001"], "completed_unit_ids": ["scene-001"], "complete": True}))
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="queued-scenes-run", control_mode="manual")))
    story = api.detail_production_v2_story(project["id"], run["run_id"], api.ProductionV2StoryDetailRequest())["revision"]
    asyncio.run(api.accept_production_v2_story_revision(project["id"], run["run_id"], story["revision_id"],
        api.ProductionV2StoryAcceptRequest(expected_source_hash=story["source_hash"])))
    payload = api.ProductionV2TextStageTaskRequest(idempotency_key="scene-click-1",
        source_revision_id=story["revision_id"], units=[{"unit_id": "scene-001", "source": "Mira opens it."}])
    queued = asyncio.run(api.enqueue_production_v2_text_task(project["id"], run["run_id"], "scenes", payload,
        api.BackgroundTasks()))
    api._execute_production_story_stage_task(queued["task_id"])
    api._execute_production_story_stage_task(queued["task_id"])
    completed = asyncio.run(api.get_production_v2_text_task(project["id"], run["run_id"], "scenes", queued["task_id"]))
    assert completed["status"] == "completed"
    assert completed["revision"]["stage"] == "scenes"
    assert completed["revision"]["items"][0]["unit_id"] == "scene-001"
    assert calls == ["scenes"]
    assert completed["revision"]["stage_task_id"] == queued["task_id"]
    store = api._production_stage_task_store()
    with store._connect() as db:
        db.execute("UPDATE production_stage_tasks SET status='recovery_required',result_json=NULL,"
                   "owner_token=NULL,lease_until=NULL WHERE task_id=?", (queued["task_id"],))
    reconciled = asyncio.run(api.get_production_v2_text_task(project["id"], run["run_id"], "scenes", queued["task_id"]))
    assert reconciled["status"] == "completed"
    assert reconciled["revision"]["revision_id"] == completed["revision"]["revision_id"]
    recovered_task = store.get(project_id=project["id"], run_id=run["run_id"], task_id=queued["task_id"])
    assert recovered_task["result"]["provider"] == "codex"
    assert recovered_task["result"]["model"] == "gpt-6-sol"
    assert calls == ["scenes"]
    with pytest.raises(api.HTTPException) as wrong_stage:
        asyncio.run(api.get_production_v2_story_task(project["id"], run["run_id"], queued["task_id"]))
    assert wrong_stage.value.status_code == 404


def test_story_task_api_worker_persists_one_revision_and_replays_status(tmp_path, monkeypatch):
    project_store = api.ProjectStore(tmp_path / "projects")
    project = project_store.create_project(title="Queued story", story_input="Mira finds the observatory key.",
                                           automation_mode=False)
    monkeypatch.setattr(api, "PROJECT_STORE", project_store)
    monkeypatch.setattr(api, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(api, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(api.reasoning_provider, "model_for", lambda _provider: "gpt-6-sol")
    generation_calls = []

    def fake_generation(*, title, source_text, provider, **_kwargs):
        generation_calls.append(source_text)
        return {"schema_version": 1, "revision_id": "story-canon-aabbccddeeff", "title": title,
            "user_story_input": source_text, "source_hash": hashlib.sha256(source_text.encode()).hexdigest(),
            "provider": provider, "model": "cpu-test", "expanded_story": source_text,
            "story_goal": "Find the key", "tone": [], "continuity_rules": [], "visual_style_notes": [],
            "source_facts": [], "inferred_details": [], "chunks": [{"chunk_id": "story_chunk_0001",
                "index": 1, "source_start": 0, "source_end": len(source_text), "source_excerpt": source_text,
                "expanded_text": source_text, "source_facts": [], "inferred_details": [],
                "continuity_summary": "", "story_goal": "Find the key", "tone": [],
                "continuity_rules": [], "visual_style_notes": []}],
            "completeness": {"expected_chunk_ids": ["story_chunk_0001"],
                "completed_chunk_ids": ["story_chunk_0001"], "source_coverage": [0, len(source_text)],
                "all_source_chunks_echoed": True, "all_fact_evidence_verified": True}}

    monkeypatch.setattr(api, "generate_story_canon", fake_generation)
    run = asyncio.run(api.create_production_v2_run(project["id"], api.ProductionV2RunRequest(
        idempotency_key="story-task-run", control_mode="manual")))
    background = api.BackgroundTasks()
    payload = api.ProductionV2StoryTaskRequest(idempotency_key="story-task-click-1")
    queued = asyncio.run(api.enqueue_production_v2_story_task(project["id"], run["run_id"], payload, background))
    duplicate = asyncio.run(api.enqueue_production_v2_story_task(project["id"], run["run_id"], payload,
        api.BackgroundTasks()))
    assert queued["task_id"] == duplicate["task_id"]
    assert queued["status"] == "queued"

    api._execute_production_story_stage_task(queued["task_id"])
    api._execute_production_story_stage_task(queued["task_id"])
    completed = asyncio.run(api.get_production_v2_story_task(project["id"], run["run_id"], queued["task_id"]))
    assert completed["status"] == "completed"
    assert completed["revision"]["revision_id"] == "story-canon-aabbccddeeff"
    assert completed["revision"]["review_status"] == "pending_review"
    assert completed["revision"]["stage_task_id"] == queued["task_id"]
    assert completed["revision"]["provider"] == "codex"
    assert completed["revision"]["model"] == "gpt-6-sol"
    assert generation_calls == ["Mira finds the observatory key."]
    store = api._production_stage_task_store()
    with store._connect() as db:
        db.execute("UPDATE production_stage_tasks SET status='recovery_required',result_json=NULL,"
                   "owner_token=NULL,lease_until=NULL WHERE task_id=?", (queued["task_id"],))
    reconciled = asyncio.run(api.get_production_v2_story_task(project["id"], run["run_id"], queued["task_id"]))
    assert reconciled["status"] == "completed"
    assert reconciled["revision"]["revision_id"] == completed["revision"]["revision_id"]
    recovered_task = store.get(project_id=project["id"], run_id=run["run_id"], task_id=queued["task_id"])
    assert recovered_task["result"]["provider"] == "codex"
    assert recovered_task["result"]["model"] == "gpt-6-sol"
    assert generation_calls == ["Mira finds the observatory key."]
    tasks = asyncio.run(api.get_production_v2_run(project["id"], run["run_id"]))["stage_tasks"]
    assert len(tasks) == 1 and tasks[0]["task_id"] == queued["task_id"]
    assert tasks[0]["status"] == "completed"
    with pytest.raises(api.HTTPException) as conflict:
        asyncio.run(api.enqueue_production_v2_story_task(project["id"], run["run_id"],
            api.ProductionV2StoryTaskRequest(idempotency_key="story-task-click-1", max_chars_per_chunk=1200),
            api.BackgroundTasks()))
    assert conflict.value.status_code == 409
