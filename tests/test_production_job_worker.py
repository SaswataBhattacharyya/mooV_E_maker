from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from story_builder.services import production_job_worker as worker_module
from story_builder.services.production_job_worker import PreparedTake, ProductionJobWorker, ProductionWorkerSupervisor
from story_builder.services.production_ledger import ProductionLedger


@pytest.fixture(autouse=True)
def isolate_comfy_submission_lock(monkeypatch, tmp_path):
    """Contract tests must not wait behind a live app/ComfyUI submission lock."""
    monkeypatch.setenv("STORY_BUILDER_COMFY_SUBMISSION_LOCK", str(tmp_path / "comfy-test.lock"))


def _queued_ledger(path: Path):
    ledger = ProductionLedger(path)
    run = ledger.create_run(project_id="p1", idempotency_key="run", config={"story": "test"})
    take = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
        idempotency_key="take", input_snapshot={"validation_hash": "a" * 64})
    return ledger, take


def test_worker_submits_reserved_prompt_collects_outputs_and_cleans_owned_inputs(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    calls = []
    cleanup = []
    released = []

    def request(url, *, method="GET", payload=None, timeout_seconds=30):
        calls.append((url, method, payload))
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        if method == "POST":
            saved = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]
            assert saved["prompt_id"] == payload["prompt_id"]
            assert saved["status"] == "submitting"
            return {"prompt_id": payload["prompt_id"]}
        payload_id = url.rsplit("/", 1)[-1]
        return {payload_id: {"status": {"status_str": "success", "completed": True},
            "outputs": {"video": [{"filename": "take.mp4", "subfolder": "", "type": "output"}]}}}

    def collect(take, state):
        assert take["take_id"] == "t1"
        assert "outputs" in state
        return [{"asset_id": "pa-0123456789abcdef", "sha256": "b" * 64, "kind": "video"}]

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda take:
        PreparedTake({"1": {"class_type": "Test"}}, lambda: cleanup.append("prepared")),
        collect=collect, cleanup=lambda take: cleanup.append(take["take_id"]), release_idle=lambda **kw:
        released.append(kw) or {"status": "idle"}, request_json=request, sleep=lambda _: None)

    result = worker.process_one()

    assert result["status"] == "needs_review"
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]
    assert current["status"] == "needs_review"
    assert current["finished_at"]
    assert current["lease_owner"] is None and current["lease_until"] is None
    assert current["output_hashes"] == [{"asset_id": "pa-0123456789abcdef", "sha256": "b" * 64, "kind": "video"}]
    assert len([call for call in calls if call[1] == "POST"]) == 1
    assert cleanup == ["prepared", "t1"]
    assert len(released) == 1


def test_worker_does_not_delete_staging_when_submit_result_is_ambiguous(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    cleanup = []

    def request(url, **kwargs):
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        raise TimeoutError("socket timed out after request body was sent")

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda take:
        PreparedTake({"1": {"class_type": "Test"}}, lambda: cleanup.append("prepared")),
        collect=lambda *_: [], cleanup=lambda take: cleanup.append(take["take_id"]),
        release_idle=lambda **_: {}, request_json=request, sleep=lambda _: None)
    result = worker.process_one()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["status"] == "recovery_required"
    assert current["status"] == "recovery_required"
    assert current["prompt_id"] == result["prompt_id"]
    assert cleanup == []


def test_worker_records_definite_comfy_rejection_and_cleans_staging(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    cleanup = []

    def request(url, **kwargs):
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        raise urllib.error.HTTPError(url, 400, "bad graph", {}, None)

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda take:
        PreparedTake({"1": {"class_type": "Test"}}, lambda: cleanup.append("prepared")),
        collect=lambda *_: [], cleanup=lambda take: cleanup.append(take["take_id"]),
        release_idle=lambda **_: {}, request_json=request, sleep=lambda _: None)
    result = worker.process_one()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["status"] == "failed"
    assert current["status"] == "failed"
    assert current["error"]["code"] == "comfy_submission_rejected"
    assert cleanup == ["prepared", "t1"]


def test_worker_idle_does_not_make_comfy_calls(tmp_path: Path):
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    calls = []
    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, request_json=lambda *a, **k: calls.append(a),
        release_idle=lambda **_: {}, sleep=lambda _: None)
    assert worker.process_one() == {"status": "idle"}
    assert calls == []


def test_director_owned_h3_take_blocks_before_preparation_and_gpu_when_provider_fails(tmp_path: Path):
    ledger = ProductionLedger(tmp_path / "ledger.sqlite3")
    run = ledger.create_run(project_id="p1", idempotency_key="full-run",
        config={"control_mode": "fully_automated", "provider": "codex"})
    queued = ledger.queue_take(project_id="p1", run_id=run["run_id"], shot_id="s1", take_id="t1",
        idempotency_key="full-take", input_snapshot={"validation_hash": "a" * 64})
    preflights = []

    def fail_preflight(provider):
        preflights.append(provider)
        raise RuntimeError("Codex rules cannot be parsed")

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy",
        prepare=lambda _take: pytest.fail("provider failure must block before staging"),
        collect=lambda *_args: [], cleanup=lambda _take: None,
        director_provider_preflight=fail_preflight,
        request_json=lambda url, **_kwargs: {"queue_running": [], "queue_pending": []}
            if url.endswith("/queue") else pytest.fail("provider failure must block before prompt POST"),
        gpu_inspector=lambda **_kwargs: pytest.fail("provider failure must block before GPU admission"),
        sleep=lambda _seconds: None)

    result = worker.process_one()

    take = ledger.get_run(project_id="p1", run_id=run["run_id"])["takes"][0]
    assert preflights == ["codex"]
    assert result["status"] == "failed"
    assert take["take_id"] == queued["take_id"]
    assert take["status"] == "failed"
    assert take["error"]["code"] == "director_provider_unavailable"
    assert take["prompt_id"] is None


def test_worker_keeps_take_in_website_queue_while_comfyui_is_busy(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    prepared = []
    worker = ProductionJobWorker(ledger, comfy_url="http://comfy",
        prepare=lambda take: prepared.append(take) or None, collect=lambda *_: [], cleanup=lambda _: None,
        release_idle=lambda **_: {},
        request_json=lambda url, **_: {"queue_running": [[1, "active"]], "queue_pending": []},
        sleep=lambda _: None)

    result = worker.process_one()
    take = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["status"] == "waiting_for_comfyui"
    assert take["status"] == "queued"
    assert take["prompt_id"] is None
    assert prepared == []


def test_worker_rechecks_comfyui_before_submit_and_requeues_staged_take(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    calls = []
    cleaned = []

    def request(url, *, method="GET", payload=None, timeout_seconds=30):
        calls.append((url, method))
        if url.endswith("/queue"):
            if sum(1 for entry in calls if entry[0].endswith("/queue")) == 1:
                return {"queue_running": [], "queue_pending": []}
            return {"queue_running": [], "queue_pending": [[2, "other"]]}
        raise AssertionError(f"Unexpected ComfyUI call: {method} {url}")

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy",
        prepare=lambda _: PreparedTake({"1": {"class_type": "Test"}}, lambda: cleaned.append("prepared")),
        collect=lambda *_: [], cleanup=lambda _: cleaned.append("take"), release_idle=lambda **_: {},
        request_json=request, sleep=lambda _: None)

    result = worker.process_one()
    take = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["status"] == "waiting_for_comfyui"
    assert take["status"] == "queued" and take["prompt_id"] is None
    assert [entry for entry in calls if entry[0].endswith("/prompt")] == []
    assert cleaned == ["prepared", "take"]


def test_worker_comfy_render_error_is_terminal_and_releases_only_via_idle_guard(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    cleanup, released = [], []

    def request(url, *, method="GET", payload=None, timeout_seconds=30):
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        if method == "POST":
            return {"prompt_id": payload["prompt_id"]}
        prompt_id = url.rsplit("/", 1)[-1]
        return {prompt_id: {"status": {"status_str": "error", "messages": [["execution_error", {"node_id": "7"}]]}}}

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda take:
        PreparedTake({"1": {"class_type": "Test"}}, lambda: cleanup.append("prepared")),
        collect=lambda *_: [], cleanup=lambda take: cleanup.append(take["take_id"]),
        release_idle=lambda **kw: released.append(kw) or {"status": "active-work-preserved"},
        request_json=request, sleep=lambda _: None)
    result = worker.process_one()

    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]
    assert result["status"] == "failed"
    assert current["status"] == "failed"
    assert current["error"]["code"] == "comfy_render_failed"
    assert cleanup == ["prepared", "t1"]
    assert len(released) == 1


def test_worker_missing_output_does_not_mark_take_as_accepted(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")

    def request(url, *, method="GET", payload=None, timeout_seconds=30):
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        if method == "POST":
            return {"prompt_id": payload["prompt_id"]}
        prompt_id = url.rsplit("/", 1)[-1]
        return {prompt_id: {"status": {"status_str": "success", "completed": True}, "outputs": {}}}

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda take:
        PreparedTake({"1": {"class_type": "Test"}}, lambda: None), collect=lambda *_: [],
        cleanup=lambda _: None, release_idle=lambda **_: {}, request_json=request, sleep=lambda _: None)
    result = worker.process_one()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]
    assert result["status"] == "failed"
    assert current["status"] == "failed"
    assert current["error"]["code"] == "output_missing"


def test_restart_reconciliation_collects_completed_prompt_without_resubmitting(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    ledger.claim_next_queued_take(lease_owner="old-worker")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    calls, cleanup, released = [], [], []

    def request(url, **kwargs):
        calls.append(url)
        if url.endswith("/queue"):
            return {"queue_pending": [], "queue_running": []}
        return {prompt_id: {"status": {"status_str": "success", "completed": True}, "outputs": {"video": []}}}

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda take, state: [{"asset_id": "pa-0123456789abcdef", "sha256": "d" * 64}],
        cleanup=lambda take: cleanup.append(take["take_id"]), release_idle=lambda **kw: released.append(kw),
        request_json=request, sleep=lambda _: None)
    result = worker.reconcile_existing_once()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["observed"] == 1
    assert calls == ["http://comfy/queue", f"http://comfy/history/{prompt_id}"]
    assert current["status"] == "needs_review"
    assert current["output_hashes"][0]["asset_id"] == "pa-0123456789abcdef"
    assert cleanup == ["t1"] and len(released) == 1


def test_worker_process_crash_reconciles_accepted_prompt_without_resubmitting(tmp_path: Path):
    """Kill the real worker after remote acceptance but before its reply is read."""
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    marker = tmp_path / "remote-accepted.json"
    child = tmp_path / "worker-submit.py"
    child.write_text(r'''import json, sys, time
from pathlib import Path
from story_builder.services import production_job_worker as worker_module
from story_builder.services.production_job_worker import PreparedTake, ProductionJobWorker
from story_builder.services.production_ledger import ProductionLedger

ledger_path, marker_path = map(Path, sys.argv[1:])
class Watchdog:
    def check(self): pass
worker_module.ensure_prompt_watchdog = lambda **_kwargs: Watchdog()
worker_module.record_gpu_telemetry = lambda *_args, **_kwargs: None

def request(url, *, method="GET", payload=None, timeout_seconds=30):
    if url.endswith("/queue"):
        return {"queue_running": [], "queue_pending": []}
    if method == "POST":
        marker_path.write_text(json.dumps({"prompt_id": payload["prompt_id"]}))
        # Model ComfyUI accepting the request while its response is lost to the
        # owner process. The parent kills us at this precise boundary.
        while True: time.sleep(0.1)
    raise AssertionError(f"Unexpected request before process termination: {url}")

worker = ProductionJobWorker(ProductionLedger(ledger_path), comfy_url="http://comfy",
    prepare=lambda _take: PreparedTake({"1": {"class_type": "Test"}}, lambda: None),
    collect=lambda *_args: [], cleanup=lambda _take: None, request_json=request,
    gpu_inspector=lambda **_kwargs: {"recorded_at": "now", "gpu": {"temperature_c": 50,
        "graphics_clock_mhz": 2070, "utilization_pct": 1, "free_memory_bytes": 100000000000},
        "compute_processes": []},
    operating_point_reader=lambda: {"temperature_c": 50, "graphics_clock_mhz": 2070},
    sleep=lambda _seconds: None)
worker.process_one()
''', encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(repo_root), env.get("PYTHONPATH", "")]))
    process = subprocess.Popen([sys.executable, str(child), str(ledger.path), str(marker)],
        cwd=repo_root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline and not marker.exists() and process.poll() is None:
            time.sleep(0.02)
        assert marker.exists(), "worker never reached the simulated remote-acceptance boundary"
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)

    prompt_id = json.loads(marker.read_text(encoding="utf-8"))["prompt_id"]
    calls: list[str] = []
    def recovered_request(url, **_kwargs):
        calls.append(url)
        if url.endswith("/queue"):
            return {"queue_pending": [], "queue_running": []}
        return {prompt_id: {"status": {"status_str": "success", "completed": True},
            "outputs": {"video": [{"filename": "recovered.mp4"}]}}}

    recovery_worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _take: None,
        collect=lambda _take, _state: [{"asset_id": "pa-0123456789abcdef", "sha256": "e" * 64,
            "kind": "video"}], cleanup=lambda _take: None, request_json=recovered_request,
        release_idle=lambda **_kwargs: {}, sleep=lambda _seconds: None)
    recovery = recovery_worker.reconcile_existing_once()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert recovery["observed"] == 1
    assert calls == ["http://comfy/queue", f"http://comfy/history/{prompt_id}"]
    assert current["prompt_id"] == prompt_id
    assert current["status"] == "needs_review"
    assert current["output_hashes"] == [{"asset_id": "pa-0123456789abcdef", "sha256": "e" * 64,
        "kind": "video"}]
    assert current["attempt"] == 1


def test_restart_reconciliation_never_treats_comfy_network_error_as_absent(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    ledger.claim_next_queued_take(lease_owner="old-worker")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, request_json=lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
        release_idle=lambda **_: {}, sleep=lambda _: None)
    worker.reconcile_existing_once()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]
    assert current["status"] == "running"
    assert current["prompt_id"] == prompt_id


def test_restart_fails_expired_pre_submit_claim_without_comfy_request(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    ledger.claim_next_queued_take(lease_owner="old-worker")
    expired = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE production_takes SET lease_until=? WHERE project_id=? AND take_id=?",
            (expired, "p1", "t1"))
    calls, cleaned = [], []
    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda take: cleaned.append(take["take_id"]),
        request_json=lambda *args, **kwargs: calls.append(args), release_idle=lambda **_: {})

    result = worker.reconcile_existing_once()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["observed"] == 1
    assert current["status"] == "failed"
    assert current["prompt_id"] is None
    assert current["error"]["code"] == "worker_interrupted_before_submit"
    assert calls == []
    assert cleaned == ["t1"]


def test_preparation_heartbeat_prevents_live_claim_from_expiring(tmp_path: Path):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    import threading
    import time
    preparing = threading.Event()

    def prepare(_take):
        preparing.set()
        time.sleep(0.35)
        raise RuntimeError("stop before submit")

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=prepare,
        collect=lambda *_: [], cleanup=lambda _: None, release_idle=lambda **_: {},
        request_json=lambda url, **_k: {"queue_running": [], "queue_pending": []} if url.endswith("/queue") else {},
        lease_seconds=1, heartbeat_interval_seconds=0.05)
    result_box = []
    caller = threading.Thread(target=lambda: result_box.append(worker.process_one()))
    caller.start()
    assert preparing.wait(timeout=2)
    time.sleep(0.15)
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]
    assert datetime.fromisoformat(current["lease_until"]) > datetime.now(timezone.utc)
    caller.join(timeout=2)
    assert not caller.is_alive()
    assert result_box[0]["status"] == "failed"


def test_worker_settles_confirmed_user_interrupt_as_cancelled(tmp_path: Path, monkeypatch):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    class Watchdog:
        def check(self): pass
    monkeypatch.setattr(worker_module, "ensure_prompt_watchdog", lambda **_: Watchdog())
    monkeypatch.setattr(worker_module, "record_gpu_telemetry", lambda *_args, **_kwargs: None)

    def request(url, *, method="GET", payload=None, timeout_seconds=30):
        if url.endswith("/queue"):
            return {"queue_running": [], "queue_pending": []}
        if method == "POST":
            return {"prompt_id": payload["prompt_id"]}
        take = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]
        assert take["status"] == "running"
        ledger.transition_take(project_id="p1", take_id="t1", status="cancel_requested",
            payload={"reason": "operator", "interrupt_requested": True})
        return {url.rsplit("/", 1)[-1]: {"status": {"status_str": "error", "messages": [
            ["execution_interrupted", {"prompt_id": take["prompt_id"]}],
        ]}}}

    cleanup, released = [], []
    worker = ProductionJobWorker(ledger, comfy_url="http://comfy",
        prepare=lambda _: PreparedTake({"1": {"class_type": "Test"}}, lambda: cleanup.append("prepared")),
        collect=lambda *_: [], cleanup=lambda take: cleanup.append(take["take_id"]),
        release_idle=lambda **kw: released.append(kw) or {"status": "idle"},
        request_json=request,
        gpu_inspector=lambda **_: {"recorded_at": "now", "gpu": {"temperature_c": 50,
            "graphics_clock_mhz": 2070, "utilization_pct": 1, "free_memory_bytes": 100_000_000_000},
            "compute_processes": []},
        operating_point_reader=lambda: {"temperature_c": 50, "graphics_clock_mhz": 2070},
        sleep=lambda _: None)

    result = worker.process_one()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result == {"status": "cancelled", "take_id": "t1",
        "prompt_id": current["prompt_id"], "reason": "comfy_execution_interrupted"}
    assert current["status"] == "cancelled"
    assert current["finished_at"] and current["lease_owner"] is None and current["lease_until"] is None
    assert current.get("error") is None
    assert cleanup == ["prepared", "t1"]
    assert len(released) == 1


def test_request_json_accepts_empty_success_acknowledgment(monkeypatch):
    class EmptyResponse:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return b""
    monkeypatch.setattr(worker_module.urllib.request, "urlopen", lambda *_args, **_kwargs: EmptyResponse())
    assert worker_module._request_json("http://comfy/interrupt", method="POST") == {}


def test_restart_reconciler_preserves_cancelled_state_for_interrupted_prompt(tmp_path: Path, monkeypatch):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    ledger.claim_next_queued_take(lease_owner="worker")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    ledger.reconcile_remote_state(project_id="p1", take_id="t1", observed="running")
    ledger.transition_take(project_id="p1", take_id="t1", status="cancel_requested",
        payload={"interrupt_requested": True})
    cleaned, released = [], []

    class Watchdog:
        def check(self): pass
    monkeypatch.setattr(worker_module, "ensure_prompt_watchdog", lambda **_: Watchdog())
    def request(url, **_kwargs):
        if url.endswith("/queue"):
            return {"queue_pending": [], "queue_running": []}
        assert url.endswith(f"/history/{prompt_id}")
        return {prompt_id: {"status": {"status_str": "error", "messages": [
            ["execution_interrupted", {"prompt_id": prompt_id}],
        ]}}}
    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda take: cleaned.append(take["take_id"]),
        request_json=request, release_idle=lambda **kw: released.append(kw) or {"status": "idle"})

    result = worker.reconcile_existing_once()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result == {"observed": 1}
    assert current["status"] == "cancelled"
    assert current.get("error") is None and current["finished_at"]
    assert current["lease_owner"] is None and current["lease_until"] is None
    assert cleaned == ["t1"] and len(released) == 1


def test_restart_reconciler_checks_queue_before_declaring_reserved_prompt_absent(tmp_path: Path, monkeypatch):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    ledger.claim_next_queued_take(lease_owner="old-worker")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    class Watchdog:
        def check(self): pass
    monkeypatch.setattr(worker_module, "ensure_prompt_watchdog", lambda **_: Watchdog())
    calls: list[str] = []
    def request(url, **_kwargs):
        calls.append(url)
        if url.endswith("/queue"):
            return {"queue_pending": [[1, prompt_id, {}, {}, []]], "queue_running": []}
        raise AssertionError("queued prompt must not be treated as absent from empty history")

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, request_json=request, sleep=lambda _: None)
    result = worker.reconcile_existing_once()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["observed"] == 0
    assert calls == ["http://comfy/queue"]
    assert current["status"] == "running"
    assert current["prompt_id"] == prompt_id


def test_restart_reconciler_defers_when_comfy_queue_shape_is_malformed(tmp_path: Path, monkeypatch):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    ledger.claim_next_queued_take(lease_owner="old-worker")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    class Watchdog:
        def check(self): pass
    monkeypatch.setattr(worker_module, "ensure_prompt_watchdog", lambda **_: Watchdog())
    calls: list[str] = []
    def request(url, **_kwargs):
        calls.append(url)
        return {"queue_pending": "not-a-list", "queue_running": []}

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, request_json=request, sleep=lambda _: None)
    result = worker.reconcile_existing_once()
    current = ledger.get_run(project_id="p1", run_id=queued["run_id"])["takes"][0]

    assert result["observed"] == 0
    assert calls == ["http://comfy/queue"]
    assert current["status"] == "running"
    assert current["prompt_id"] == prompt_id


def test_restart_reconciler_is_idempotent_for_repeated_missing_prompt(tmp_path: Path, monkeypatch):
    ledger, queued = _queued_ledger(tmp_path / "ledger.sqlite3")
    ledger.claim_next_queued_take(lease_owner="old-worker")
    prompt_id = ledger.reserve_prompt_id(project_id="p1", take_id="t1")["prompt_id"]
    ledger.bind_prompt_id(project_id="p1", take_id="t1", prompt_id=prompt_id)
    class Watchdog:
        def check(self): pass
    monkeypatch.setattr(worker_module, "ensure_prompt_watchdog", lambda **_: Watchdog())
    calls: list[str] = []
    def request(url, **_kwargs):
        calls.append(url)
        if url.endswith("/queue"):
            return {"queue_pending": [], "queue_running": []}
        return {}

    worker = ProductionJobWorker(ledger, comfy_url="http://comfy", prepare=lambda _: None,
        collect=lambda *_: [], cleanup=lambda _: None, request_json=request, sleep=lambda _: None)
    first = worker.reconcile_existing_once()
    run_after_first = ledger.get_run(project_id="p1", run_id=queued["run_id"])
    event_count = len(run_after_first["events"])
    second = worker.reconcile_existing_once()
    run_after_second = ledger.get_run(project_id="p1", run_id=queued["run_id"])

    assert first["observed"] == 1
    assert run_after_first["takes"][0]["status"] == "recovery_required"
    assert second["observed"] == 0
    assert len(run_after_second["events"]) == event_count


def test_worker_supervisor_waits_when_only_reconciling_an_active_remote_prompt():
    class IdleWithRecovery:
        def reconcile_existing_once(self): return {"observed": 1}
        def process_one(self): return {"status": "idle"}
        def review_next_take(self): return {"status": "idle"}

    class StopOnWait:
        def __init__(self):
            import threading
            self.stop = threading.Event()
            self.waits: list[float] = []
        def is_set(self): return self.stop.is_set()
        def set(self): self.stop.set()
        def wait(self, timeout=None):
            self.waits.append(timeout)
            self.stop.set()
            return True

    supervisor = ProductionWorkerSupervisor(IdleWithRecovery(), idle_sleep_seconds=0.25)
    stop = StopOnWait()
    supervisor._stop = stop
    supervisor._run()

    assert stop.waits == [0.25]
